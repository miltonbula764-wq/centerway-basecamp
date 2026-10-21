"""One bounded cycle; failures/backpressure never prevent draining existing work."""

import time
from .engine import enqueue, tick
from .emitter import send_once
from .store import event, transaction


def cycle(db, cfg, company):
    errors = []
    result = None
    for stage, operation in (
        ("generation", lambda: tick(db, cfg, company, time.time())),
        ("batching", lambda: enqueue(db, cfg, company, time.time())),
        ("delivery", lambda: send_once(db, cfg, company)),
    ):
        try:
            result = operation()
        except Exception:
            code = stage + "_failed"
            errors.append(code)
            try:
                previous = db.execute(
                    "SELECT max(at) FROM technical_errors WHERE code=?", (code,)
                ).fetchone()[0]
                if previous is None or time.time() - previous >= 60:
                    db.execute(
                        "INSERT INTO technical_errors(at,code) VALUES(?,?)",
                        (time.time(), code),
                    )
            except Exception:
                pass  # Storage failure remains visible in process health.
    if result == "simulated_integration_outage":
        with transaction(db):
            if not db.execute("SELECT 1 FROM meta WHERE key='outage'").fetchone():
                db.execute("INSERT INTO meta VALUES('outage','active')")
                event(db, None, None, "integration_outage", {"at": time.time()})
    else:
        with transaction(db):
            if db.execute("SELECT 1 FROM meta WHERE key='outage'").fetchone():
                event(db, None, None, "integration_resumed", {"at": time.time()})
            db.execute("DELETE FROM meta WHERE key='outage'")
    db.execute(
        "INSERT OR REPLACE INTO meta VALUES('last_cycle',?)", (str(time.time()),)
    )
    db.execute(
        "INSERT OR REPLACE INTO meta VALUES('last_error',?)", (",".join(errors),)
    )
    return errors
