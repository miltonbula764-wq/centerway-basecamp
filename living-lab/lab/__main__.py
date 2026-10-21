import argparse
import json
import signal
import threading
import time
from pathlib import Path

from .config import load
from .emitter import send_once
from .engine import enqueue, tick
from .imports import comparisons, receipts
from .store import connect, initialize, transaction
from .runtime import cycle
from .web import make_server


def main():
    parser = argparse.ArgumentParser(
        description="Independent living SaaS laboratory; no hosted sends by default"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "command",
        choices=[
            "serve",
            "once",
            "export",
            "import-receipts",
            "import-comparisons",
            "retry-blocked",
            "history",
            "backup",
        ],
    )
    parser.add_argument("--company")
    parser.add_argument("--file")
    parser.add_argument("--batch")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    cfg = load(args.config)
    if args.company and args.company not in {c["id"] for c in cfg["companies"]}:
        parser.error("unknown company")
    selected = [
        c for c in cfg["companies"] if not args.company or c["id"] == args.company
    ]
    if args.command not in ("serve", "once") and len(selected) != 1:
        parser.error("--company required")
    if (
        args.command in ("import-receipts", "import-comparisons", "export", "backup")
        and not args.file
    ):
        parser.error("--file required")
    if args.command == "retry-blocked" and not args.batch:
        parser.error("--batch required")
    health = {}
    paths = {}
    for c in selected:
        try:
            paths[c["id"]] = initialize(cfg, c)
        except Exception:
            health[c["id"]] = "company_initialization_failed"
    if args.command == "serve":
        stop = threading.Event()

        def worker(company):
            while not stop.is_set():
                db = None
                try:
                    if company["id"] not in paths:
                        paths[company["id"]] = initialize(cfg, company)
                    db = connect(paths[company["id"]])
                    errors = cycle(db, cfg, company)
                    if errors:
                        health[company["id"]] = ",".join(errors)
                    else:
                        health.pop(company["id"], None)
                except Exception:
                    health[company["id"]] = (
                        "company_worker_failed_check_local_state_and_secret_mount"
                    )
                    try:
                        if db is not None:
                            previous = db.execute(
                                "SELECT max(at) FROM technical_errors"
                            ).fetchone()[0]
                            if previous is None or time.time() - previous >= 60:
                                db.execute(
                                    "INSERT INTO technical_errors(at,code) VALUES(?,?)",
                                    (time.time(), "worker_failed"),
                                )
                    except Exception:
                        pass  # Disk loss is visible in private panel health.
                finally:
                    if db is not None:
                        db.close()
                stop.wait(3)

        workers = [
            threading.Thread(target=worker, args=(c,), daemon=True) for c in selected
        ]
        view = dict(cfg, companies=selected)
        server = make_server(view, paths, health, args.bind, args.port)
        for w in workers:
            w.start()

        def shutdown(*_):
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        try:
            server.serve_forever()
        finally:
            stop.set()
            server.server_close()
            for w in workers:
                w.join(timeout=40)
        return
    for c in selected:
        if c["id"] not in paths:
            raise SystemExit("company_initialization_failed")
        db = connect(paths[c["id"]])
        try:
            if args.command == "once":
                tick(db, cfg, c, time.time())
                enqueue(db, cfg, c, time.time())
                print(c["id"], send_once(db, cfg, c))
            elif args.command in ("import-receipts", "import-comparisons"):
                doc = json.loads(Path(args.file).read_text())
                (receipts if args.command == "import-receipts" else comparisons)(
                    db, c, doc, time.time()
                )
            elif args.command == "retry-blocked":
                # Only the SAME body/UUID may be retried (e.g. credential replaced).
                with transaction(db):
                    n = db.execute(
                        "UPDATE outbox SET state='pending',due_at=? WHERE id=? AND state='blocked'",
                        (time.time(), args.batch),
                    ).rowcount
                    if n != 1:
                        raise ValueError("blocked_batch_required")
            elif args.command == "history":
                if not 1 <= args.hours <= 168:
                    raise ValueError("history_limit_1_to_168_hours")
                if (
                    db.execute("SELECT 1 FROM ticks LIMIT 1").fetchone()
                    or db.execute("SELECT paused FROM controls").fetchone()[0]
                ):
                    raise ValueError("history_requires_fresh_unpaused_company_state")
                now = time.time()
                start = int((now - args.hours * 3600) // cfg["interval_seconds"])
                # Only a laboratory cursor; all observations remain actual past times.
                with transaction(db):
                    db.execute("INSERT INTO meta VALUES('epoch',?)", (str(start),))
                    db.execute(
                        "INSERT INTO ticks VALUES(?,?,'synthetic_history')",
                        (start - 1, now),
                    )
                while db.execute("SELECT max(slot) FROM ticks").fetchone()[0] < int(
                    now // cfg["interval_seconds"]
                ):
                    tick(db, cfg, c, now, historical=True)
                print("Explicit synthetic history generated; no send performed")
            elif args.command == "backup":
                import sqlite3

                target = Path(args.file)
                with target.open("xb") as f:
                    pass
                target.chmod(0o600)
                backup = sqlite3.connect(target)
                try:
                    db.backup(backup)
                finally:
                    backup.close()
            elif args.command == "export":
                # Private backup/export: never pipe to C01. Explicit local file only.
                output = Path(args.file)
                output.mkdir(mode=0o700, parents=True, exist_ok=False)
                for table in (
                    "clients",
                    "ticks",
                    "events",
                    "measurements",
                    "outbox",
                    "attempts",
                    "comparisons",
                    "technical_errors",
                ):
                    p = output / (table + ".json")
                    p.write_text(
                        json.dumps(
                            [dict(r) for r in db.execute("SELECT * FROM " + table)],
                            indent=2,
                        )
                    )
                    p.chmod(0o600)
        finally:
            db.close()


if __name__ == "__main__":
    main()
