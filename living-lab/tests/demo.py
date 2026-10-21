"""Reproducible controlled demonstration. No real credentials/endpoints accepted."""

import json
import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from lab.config import load
from lab.emitter import send_once
from lab.engine import tick, enqueue, iso
from lab.imports import receipts
from lab.store import initialize, connect
from receiver import Receiver


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = json.loads(
            (Path(__file__).parents[1] / "config.example.json").read_text()
        )
        cfg.update(mode="controlled", state_dir=str(root / "state"))
        identities = {}
        for i, c in enumerate(cfg["companies"]):
            c.update(
                credential_file=str(root / (c["id"] + ".secret")), send_enabled=True
            )
            secret = (
                "cw_ingest_v1_"
                + str(uuid5(NAMESPACE_URL, c["id"]))
                + "."
                + str(i + 1) * 64
            )
            Path(c["credential_file"]).write_text(secret)
            identities[c["id"]] = dict(
                secret=secret, source=c["source"], profile_id=c["profile_id"]
            )
        receiver = Receiver(root / "receiver.sqlite", identities)
        try:
            for c in cfg["companies"]:
                c["endpoint"] = receiver.endpoint
            config = root / "config.json"
            config.write_text(json.dumps(cfg))
            cfg = load(config)
            paths = {c["id"]: initialize(cfg, c) for c in cfg["companies"]}
            dbs = {key: connect(path) for key, path in paths.items()}
            try:
                # Deliberately accelerated LAB timeline: actual past timestamps, never
                # a forged CENTERWAY/server clock. All these ticks marked as history.
                base = 1_000_020.0
                end = base + 60 * 49
                for c in cfg["companies"]:
                    db = dbs[c["id"]]
                    db.execute(
                        "INSERT INTO ticks VALUES(?,?,'synthetic_history')",
                        (int(base // 60) - 1, end),
                    )
                    db.execute(
                        "INSERT INTO meta VALUES('epoch',?)", (str(int(base // 60)),)
                    )
                    while db.execute("SELECT max(slot) FROM ticks").fetchone()[0] < int(
                        end // 60
                    ):
                        tick(db, cfg, c, end, historical=True)
                receiver.faults["atlas"] = ["drop_after_commit", "503", "429"]
                for n in range(240):
                    now = end + 60 + n * 7
                    for c in cfg["companies"]:
                        db = dbs[c["id"]]
                        enqueue(db, cfg, c, now)
                        send_once(db, cfg, c, now)
                # Mapping obtained from the controlled receiver's private test state,
                # never inferred from a C01 response nor an unauthorized CENTERWAY read.
                for c in cfg["companies"]:
                    db = dbs[c["id"]]
                    items = []
                    with sqlite3.connect(receiver.path) as remote:
                        for m in db.execute(
                            "SELECT p.* FROM measurements p JOIN outbox b ON b.id=p.batch_id WHERE b.state='sent' AND EXISTS(SELECT 1 FROM measurements x WHERE x.corrects=p.id)"
                        ):
                            remote_id = remote.execute(
                                "SELECT id FROM observations WHERE company=? AND key=?",
                                (c["id"], m["id"]),
                            ).fetchone()
                            if remote_id:
                                items.append(
                                    {
                                        "measurement_key": m["id"],
                                        "observation_id": remote_id[0],
                                        "source": c["source"],
                                        "profile_id": c["profile_id"],
                                        "subject_external_ref": m["client"],
                                        "indicator_key": m["indicator"],
                                        "observed_at": iso(m["observed_at"]),
                                        "value_numeric": m["value"],
                                    }
                                )
                    receipts(db, c, {"company": c["id"], "receipts": items}, now)
                for n in range(80):
                    now = end + 60 + 240 * 7 + n * 7
                    for c in cfg["companies"]:
                        db = dbs[c["id"]]
                        enqueue(db, cfg, c, now)
                        send_once(db, cfg, c, now)
                results = {
                    "scope": "controlled HTTP only; no CENTERWAY access",
                    "timeline": "50 accelerated synthetic historical ticks per company; no realtime claim",
                    "companies": {},
                }
                for c in cfg["companies"]:
                    db = dbs[c["id"]]
                    produced = db.execute(
                        "SELECT count(*) FROM measurements"
                    ).fetchone()[0]
                    accepted = receiver.count(c["id"])
                    sent = db.execute(
                        "SELECT count(*) FROM measurements m JOIN outbox b ON b.id=m.batch_id WHERE b.state='sent'"
                    ).fetchone()[0]
                    assert accepted == sent == produced, (
                        c["id"],
                        accepted,
                        sent,
                        produced,
                    )
                    attempts = db.execute("SELECT count(*) FROM attempts").fetchone()[0]
                    for a in db.execute("SELECT started_at FROM attempts"):
                        assert (
                            db.execute(
                                "SELECT count(*) FROM attempts WHERE started_at>? AND started_at<=?",
                                (a[0] - 60, a[0]),
                            ).fetchone()[0]
                            <= 10
                        )
                    results["companies"][c["id"]] = {
                        "clients": db.execute(
                            "SELECT count(*) FROM clients"
                        ).fetchone()[0],
                        "ticks": db.execute(
                            "SELECT count(*) FROM ticks WHERE slot>=?",
                            (int(base // 60),),
                        ).fetchone()[0],
                        "produced": produced,
                        "accepted_unique": accepted,
                        "attempts": attempts,
                        "failed_or_ambiguous_attempts": db.execute(
                            "SELECT count(*) FROM attempts WHERE code<>'completed'"
                        ).fetchone()[0],
                        "corrections": db.execute(
                            "SELECT count(*) FROM measurements WHERE corrects IS NOT NULL"
                        ).fetchone()[0],
                        "pending_batches": db.execute(
                            "SELECT count(*) FROM outbox WHERE state<>'sent'"
                        ).fetchone()[0],
                    }
                print(json.dumps(results, indent=2))
            finally:
                for db in dbs.values():
                    db.close()
        finally:
            receiver.close()


if __name__ == "__main__":
    main()
