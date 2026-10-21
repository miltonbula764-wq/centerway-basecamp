"""Manual imports of authorized evidence. Never fetches CENTERWAY tables/RPCs."""

import math
from uuid import UUID

from .engine import event
from .store import transaction


def receipts(db, company, document, now):
    if document["company"] != company["id"]:
        raise ValueError("receipt_company_mismatch")
    with transaction(db):
        for item in document["receipts"]:
            UUID(item["observation_id"])
            row = db.execute(
                """SELECT m.*,b.state FROM measurements m JOIN outbox b ON b.id=m.batch_id
                 WHERE m.id=?""",
                (item["measurement_key"],),
            ).fetchone()
            if not row or row["state"] != "sent":
                raise ValueError("original_not_acknowledged")
            for field, expected in [
                ("subject_external_ref", row["client"]),
                ("indicator_key", row["indicator"]),
                ("source", company["source"]),
                ("profile_id", company["profile_id"]),
            ]:
                if item[field] != expected:
                    raise ValueError("receipt_identity_mismatch")
            from .engine import iso

            if (
                item["observed_at"] != iso(row["observed_at"])
                or item["value_numeric"] != row["value"]
            ):
                raise ValueError("receipt_payload_mismatch")
            if (
                row["observation_id"]
                and row["observation_id"] != item["observation_id"]
            ):
                raise ValueError("receipt_is_immutable")
            db.execute(
                "UPDATE measurements SET observation_id=? WHERE id=?",
                (item["observation_id"], row["id"]),
            )
            event(
                db,
                row["slot"],
                row["client"],
                "authorized_receipt_import",
                {"measurement": row["id"], "imported_at": now},
            )


def comparisons(db, company, document, now):
    if document["company"] != company["id"]:
        raise ValueError("comparison_company_mismatch")
    with transaction(db):
        for item in document["evaluations"]:
            if not db.execute(
                "SELECT 1 FROM clients WHERE ref=?", (item["client"],)
            ).fetchone():
                raise ValueError("unknown_client")
            if item["indicator"] not in ("cycle_minutes", "delivery_pct"):
                raise ValueError("unknown_indicator")
            if (
                not isinstance(item["observed_until"], (int, float))
                or not math.isfinite(item["observed_until"])
                or item["observed_until"] > now
            ):
                raise ValueError("invalid_comparison_cutoff")
            text = str(item["actual_result"])
            ref = str(item["evidence_ref"])
            if len(text) > 4000 or len(ref) > 2000:
                raise ValueError("comparison_too_large")
            values = (
                item["external_id"],
                item["client"],
                item["indicator"],
                item["observed_until"],
                text,
                ref,
            )
            old = db.execute(
                "SELECT external_id,client,indicator,observed_until,actual_result,evidence_ref FROM comparisons WHERE external_id=?",
                (item["external_id"],),
            ).fetchone()
            if old and tuple(old) != values:
                raise ValueError("comparison_history_is_immutable")
            db.execute(
                "INSERT OR IGNORE INTO comparisons(imported_at,external_id,client,indicator,observed_until,actual_result,evidence_ref) VALUES(?,?,?,?,?,?,?)",
                (now,) + values,
            )
