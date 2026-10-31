"""No real DNS, network, credentials, database, or backup in this suite."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/neon_connectivity.py"
SPEC = importlib.util.spec_from_file_location("neon_connectivity", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
HOST = "ep-example-only.c-7.eu-central-1.aws.neon.tech"
SENSITIVE = "postgresql://private-user:private-password@hidden.invalid/private-db"
ADDRESS = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 5432))


class ProbeTests(unittest.TestCase):
    def setUp(self):
        # An unmocked network operation fails every test instead of reaching out.
        self.dns = patch.object(probe.socket, "getaddrinfo", side_effect=AssertionError("unexpected DNS")).start()
        self.socket = patch.object(probe.socket, "socket", side_effect=AssertionError("unexpected TCP")).start()
        self.addCleanup(patch.stopall)

    def test_invalid_and_missing_config_never_resolve(self):
        for value in ("", SENSITIVE, "127.0.0.1", "localhost", HOST + ":5432",
                      HOST + "\n", "ep-test-pooler.aws.neon.tech", "ep-test.aws.neon.tech.evil.invalid"):
            with self.subTest(value=value):
                self.assertEqual(probe.bounded_probe(value), "invalid_configuration")
        self.dns.assert_not_called()
        self.socket.assert_not_called()

    def test_dns_error_is_a_fixed_code(self):
        self.dns.side_effect = socket.gaierror(SENSITIVE)
        self.assertEqual(probe.probe(HOST), "dns_failed")
        self.socket.assert_not_called()

    def test_empty_dns_answer(self):
        self.dns.side_effect = None
        self.dns.return_value = []
        self.assertEqual(probe.probe(HOST), "dns_failed")

    def test_private_reserved_or_mixed_answers_are_rejected(self):
        self.dns.side_effect = None
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.0.2.1"):
            self.dns.return_value = [ADDRESS, (*ADDRESS[:4], (address, 5432))]
            self.assertEqual(probe.probe(HOST), "non_public_address")
        self.socket.assert_not_called()

    def connection(self):
        self.dns.side_effect = None
        self.dns.return_value = [ADDRESS]
        self.socket.side_effect = None
        connection = self.socket.return_value.__enter__.return_value
        return connection

    def test_connect_and_close_without_sending_application_data(self):
        connection = self.connection()
        self.assertEqual(probe.probe(HOST), "tcp_reachable")
        self.dns.assert_called_once_with(HOST, 5432, type=socket.SOCK_STREAM)
        connection.connect.assert_called_once_with(ADDRESS[4])
        connection.settimeout.assert_called_once()
        connection.send.assert_not_called()
        connection.sendall.assert_not_called()
        connection.recv.assert_not_called()
        self.socket.return_value.__exit__.assert_called_once()

    def test_refused_connection_and_timeout_do_not_leak_exception(self):
        connection = self.connection()
        for error in (ConnectionRefusedError(SENSITIVE), TimeoutError(SENSITIVE)):
            connection.connect.side_effect = error
            self.assertEqual(probe.probe(HOST), "tcp_unreachable")

    def test_ipv6_failure_can_fall_back_to_ipv4(self):
        connection = self.connection()
        self.dns.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 5432, 0, 0)), ADDRESS]
        connection.connect.side_effect = [OSError(SENSITIVE), None]
        self.assertEqual(probe.probe(HOST), "tcp_reachable")
        self.assertEqual(connection.connect.call_count, 2)

    def test_tcp_budget_is_bounded(self):
        self.connection()
        with patch.object(probe.time, "monotonic", side_effect=[0, 9]):
            self.assertEqual(probe.probe(HOST), "timeout")
        self.socket.assert_not_called()

    def test_subprocess_has_global_deadline_and_no_inherited_credentials(self):
        child = Mock(returncode=0, stdout="tcp_reachable\n", stderr=SENSITIVE)
        with patch.object(probe.subprocess, "run", return_value=child) as run:
            self.assertEqual(probe.bounded_probe(HOST), "tcp_reachable")
        args, kwargs = run.call_args
        self.assertNotIn(HOST, args[0])
        self.assertEqual(kwargs["input"], HOST)
        self.assertEqual(kwargs["env"], {"LANG": "C.UTF-8"})
        self.assertEqual(kwargs["timeout"], 15)
        self.assertTrue(kwargs["capture_output"])

    def test_dns_hang_and_untrusted_child_output_are_sanitized(self):
        cases = [
            (subprocess.TimeoutExpired("worker", 15, output=SENSITIVE), None, "timeout"),
            (RuntimeError(SENSITIVE), None, "internal_error"),
            (None, Mock(returncode=0, stdout=SENSITIVE), "internal_error"),
            (None, Mock(returncode=1, stdout="tcp_reachable"), "internal_error"),
        ]
        for error, child, expected in cases:
            with patch.object(probe.subprocess, "run", side_effect=error, return_value=child):
                self.assertEqual(probe.bounded_probe(HOST), expected)

    def test_public_report_contains_only_fixed_fields_and_codes(self):
        for result in probe.RESULTS:
            with patch.object(probe, "bounded_probe", return_value=result), contextlib.redirect_stdout(io.StringIO()) as output:
                code = probe.main()
            report = json.loads(output.getvalue())
            self.assertEqual(set(report), {"schema_version", "result", "port", "application_bytes_sent", "database_login_attempted"})
            self.assertEqual(report["application_bytes_sent"], 0)
            self.assertFalse(report["database_login_attempted"])
            self.assertEqual(code, 0 if result == "tcp_reachable" else 1)
            self.assertNotIn(HOST, output.getvalue())
            self.assertNotIn(SENSITIVE, output.getvalue())

    def test_actual_entrypoint_with_missing_host_fails_without_network(self):
        child = subprocess.run([os.sys.executable, str(SCRIPT)], env={"LANG": "C.UTF-8"}, capture_output=True, text=True, timeout=3)
        self.assertEqual(child.returncode, 1)
        self.assertEqual(json.loads(child.stdout)["result"], "invalid_configuration")
        self.assertEqual(child.stderr, "")


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # BaseLoader preserves the YAML key `on` (YAML 1.1 otherwise treats it as bool).
        cls.manual = yaml.load((ROOT / ".github/workflows/recovery-mvp-neon-connectivity.yml").read_text(), Loader=yaml.BaseLoader)
        cls.ci = yaml.load((ROOT / ".github/workflows/recovery-mvp-neon-connectivity-ci.yml").read_text(), Loader=yaml.BaseLoader)

    def test_live_probe_is_dispatch_only_and_needs_reviewed_sha(self):
        self.assertEqual(set(self.manual["on"]), {"workflow_dispatch"})
        fields = self.manual["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(set(fields), {"reviewed_sha"})
        self.assertEqual(fields["reviewed_sha"]["required"], "true")
        job = self.manual["jobs"]["diagnostic"]
        self.assertEqual(job["environment"], "centerway-gate1-diagnostic")
        self.assertEqual(job["timeout-minutes"], "2")
        self.assertEqual(job["steps"][0]["env"], {"REVIEWED_SHA": "${{ inputs.reviewed_sha }}"})
        self.assertIn('"$REVIEWED_SHA" != "$GITHUB_SHA"', job["steps"][0]["run"])
        self.assertEqual(job["steps"][-1]["env"], {"CENTERWAY_NEON_DIAGNOSTIC_HOST": "${{ secrets.CENTERWAY_NEON_DIAGNOSTIC_HOST }}"})

    def test_ci_never_receives_secrets_or_runs_the_probe(self):
        self.assertEqual(set(self.ci["on"]), {"pull_request"})
        raw = json.dumps(self.ci)
        self.assertNotIn("secrets.", raw)
        self.assertNotIn("environment", self.ci["jobs"]["validate"])
        commands = [step["run"] for step in self.ci["jobs"]["validate"]["steps"] if "run" in step]
        self.assertTrue(any("unittest discover" in command for command in commands))
        self.assertFalse(any("python3 .github/scripts/neon_connectivity.py" in command for command in commands))

    def test_both_workflows_are_read_only_and_checkout_has_no_persisted_token(self):
        for workflow in (self.manual, self.ci):
            self.assertEqual(workflow["permissions"], {"contents": "read"})
            for job in workflow["jobs"].values():
                for step in job["steps"]:
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")
                    if step.get("uses", "").startswith("actions/checkout@"):
                        self.assertEqual(step["with"]["persist-credentials"], "false")
                    self.assertNotIn("upload-artifact", step.get("uses", ""))


if __name__ == "__main__":
    unittest.main()
