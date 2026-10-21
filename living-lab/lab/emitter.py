"""Durable at-least-once HTTPS emitter. No database/administration access to CENTERWAY."""

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

from .store import transaction, event


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a credential, even to another HTTPS host.


def retry_after(value, now):
    try:
        n = float(value)
        if math.isfinite(n):
            return max(1, n)
    except (TypeError, ValueError):
        pass
    try:
        return max(
            1,
            (
                parsedate_to_datetime(value) - datetime.fromtimestamp(now, timezone.utc)
            ).total_seconds(),
        )
    except (TypeError, ValueError, OverflowError):
        return 60


def integration_interrupted(db, company):
    epoch = db.execute("SELECT value FROM meta WHERE key='epoch'").fetchone()
    slot = db.execute("SELECT max(slot) FROM ticks").fetchone()[0]
    if not epoch or slot is None:
        return False
    # Offset by seed, independent company clocks. No CENTERWAY clock manipulation.
    return (slot - int(epoch[0]) + company["seed"] % 13) % 40 in (20, 21, 22)


def claim(db, now):
    with transaction(db):
        if db.execute("SELECT paused FROM controls WHERE id=1").fetchone()[0]:
            return None
        expired = db.execute(
            "SELECT id FROM outbox WHERE state='leased' AND lease_until<=?", (now,)
        ).fetchall()
        for old in expired:
            event(
                db,
                None,
                None,
                "lease_expired",
                {"batch_id": old["id"], "at": now, "outcome": "unknown"},
            )
        db.execute(
            "UPDATE attempts SET finished_at=?,code='lease_expired_outcome_unknown' WHERE finished_at IS NULL AND batch_id IN (SELECT id FROM outbox WHERE state='leased' AND lease_until<=?)",
            (now, now),
        )
        db.execute(
            "UPDATE outbox SET state='pending',lease_token=NULL,lease_until=NULL,last_code='lease_expired_outcome_unknown' WHERE state='leased' AND lease_until<=?",
            (now,),
        )
        # Reserve requests before I/O. Includes retries/unknown outcomes and survives crashes.
        if (
            db.execute(
                "SELECT count(*) FROM attempts WHERE started_at>?", (now - 60,)
            ).fetchone()[0]
            >= 10
        ):
            return None
        row = db.execute(
            "SELECT * FROM outbox WHERE state='pending' AND due_at<=? ORDER BY due_at,created_at,id LIMIT 1",
            (now,),
        ).fetchone()
        if not row:
            return None
        token = str(uuid4())
        db.execute(
            "UPDATE outbox SET state='leased',lease_until=?,lease_token=?,tries=tries+1 WHERE id=?",
            (now + 180, token, row["id"]),
        )
        aid = db.execute(
            "INSERT INTO attempts(batch_id,started_at,code) VALUES(?,?,'in_flight')",
            (row["id"], now),
        ).lastrowid
        return dict(row), token, aid


