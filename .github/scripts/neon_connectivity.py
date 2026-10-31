"""Bounded, credential-free Neon DNS/TCP probe. Never speak PostgreSQL.

The child isolates potentially blocking DNS; its host arrives on stdin, not argv.
Only fixed status codes cross the logging boundary. No exception text is logged.
"""

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time

HOST_ENV = "CENTERWAY_NEON_DIAGNOSTIC_HOST"
TOTAL_TIMEOUT = 15
TCP_BUDGET = 8
RESULTS = frozenset({
    "tcp_reachable", "dns_failed", "tcp_unreachable", "timeout",
    "invalid_configuration", "non_public_address", "internal_error",
})
HOST_PATTERN = re.compile(r"ep-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+\.neon\.tech", re.ASCII)


def valid_host(host):
    # A hostname only, never a URL, DSN, port, address, or pooled endpoint.
    return bool(len(host) <= 253 and HOST_PATTERN.fullmatch(host)
                and not host.split(".", 1)[0].endswith("-pooler"))


def probe(host):
    if not valid_host(host):
        return "invalid_configuration"
    try:
        addresses = socket.getaddrinfo(host, 5432, type=socket.SOCK_STREAM)
    except OSError:
        return "dns_failed"
    if not addresses:
        return "dns_failed"
    # Refuse the entire resolution if any address is private/reserved. Connect
    # directly to these validated addresses, without a second DNS lookup.
    if any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        return "non_public_address"
    deadline = time.monotonic() + TCP_BUDGET
    for family, kind, protocol, _, address in addresses[:8]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timeout"
        try:
            with socket.socket(family, kind, protocol) as connection:
                connection.settimeout(min(remaining, 3))
                connection.connect(address)
                # No send/sendall, TLS, PostgreSQL startup, authentication or SQL.
                return "tcp_reachable"
        except OSError:
            continue
    return "tcp_unreachable"


def bounded_probe(host):
    if not valid_host(host):
        return "invalid_configuration"
    try:
        child = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--worker"],
            input=host, text=True, capture_output=True, timeout=TOTAL_TIMEOUT,
            # Do not forward runner tokens, database variables or credentials.
            env={"LANG": "C.UTF-8"}, check=False,
        )
        result = child.stdout.strip()
        return result if child.returncode == 0 and result in RESULTS else "internal_error"
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "internal_error"


def main():
    result = bounded_probe(os.environ.get(HOST_ENV, ""))
    report = {
        "schema_version": 1, "result": result, "port": 5432,
        "application_bytes_sent": 0, "database_login_attempted": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if result == "tcp_reachable" else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        try:
            print(probe(sys.stdin.read(254)))
        except Exception:
            print("internal_error")
    else:
        sys.exit(main())
