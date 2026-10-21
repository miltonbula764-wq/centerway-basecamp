"""Seeded SaaS facts. Private causes/scenarios never participate in the wire serializer."""

import hashlib
import json
import math
import random
from datetime import datetime, timezone
from uuid import UUID, uuid5

from .config import INDICATORS
from .store import event, transaction

SCENARIOS = (
    "normal",
    "improvement",
    "gradual_deterioration",
    "sudden_deterioration",
    "oscillation",
    "insufficient",
    "late",
    "correction",
    "independent",
    "activity",
    "integration_outage",
    "unknown_cause",
)
NAMESPACE = UUID("f32cc919-4bcb-40ef-b0f1-9ad477443e88")
MAX_UNBATCHED = 100000


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def identity(company, text):
    return str(
        uuid5(NAMESPACE, company["id"] + ":" + str(company["seed"]) + ":" + text)
    )


def rng_for(company, slot, client=""):
    return random.Random(
        hashlib.sha256(f"{company['seed']}:{slot}:{client}".encode()).digest()
    )


def tick(db, cfg, company, now, historical=False):
    interval = cfg["interval_seconds"]
    current = int(now // interval)
    with transaction(db):
        if db.execute("SELECT paused FROM controls WHERE id=1").fetchone()[0]:
            return 0
        if (
            db.execute(
                "SELECT count(*) FROM measurements WHERE batch_id IS NULL"
            ).fetchone()[0]
            >= MAX_UNBATCHED
        ):
            raise RuntimeError("unbatched_capacity_reached")
        for i in range(company["clients"]):
            db.execute(
                "INSERT OR IGNORE INTO clients(ref,cohort) VALUES(?,?)",
                (f"{company['id']}-{i + 1:03}", SCENARIOS[i % len(SCENARIOS)]),
            )
        previous = db.execute("SELECT max(slot) FROM ticks").fetchone()[0]
        if previous is not None and current <= previous:
            return 0
        # Bounded catch-up; missing slots are generated later, never silently skipped.
        start = current if previous is None else previous + 1
        resumed = db.execute(
            "SELECT value FROM meta WHERE key='resume_slot'"
        ).fetchone()
        if resumed and int(resumed[0]) > start:
            event(
                db,
                None,
                None,
                "paused_gap",
                {"from_slot": start, "until_slot": int(resumed[0])},
            )
            start = int(resumed[0])
        slots = range(start, min(current + 1, start + 30))
        made = 0
        epoch = db.execute("SELECT value FROM meta WHERE key='epoch'").fetchone()
        origin = int(epoch[0]) if epoch else start
        db.execute("INSERT OR IGNORE INTO meta VALUES('epoch',?)", (str(origin),))
        for slot in slots:
            provenance = (
                "synthetic_history" if historical or slot != current else "realtime"
            )
            at = slot * interval
            elapsed = slot - origin
            db.execute("INSERT INTO ticks VALUES(?,?,?)", (slot, now, provenance))
            for i in range(company["clients"]):
                ref = f"{company['id']}-{i + 1:03}"
                scenario = SCENARIOS[i % len(SCENARIOS)]
                rng = rng_for(company, slot, ref)
                active = scenario != "activity" or elapsed % 12 < 8
                db.execute(
                    "UPDATE clients SET active=? WHERE ref=?", (int(active), ref)
                )
                missing = scenario == "insufficient" and rng.random() < 0.8
                event(
                    db,
                    slot,
                    ref,
                    "operation",
                    {
                        "scenario": scenario,
                        "active": active,
                        "missing": missing,
                        "cause": None
                        if scenario == "unknown_cause"
                        else {
                            "improvement": "training rollout",
                            "gradual_deterioration": "growing backlog",
                            "sudden_deterioration": "worker capacity loss",
                            "oscillation": "temporary load peak",
                            "insufficient": "sensor unavailable",
                            "late": "delayed export",
                            "correction": "sensor calibration error",
                            "activity": "seasonal customer pause",
                            "integration_outage": "temporary connector interruption",
                        }.get(scenario, "synthetic operating conditions"),
                        "provenance": provenance,
                        "observed_at": iso(at),
                        "observed_at_epoch": at,
                    },
                )
                if not active or missing:
                    continue  # Unknown data stays absent. Never impute a value.
                base = 85 + rng.uniform(-3, 3)
                if scenario == "improvement":
                    base = max(20, 100 - elapsed * 0.8)
                elif scenario == "gradual_deterioration":
                    base = min(240, 65 + elapsed * 0.9)
                elif scenario == "sudden_deterioration":
                    base = 60 if elapsed % 24 < 12 else 160
                elif scenario == "oscillation":
                    base = 135 if elapsed % 8 == 3 else 65
                elif scenario == "unknown_cause":
                    base = 90 + math.sin(elapsed / 3) * 20
                elif scenario == "independent":
                    base = max(25, 95 - elapsed * 0.3)
                delay = rng.randint(2, 6) * interval if scenario == "late" else 0
                # Variable volumes: deterministic omissions of second indicator.
                for key in INDICATORS:
                    if key == "delivery_pct" and rng.random() < 0.15:
                        continue
                    value = base if key == "cycle_minutes" else rng.uniform(92, 99)
                    if scenario == "independent" and key == "delivery_pct":
                        value = max(30, 95 - elapsed * 0.6)
                    mid = identity(company, f"{slot}:{ref}:{key}")
                    db.execute(
                        "INSERT INTO measurements(id,slot,client,indicator,observed_at,value,available_at,provenance) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            mid,
                            slot,
                            ref,
                            key,
                            at,
                            f"{value:.3f}",
                            at + delay,
                            provenance,
                        ),
                    )
                    made += 1
                    if (
                        scenario == "correction"
                        and key == "cycle_minutes"
                        and elapsed % 6 == 0
                    ):
                        cid = identity(company, mid + ":correction")
                        db.execute(
                            "INSERT INTO measurements(id,slot,client,indicator,observed_at,value,available_at,provenance,corrects) VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                cid,
                                slot,
                                ref,
                                key,
                                at,
                                f"{max(1, value - 12):.3f}",
                                at + interval * 2,
                                provenance,
                                mid,
                            ),
                        )
                        event(
                            db,
                            slot,
                            ref,
                            "correction_pending_receipt",
                            {"measurement_id": cid, "corrects": mid},
                        )
                        made += 1
        return made