def send_once(db, cfg, company, now=None):
    supplied_clock = now is not None
    now = time.time() if now is None else now
    if cfg["mode"] == "offline" or not company["send_enabled"]:
        return "disabled"
    if integration_interrupted(db, company):
        return "simulated_integration_outage"
    # Validate both secrets before a claim, preventing accidental shared credentials.
    # Missing/bad credentials in company B must not stop company A: only check a
    # readable peer for equality; A validates its own key independently.
    own = Path(company["credential_file"]).read_text().strip()
    if not re.fullmatch(r"cw_ingest_v1_[0-9a-f-]{36}\.[0-9a-f]{64}", own):
        raise ValueError("invalid_c01_credential")
    for peer in cfg["companies"]:
        if peer["id"] == company["id"]:
            continue
        try:
            other = Path(peer["credential_file"]).read_text().strip()
        except OSError:
            continue
        if other == own:
            raise ValueError("credentials_must_be_independent")
    item = claim(db, now)
    if not item:
        return "idle_or_limited"
    row, token, aid = item
    status = None
    data = {}
    delay = 0
    code = "transport_outcome_unknown"
    state = "pending"
    try:
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["payload_hash"]:
            raise ValueError("payload_integrity")
        body = json.loads(row["payload"])
        if (
            body["profile_id"] != company["profile_id"]
            or body["source"] != company["source"]
        ):
            raise ValueError("binding_integrity")
        handlers = [NoRedirect()]
        if cfg["mode"] == "controlled":
            handlers.append(urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request(
            company["endpoint"],
            data=row["payload"].encode(),
            method="POST",
            headers={
                "Authorization": "Bearer " + own,
                "Idempotency-Key": row["id"],
                "Content-Type": "application/json",
            },
        )
        try:
            response = opener.open(req, timeout=35)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            status = response.status
            # Never log raw bodies, headers or upstream exceptions.
            raw = response.read(65537)
            if len(raw) <= 65536:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        data = parsed
                except (ValueError, UnicodeError):
                    pass
            if (
                status == 200
                and data.get("status") == "completed"
                and data.get("rejected") == 0
                and data.get("row_count") == len(body["rows"])
                and type(data.get("inserted")) is int
                and type(data.get("duplicates")) is int
                and type(data.get("row_count")) is int
                and type(data.get("rejected")) is int
                and data["inserted"] >= 0
                and data["duplicates"] >= 0
                and data["inserted"] + data["duplicates"] == len(body["rows"])
            ):
                state = "sent"
                code = "completed"
            elif status == 429:
                code = "rate_limited"
                delay = retry_after(response.headers.get("Retry-After"), now)
            elif status in (408, 425, 500, 502, 503, 504) or status == 200:
                code = "ambiguous_response" if status == 200 else "upstream_unavailable"
            else:
                state = "blocked"
                code = "http_" + str(status)
    except ValueError:
        state = "blocked"
        code = "local_payload_integrity"
    except (OSError, urllib.error.URLError, TimeoutError):
        pass
    # Deterministic bounded backoff; Retry-After is a minimum, never shortened.
    # Injected clocks exist only in deterministic controlled tests.
    finished = now if supplied_clock else time.time()
    backoff = min(3600, 2 ** min(row["tries"] + 1, 11))
    jitter = (
        int(
            hashlib.sha256((row["id"] + str(row["tries"])).encode()).hexdigest()[:4], 16
        )
        % 7
    )
    due = finished + max(delay, backoff + jitter)
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch("[0-9a-f-]{36}", request_id):
        request_id = None
    details = {}
    if isinstance(data.get("code"), str) and re.fullmatch(
        "[a-z0-9_]{1,80}", data["code"]
    ):
        details["code"] = data["code"]
    if isinstance(data.get("errors"), list):
        details["errors"] = [
            {
                "line": e.get("line"),
                "errors": [
                    v
                    for v in e.get("errors", [])
                    if isinstance(v, str) and re.fullmatch("[a-z0-9_]{1,80}", v)
                ],
            }
            for e in data["errors"][:20]
            if isinstance(e, dict)
            and isinstance(e.get("line"), int)
            and isinstance(e.get("errors"), list)
        ]
    # Status/error metadata only; private simulator facts are never in a request.
    with transaction(db):
        db.execute(
            "UPDATE attempts SET finished_at=?,http_status=?,code=?,request_id=?,inserted=?,duplicates=?,rejected=?,details=? WHERE id=?",
            (
                finished,
                status,
                code,
                request_id,
                data.get("inserted") if state == "sent" else None,
                data.get("duplicates") if state == "sent" else None,
                0 if state == "sent" else None,
                json.dumps(details),
                aid,
            ),
        )
        changed = db.execute(
            "UPDATE outbox SET state=?,due_at=?,lease_until=NULL,lease_token=NULL,last_code=? WHERE id=? AND lease_token=?",
            (state, due, code, row["id"], token),
        ).rowcount
        if not changed:
            return "lease_lost_outcome_recorded"
    return code
