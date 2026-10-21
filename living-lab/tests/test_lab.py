import base64
import concurrent.futures
import copy
import json
import sqlite3
import subprocess
import sys
import os
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from lab.config import load
from lab.emitter import claim, retry_after, send_once
from lab.engine import SCENARIOS, enqueue, iso, tick
from lab.imports import comparisons, receipts
from lab.store import connect, initialize
from lab.web import make_server, report
from receiver import Receiver

ROOT = Path(__file__).resolve().parents[1]


class LabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = json.loads((ROOT / "config.example.json").read_text())
        self.cfg.update(
            mode="controlled",
            state_dir=str(self.root / "state"),
            admin_password_file=str(self.root / "admin"),
        )
        (self.root / "admin").write_text("test-dashboard-password-only-207b")
        tenants = {}
        for i, c in enumerate(self.cfg["companies"]):
            c["credential_file"] = str(self.root / (c["id"] + ".secret"))
            c["send_enabled"] = True
            secret = (
                "cw_ingest_v1_"
                + str(uuid5(NAMESPACE_URL, c["id"]))
                + "."
                + str(i + 1) * 64
            )
            Path(c["credential_file"]).write_text(secret)
            tenants[c["id"]] = dict(
                secret=secret, profile_id=c["profile_id"], source=c["source"]
            )
        self.receiver = Receiver(self.root / "receiver.sqlite", tenants)
        for c in self.cfg["companies"]:
            c["endpoint"] = self.receiver.endpoint
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(self.cfg))
        self.cfg = load(self.config)
        self.a, self.b = self.cfg["companies"]
        self.paths = {c["id"]: initialize(self.cfg, c) for c in self.cfg["companies"]}
        self.db = connect(self.paths["atlas"])
        self.now = 1_000_020.0

    def tearDown(self):
        self.db.close()
        self.receiver.close()
        self.tmp.cleanup()

    def prepare(self):
        tick(self.db, self.cfg, self.a, self.now)
        # Multiple bounded pages, never one giant unbounded payload.
        for _ in range(80):
            if not enqueue(self.db, self.cfg, self.a, self.now):
                break

    def flush(self, now=None):
        now = self.now if now is None else now
        for i in range(80):
            result = send_once(self.db, self.cfg, self.a, now + i * 4)
            if result in ("idle_or_limited", "simulated_integration_outage"):
                break

    def document(self, row):
        return {
            "company": "atlas",
            "receipts": [
                {
                    "measurement_key": row["id"],
                    "observation_id": str(uuid5(NAMESPACE_URL, "atlas" + row["id"])),
                    "profile_id": self.a["profile_id"],
                    "source": self.a["source"],
                    "subject_external_ref": row["client"],
                    "indicator_key": row["indicator"],
                    "observed_at": iso(row["observed_at"]),
                    "value_numeric": row["value"],
                }
            ],
        }

    def test_reproducible_seed_and_restart_idempotence(self):
        self.prepare()
        first = [
            tuple(r)
            for r in self.db.execute("SELECT id,value FROM measurements ORDER BY id")
        ]
        self.assertEqual(0, tick(self.db, self.cfg, self.a, self.now))
        self.db.close()
        self.db = connect(self.paths["atlas"])
        self.assertEqual(0, tick(self.db, self.cfg, self.a, self.now))
        other = dict(self.cfg, state_dir=str(self.root / "replica"))
        db = connect(initialize(other, self.a))
        tick(db, other, self.a, self.now)
        self.assertEqual(
            first,
            [
                tuple(r)
                for r in db.execute("SELECT id,value FROM measurements ORDER BY id")
            ],
        )
        db.close()
        self.assertEqual(
            set(SCENARIOS),
            {r[0] for r in self.db.execute("SELECT cohort FROM clients")},
        )

    def test_catchup_is_bounded_explicit_history_without_future(self):
        tick(self.db, self.cfg, self.a, self.now)
        tick(self.db, self.cfg, self.a, self.now + 6000)
        self.assertEqual(
            31, self.db.execute("SELECT count(*) FROM ticks").fetchone()[0]
        )
        self.assertEqual(
            30,
            self.db.execute(
                "SELECT count(*) FROM ticks WHERE provenance='synthetic_history'"
            ).fetchone()[0],
        )
        self.assertLessEqual(
            self.db.execute("SELECT max(observed_at) FROM measurements").fetchone()[0],
            self.now + 6000,
        )
        tick(self.db, self.cfg, self.a, self.now + 6000)
        self.assertEqual(
            61, self.db.execute("SELECT count(*) FROM ticks").fetchone()[0]
        )

    def test_scenarios_missing_late_activity_divergence_and_causes(self):
        for n in range(45):
            tick(self.db, self.cfg, self.a, self.now + n * 60)
        count = lambda suffix: self.db.execute(
            "SELECT count(*) FROM measurements WHERE client=? AND indicator=?",
            ("atlas-" + suffix, "cycle_minutes"),
        ).fetchone()[0]
        self.assertLess(count("006"), count("001"))
        self.assertLess(count("010"), count("001"))
        self.assertGreater(
            self.db.execute(
                "SELECT count(*) FROM measurements WHERE available_at>observed_at"
            ).fetchone()[0],
            0,
        )
        vals = lambda ref, key: [
            float(r[0])
            for r in self.db.execute(
                "SELECT value FROM measurements WHERE client=? AND indicator=? ORDER BY observed_at",
                (ref, key),
            )
        ]
        self.assertGreater(
            vals("atlas-003", "cycle_minutes")[-1],
            vals("atlas-003", "cycle_minutes")[0],
        )
        self.assertLess(
            vals("atlas-002", "cycle_minutes")[-1],
            vals("atlas-002", "cycle_minutes")[0],
        )
        self.assertLess(
            vals("atlas-009", "delivery_pct")[-1], vals("atlas-009", "delivery_pct")[0]
        )
        truths = [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT truth FROM events WHERE client='atlas-012'"
            )
        ]
        self.assertTrue(all(t["cause"] is None for t in truths))

    def test_wire_allowlist_coverage_and_budget(self):
        self.prepare()
        for row in self.db.execute("SELECT payload FROM outbox"):
            p = json.loads(row[0])
            self.assertEqual({"profile_id", "source", "coverage", "rows"}, set(p))
            self.assertLess(len(row[0].encode()), 1_800_000)
            self.assertLessEqual(len(p["rows"]), 1000)
            for m in p["rows"]:
                self.assertEqual(
                    {
                        "line",
                        "subject_external_ref",
                        "indicator_key",
                        "observed_at",
                        "value_numeric",
                        "unit",
                        "idempotency_key",
                    },
                    set(m),
                )
                self.assertLess(
                    datetime.fromisoformat(m["observed_at"]),
                    datetime.fromisoformat(p["coverage"]["end"]),
                )
                self.assertGreaterEqual(
                    datetime.fromisoformat(m["observed_at"]),
                    datetime.fromisoformat(p["coverage"]["start"]),
                )
            self.assertNotIn("scenario", row[0])
            self.assertNotIn("cause", row[0])
            self.assertNotIn("expected", row[0])

    def test_commit_then_transport_loss_safe_replay(self):
        self.prepare()
        self.receiver.faults["atlas"] = ["drop_after_commit"]
        before = dict(
            self.db.execute(
                "SELECT * FROM outbox ORDER BY due_at,created_at,id LIMIT 1"
            ).fetchone()
        )
        self.assertEqual(
            "transport_outcome_unknown", send_once(self.db, self.cfg, self.a, self.now)
        )
        remote = self.receiver.count("atlas")
        self.assertGreater(remote, 0)
        self.db.execute(
            "UPDATE outbox SET due_at=? WHERE id<>?", (self.now + 1000, before["id"])
        )
        self.assertEqual(
            "completed", send_once(self.db, self.cfg, self.a, self.now + 20)
        )
        self.assertEqual(remote, self.receiver.count("atlas"))
        requests = self.receiver.requests[-2:]
        self.assertEqual(requests[0], requests[1])
        after = self.db.execute(
            "SELECT * FROM outbox WHERE id=?", (before["id"],)
        ).fetchone()
        self.assertEqual("sent", after["state"])
        self.assertEqual(before["payload"], after["payload"])

    def test_429_honors_retry_after_and_identity(self):
        self.prepare()
        self.receiver.faults["atlas"] = ["429"]
        self.assertEqual("rate_limited", send_once(self.db, self.cfg, self.a, self.now))
        attempt = self.db.execute("SELECT batch_id FROM attempts").fetchone()[0]
        due = self.db.execute(
            "SELECT due_at FROM outbox WHERE id=?", (attempt,)
        ).fetchone()[0]
        self.assertGreaterEqual(due, self.now + 120)
        self.assertEqual(120, retry_after("120", self.now))
        self.assertEqual(60, retry_after("nan", self.now))

    def test_permanent_error_blocked_and_redirect_never_followed(self):
        for status in ("401", "409", "413", "422", "307"):
            with self.subTest(status=status):
                self.db.execute("DELETE FROM attempts")
                self.db.execute("UPDATE outbox SET state='pending',due_at=0")
                if not self.db.execute("SELECT 1 FROM outbox").fetchone():
                    self.prepare()
                self.receiver.faults["atlas"] = [status]
                self.assertEqual(
                    "http_" + status, send_once(self.db, self.cfg, self.a, self.now)
                )
                self.assertEqual(
                    1,
                    self.db.execute(
                        "SELECT count(*) FROM outbox WHERE state='blocked'"
                    ).fetchone()[0],
                )

    def test_malformed_success_is_not_acknowledged(self):
        self.prepare()
        self.receiver.faults["atlas"] = ["bad_success"]
        self.assertEqual(
            "ambiguous_response", send_once(self.db, self.cfg, self.a, self.now)
        )
        self.assertEqual(
            0,
            self.db.execute(
                "SELECT count(*) FROM outbox WHERE state='sent'"
            ).fetchone()[0],
        )

    def test_durable_lease_recovers_without_new_uuid(self):
        self.prepare()
        first = claim(self.db, self.now)
        self.assertIsNotNone(first)
        self.db.close()
        self.db = connect(self.paths["atlas"])
        item = claim(self.db, self.now + 181)
        # Other equal-due pages may precede expired item; all identities remain stable.
        self.assertIsNotNone(item)
        self.assertEqual(
            "lease_expired_outcome_unknown",
            self.db.execute(
                "SELECT code FROM attempts WHERE id=?", (first[2],)
            ).fetchone()[0],
        )
        self.assertEqual(
            first[0]["payload"],
            self.db.execute(
                "SELECT payload FROM outbox WHERE id=?", (first[0]["id"],)
            ).fetchone()[0],
        )

    def test_concurrent_claims_and_persistent_quota(self):
        self.prepare()
        # Add valid tiny-batch copies with stable separate UUIDs only for claim testing.
        row = self.db.execute("SELECT * FROM outbox LIMIT 1").fetchone()
        for n in range(35):
            self.db.execute(
                "INSERT INTO outbox VALUES(?,?,?,'pending',?,?,NULL,NULL,0,NULL)",
                (
                    str(uuid5(NAMESPACE_URL, str(n))),
                    row["payload"],
                    row["payload_hash"],
                    self.now,
                    self.now,
                ),
            )

        def worker(_):
            db = connect(self.paths["atlas"])
            try:
                return claim(db, self.now)
            finally:
                db.close()

        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            items = list(pool.map(worker, range(35)))
        claimed = [r[0]["id"] for r in items if r]
        self.assertEqual(10, len(claimed))
        self.assertEqual(10, len(set(claimed)))
        self.db.close()
        self.db = connect(self.paths["atlas"])
        self.assertIsNone(claim(self.db, self.now + 1))
        self.assertIsNotNone(claim(self.db, self.now + 61))

    def test_backpressure_does_not_deadlock_delivery(self):
        from lab.runtime import cycle

        self.prepare()
        with (
            patch("lab.runtime.tick", side_effect=RuntimeError("capacity")),
            patch("lab.runtime.enqueue", side_effect=RuntimeError("full")),
            patch("lab.runtime.send_once", return_value="completed") as sender,
        ):
            errors = cycle(self.db, self.cfg, self.a)
        self.assertEqual(["generation_failed", "batching_failed"], errors)
        sender.assert_called_once()
        self.assertEqual(
            2, self.db.execute("SELECT count(*) FROM technical_errors").fetchone()[0]
        )

    def test_offline_mode_and_disabled_send_have_no_http(self):
        self.prepare()
        cfg = dict(self.cfg, mode="offline")
        self.assertEqual("disabled", send_once(self.db, cfg, self.a, self.now))
        self.assertEqual(
            "disabled",
            send_once(self.db, self.cfg, dict(self.a, send_enabled=False), self.now),
        )
        self.assertEqual([], self.receiver.requests)

    def test_company_failure_isolated_and_independent_secrets(self):
        self.prepare()
        Path(self.b["credential_file"]).unlink()
        self.assertEqual("completed", send_once(self.db, self.cfg, self.a, self.now))
        other = connect(self.paths["beacon"])
        tick(other, self.cfg, self.b, self.now)
        enqueue(other, self.cfg, self.b, self.now)
        with self.assertRaises(OSError):
            send_once(other, self.cfg, self.b, self.now)
        self.assertGreater(self.receiver.count("atlas"), 0)
        self.assertEqual(0, self.receiver.count("beacon"))
        other.close()
        Path(self.b["credential_file"]).write_text(
            Path(self.a["credential_file"]).read_text()
        )
        with self.assertRaisesRegex(ValueError, "independent"):
            send_once(self.db, self.cfg, self.a, self.now + 5)

    def test_receipts_unlock_correction_preserve_original(self):
        self.prepare()
        self.flush()
        original = self.db.execute(
            "SELECT p.* FROM measurements p JOIN measurements c ON c.corrects=p.id JOIN outbox b ON b.id=p.batch_id WHERE b.state='sent' LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(original)
        self.assertIsNone(
            self.db.execute(
                "SELECT batch_id FROM measurements WHERE corrects=?", (original["id"],)
            ).fetchone()[0]
        )
        receipts(self.db, self.a, self.document(original), self.now + 60)
        equivalent = self.document(original)
        equivalent["receipts"][0]["observed_at"] = equivalent["receipts"][0][
            "observed_at"
        ].replace("Z", "+00:00")
        equivalent["receipts"][0]["value_numeric"] = float(original["value"])
        equivalent["receipts"][0]["observation_id"] = equivalent["receipts"][0][
            "observation_id"
        ].upper()
        receipts(self.db, self.a, equivalent, self.now + 61)
        changed = self.document(original)
        changed["receipts"][0]["value_numeric"] = "999999"
        with self.assertRaisesRegex(ValueError, "receipt_payload_mismatch"):
            receipts(self.db, self.a, changed, self.now + 62)
        enqueue(self.db, self.cfg, self.a, self.now + 180)
        correction = self.db.execute(
            "SELECT * FROM measurements WHERE corrects=?", (original["id"],)
        ).fetchone()
        self.assertIsNotNone(correction["batch_id"])
        payload = json.loads(
            self.db.execute(
                "SELECT payload FROM outbox WHERE id=?", (correction["batch_id"],)
            ).fetchone()[0]
        )
        row = next(
            r for r in payload["rows"] if r["idempotency_key"] == correction["id"]
        )
        self.assertEqual(
            self.document(original)["receipts"][0]["observation_id"],
            row["corrects_observation_id"],
        )
        self.assertEqual(
            original["value"],
            self.db.execute(
                "SELECT value FROM measurements WHERE id=?", (original["id"],)
            ).fetchone()[0],
        )
        bad = self.document(original)
        bad["company"] = "beacon"
        with self.assertRaises(ValueError):
            receipts(self.db, self.a, bad, self.now + 181)

    def test_authorized_comparisons_are_append_only_and_join_private_facts(self):
        self.prepare()
        doc = {
            "company": "atlas",
            "evaluations": [
                {
                    "external_id": "evaluation-1",
                    "client": "atlas-001",
                    "indicator": "cycle_minutes",
                    "observed_until": self.now,
                    "actual_result": "inconclusive",
                    "evidence_ref": "authorized-export:one",
                }
            ],
        }
        comparisons(self.db, self.a, doc, self.now)
        comparisons(self.db, self.a, doc, self.now)
        self.assertEqual(
            1, self.db.execute("SELECT count(*) FROM comparisons").fetchone()[0]
        )
        item = report(self.paths["atlas"])["comparisons"][0]
        self.assertGreater(len(item["simulator_measurements"]), 0)
        self.assertGreater(len(item["private_events"]), 0)
        doc["evaluations"][0]["actual_result"] = "achieved"
        with self.assertRaises(ValueError):
            comparisons(self.db, self.a, doc, self.now)

    def test_real_daemon_survives_terminal_independent_restart_and_peer_failures(self):
        # Actual wall-clock ticks and a separate OS process; no clock patch.
        self.cfg["interval_seconds"] = 10
        self.cfg["state_dir"] = str(self.root / "daemon")
        self.config.write_text(json.dumps(self.cfg))
        self.receiver.faults["beacon"] = ["401"] * 100
        process = None

        def start():
            return subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lab",
                    "--config",
                    str(self.config),
                    "serve",
                    "--port",
                    "0",
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        try:
            process = start()
            deadline = time.monotonic() + 25
            while self.receiver.count("atlas") == 0 and time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail("daemon exited before serving")
                time.sleep(0.2)
            self.assertGreater(self.receiver.count("atlas"), 0)
            before = self.receiver.count("atlas")
            deadline = time.monotonic() + 25
            while (
                self.receiver.count("atlas") <= before and time.monotonic() < deadline
            ):
                time.sleep(0.2)
            self.assertGreater(self.receiver.count("atlas"), before)
            self.assertEqual(0, self.receiver.count("beacon"))
            process.terminate()
            process.wait(timeout=45)
            self.assertEqual(0, process.returncode)
            process.stderr.close()
            first = self.receiver.count("atlas")
            self.receiver.faults["beacon"] = []
            process = start()
            deadline = time.monotonic() + 65
            while self.receiver.count("beacon") == 0 and time.monotonic() < deadline:
                time.sleep(0.2)
            self.assertGreater(self.receiver.count("beacon"), 0)
            self.assertGreaterEqual(self.receiver.count("atlas"), first)
            for request in self.receiver.requests:
                for row in request["payload"]["rows"]:
                    self.assertLessEqual(
                        datetime.fromisoformat(row["observed_at"]).timestamp(),
                        time.time(),
                    )
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=45)
                if process.stderr:
                    process.stderr.close()

    def test_https_certificate_verification_and_trusted_controlled_receiver(self):
        cert = self.root / "ca.pem"
        key = self.root / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-subj",
                "/CN=127.0.0.1",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        identities = self.receiver.companies
        self.receiver.close()
        self.receiver = Receiver(
            self.root / "tls-receiver.sqlite", identities, tls=context
        )
        self.cfg.update(mode="live", state_dir=str(self.root / "tls-state"))
        for c in self.cfg["companies"]:
            c["endpoint"] = self.receiver.endpoint
        self.config.write_text(json.dumps(self.cfg))
        load(self.config)
        self.db.close()
        self.paths = {c["id"]: initialize(self.cfg, c) for c in self.cfg["companies"]}
        self.db = connect(self.paths["atlas"])
        self.prepare()
        with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
            self.assertEqual(
                "transport_outcome_unknown",
                send_once(self.db, self.cfg, self.a, self.now),
            )
            self.assertEqual(0, self.receiver.count("atlas"))
            with patch.dict(os.environ, {"SSL_CERT_FILE": str(cert)}):
                self.assertEqual(
                    "completed", send_once(self.db, self.cfg, self.a, self.now + 20)
                )
        self.assertGreater(self.receiver.count("atlas"), 0)

    def test_consistent_backup_restores_durable_outbox_and_ticks(self):
        self.prepare()
        target = self.root / "backup.sqlite3"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "lab",
                "--config",
                str(self.config),
                "backup",
                "--company",
                "atlas",
                "--file",
                str(target),
            ],
            cwd=ROOT,
            check=True,
        )
        with sqlite3.connect(target) as restored:
            self.assertEqual(
                "ok", restored.execute("PRAGMA integrity_check").fetchone()[0]
            )
            self.assertEqual(
                self.db.execute("SELECT count(*) FROM ticks").fetchone()[0],
                restored.execute("SELECT count(*) FROM ticks").fetchone()[0],
            )
            self.assertEqual(
                [
                    tuple(r)
                    for r in self.db.execute(
                        "SELECT id,payload,payload_hash FROM outbox ORDER BY id"
                    )
                ],
                restored.execute(
                    "SELECT id,payload,payload_hash FROM outbox ORDER BY id"
                ).fetchall(),
            )
        self.assertEqual(0o600, target.stat().st_mode & 0o777)

    def test_state_binding_cannot_retarget_existing_batches(self):
        changed = dict(self.a, profile_id=str(uuid5(NAMESPACE_URL, "changed")))
        with self.assertRaisesRegex(ValueError, "binding_changed"):
            initialize(self.cfg, changed)

    def test_config_rejects_non_https_and_wrong_controlled_host(self):
        for mode, url in [
            ("live", "http://example.org/functions/v1/ingest-v1/observations"),
            ("controlled", "http://localhost/functions/v1/ingest-v1/observations"),
            ("controlled", "http://127.0.0.1/functions/v1/ingest-v1/observations?q=x"),
        ]:
            cfg = copy.deepcopy(self.cfg)
            cfg["mode"] = mode
            cfg["companies"][0]["endpoint"] = url
            self.config.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                load(self.config)

    def test_private_panel_auth_csrf_pause_resume_persistent(self):
        self.prepare()
        server = make_server(self.cfg, self.paths, {}, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:" + str(server.server_port)
        auth = (
            "Basic "
            + base64.b64encode(
                b"lab-operator:test-dashboard-password-only-207b"
            ).decode()
        )

        def request(path, headers=None, data=None):
            req = urllib.request.Request(url + path, headers=headers or {}, data=data)
            try:
                return urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                return e

        try:
            with request("/api/state") as r:
                self.assertEqual(401, r.status)
            with request("/", {"Authorization": auth}) as r:
                page = r.read().decode()
                token = page.split("const csrf='")[1].split("'")[0]
            data = json.dumps({"company": "atlas", "paused": True}).encode()
            with request("/api/control", {"Authorization": auth}, data) as r:
                self.assertEqual(403, r.status)
            with request(
                "/api/control", {"Authorization": auth, "X-Lab-CSRF": token}, data
            ) as r:
                self.assertEqual(200, r.status)
            self.assertEqual(0, tick(self.db, self.cfg, self.a, self.now + 60))
            with request("/api/state", {"Authorization": auth}) as r:
                output = r.read().decode()
                self.assertNotIn(Path(self.a["credential_file"]).read_text(), output)
                self.assertIn("scenario", output)
            self.db.close()
            self.db = connect(self.paths["atlas"])
            self.assertEqual(
                1, self.db.execute("SELECT paused FROM controls").fetchone()[0]
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