def enqueue(db, cfg, company, now):
    """Allowlist-only C01 serializer. Bodies and UUIDs become immutable once queued."""
    with transaction(db):
        if db.execute("SELECT paused FROM controls WHERE id=1").fetchone()[0]:
            return 0
        if (
            db.execute("SELECT count(*) FROM outbox WHERE state <> 'sent'").fetchone()[
                0
            ]
            >= 5000
        ):
            raise RuntimeError("outbox_capacity_reached")
        # Per-company/time-bucket reproducible irregular batch sizes.
        rng = rng_for(company, int(now // cfg["interval_seconds"]), "batch")
        limit = rng.choice([1, 7, 31, 127, 500, 1000])
        rows = db.execute(
            """SELECT m.*,p.observation_id AS corrects_remote FROM measurements m
            LEFT JOIN measurements p ON p.id=m.corrects
            WHERE m.batch_id IS NULL AND m.available_at<=? AND m.observed_at<=?
              AND (m.corrects IS NULL OR (p.observation_id IS NOT NULL AND
                   EXISTS(SELECT 1 FROM outbox b WHERE b.id=p.batch_id AND b.state='sent')))
            ORDER BY m.observed_at,m.id LIMIT ?""",
            (now, now, limit),
        ).fetchall()
        if not rows:
            return 0
        body_rows = []
        for m in rows:
            row = {
                "line": len(body_rows) + 1,
                "subject_external_ref": m["client"],
                "indicator_key": m["indicator"],
                "observed_at": iso(m["observed_at"]),
                "value_numeric": m["value"],
                "unit": INDICATORS[m["indicator"]],
                "idempotency_key": m["id"],
            }
            if m["corrects_remote"]:
                row["corrects_observation_id"] = m["corrects_remote"]
            body_rows.append(row)
        payload = {
            "profile_id": company["profile_id"],
            "source": company["source"],
            "coverage": {
                "start": iso(min(m["observed_at"] for m in rows)),
                "end": iso(max(m["observed_at"] for m in rows) + 0.001),
                "declared": True,
            },
            "rows": body_rows,
        }
        # Default JSON separators conservatively include JSONB-style whitespace.
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
        if len(body.encode()) > 1_800_000:
            raise RuntimeError("batch_byte_budget_exceeded")
        bid = identity(company, "batch:" + ":".join(m["id"] for m in rows))
        db.execute(
            "INSERT INTO outbox VALUES(?,?,?,'pending',?,?,NULL,NULL,0,NULL)",
            (bid, body, hashlib.sha256(body.encode()).hexdigest(), now, now),
        )
        db.executemany(
            "UPDATE measurements SET batch_id=? WHERE id=?",
            [(bid, m["id"]) for m in rows],
        )
        return len(rows)
