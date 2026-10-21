"""Controlled HTTP receiver, never a CENTERWAY deployment. Synthetic secrets only."""

import json
import socket
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid5, NAMESPACE_URL


class Receiver:
    def __init__(self, path, companies, tls=None):
        self.path = path
        self.companies = companies
        self.faults = {}
        self.requests = []
        self.lock = threading.Lock()
        with sqlite3.connect(path) as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS requests(company TEXT,id TEXT,payload TEXT,response TEXT,PRIMARY KEY(company,id));
                CREATE TABLE IF NOT EXISTS observations(company TEXT,key TEXT,id TEXT,row TEXT,PRIMARY KEY(company,key));""")
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != "/functions/v1/ingest-v1/observations":
                    self.send_error(404)
                    return
                key = self.headers.get("Authorization", "").removeprefix("Bearer ")
                company = next(
                    (k for k, v in outer.companies.items() if v["secret"] == key), None
                )
                if company is None:
                    self.send_error(401)
                    return
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                operation = self.headers["Idempotency-Key"]
                with outer.lock:
                    outer.requests.append(
                        {"company": company, "id": operation, "payload": payload}
                    )
                    faults = outer.faults.get(company, [])
                    fault = faults.pop(0) if faults else None
                    if fault not in ("drop_after_commit", None):
                        status = int(fault) if fault.isdigit() else 200
                        self.respond(status, {"status": "unknown"})
                        return
                    expected = outer.companies[company]
                    if (
                        payload["profile_id"] != expected["profile_id"]
                        or payload["source"] != expected["source"]
                    ):
                        self.respond(422, {"code": "identity_mismatch"})
                        return
                    if set(payload) != {"profile_id", "source", "coverage", "rows"}:
                        self.respond(400, {"code": "unknown_fields"})
                        return
                    if (
                        len(payload["rows"]) > 1000
                        or len(json.dumps(payload).encode()) > 2_000_000
                    ):
                        self.respond(413, {"code": "limit"})
                        return
                    for row in payload["rows"]:
                        if not set(row) <= {
                            "line",
                            "subject_external_ref",
                            "indicator_key",
                            "observed_at",
                            "value_numeric",
                            "unit",
                            "idempotency_key",
                            "corrects_observation_id",
                        }:
                            self.respond(422, {"code": "private_field_leaked"})
                            return
                        if not row["subject_external_ref"].startswith(company + "-"):
                            self.respond(422, {"code": "foreign_client"})
                            return
                    canonical = json.dumps(payload, sort_keys=True)
                    with sqlite3.connect(outer.path) as db:
                        old = db.execute(
                            "SELECT payload,response FROM requests WHERE company=? AND id=?",
                            (company, operation),
                        ).fetchone()
                        if old:
                            if old[0] != canonical:
                                self.respond(409, {"code": "conflict"})
                                return
                            result = json.loads(old[1])
                        else:
                            inserted = 0
                            duplicates = 0
                            for row in payload["rows"]:
                                previous = db.execute(
                                    "SELECT row FROM observations WHERE company=? AND key=?",
                                    (company, row["idempotency_key"]),
                                ).fetchone()
                                serial = json.dumps(
                                    {k: v for k, v in row.items() if k != "line"},
                                    sort_keys=True,
                                )
                                if previous:
                                    if previous[0] != serial:
                                        self.respond(409, {"code": "row_conflict"})
                                        return
                                    duplicates += 1
                                else:
                                    db.execute(
                                        "INSERT INTO observations VALUES(?,?,?,?)",
                                        (
                                            company,
                                            row["idempotency_key"],
                                            str(
                                                uuid5(
                                                    NAMESPACE_URL,
                                                    company + row["idempotency_key"],
                                                )
                                            ),
                                            serial,
                                        ),
                                    )
                                    inserted += 1
                            result = {
                                "status": "completed",
                                "row_count": len(payload["rows"]),
                                "inserted": inserted,
                                "duplicates": duplicates,
                                "rejected": 0,
                                "errors": [],
                                "code": "completed",
                                "batch_id": operation,
                            }
                            db.execute(
                                "INSERT INTO requests VALUES(?,?,?,?)",
                                (company, operation, canonical, json.dumps(result)),
                            )
                    if fault == "drop_after_commit":
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    self.respond(200, result)

            def respond(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if status == 429:
                    self.send_header("Retry-After", "120")
                if status in (301, 302, 307, 308):
                    self.send_header(
                        "Location", "https://must-never-be-contacted.invalid/"
                    )
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.scheme = "https" if tls else "http"
        if tls:
            self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def endpoint(self):
        return (
            self.scheme
            + "://127.0.0.1:"
            + str(self.server.server_port)
            + "/functions/v1/ingest-v1/observations"
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def count(self, company):
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT count(*) FROM observations WHERE company=?", (company,)
            ).fetchone()[0]
