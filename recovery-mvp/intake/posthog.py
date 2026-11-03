"""M01: server-side, read-only PostHog outcome-event intake into append-only PostgreSQL.

One configured SaaS tenant, one explicitly named business-operation success event.
This is producer telemetry; it is NOT independent evidence of business value.
No OAuth, web route, automated scheduler, intervention or customer emails.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import re
import sys
from urllib import request
import uuid

MAX_CUSTOMERS = 200
MAX_DAYS = 7
NAMESPACE = uuid.UUID("dd31e8c8-36b3-413b-9770-047949201a5c")
EVENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,79}$")


class IntakeError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise IntakeError(code)


def utc_day(value):
    try:
        d = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise IntakeError("invalid_utc_day") from None
    require(d.isoformat() == value, "invalid_utc_day")
    return d


def validate_settings(tenant, region, project, group_index, event):
    try:
        tenant = str(uuid.UUID(tenant))
        project = int(project)
        group_index = int(group_index)
    except (ValueError, TypeError, AttributeError):
        raise IntakeError("invalid_settings") from None
    require(region in ("us", "eu"), "invalid_region")
    require(0 < project <= 2147483647, "invalid_project")
    require(0 <= group_index <= 4, "invalid_group_index")
    require(isinstance(event, str) and EVENT_NAME.fullmatch(event) is not None, "invalid_event")
    return tenant, region, project, group_index, event


def normalize_rows(value):
    """Reject incomplete/ambiguous provider results, never guess missing customers."""
    require(isinstance(value, list) and len(value) <= MAX_CUSTOMERS, "intake_truncated")
    seen, rows = set(), []
    for item in value:
        require(isinstance(item, (tuple, list)) and len(item) == 2, "invalid_provider_row")
        customer, amount = item
        require(isinstance(customer, str) and 0 < len(customer) <= 256
                and customer == customer.strip(), "invalid_customer_key")
        require(type(amount) is int and 0 <= amount <= 2147483647, "invalid_provider_count")
        require(customer not in seen, "duplicate_customer")
        seen.add(customer)
        rows.append({"customer": customer, "count": amount})
    return sorted(rows, key=lambda r: r["customer"])


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IntakeError("posthog_redirect_rejected")


def posthog_transport(url, headers, body):
    req = request.Request(url, data=body, method="POST", headers=headers)
    opener = request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=15) as response:
            payload = response.read(1_000_001)
            require(len(payload) <= 1_000_000, "provider_response_too_large")
            require(response.status == 200, "provider_http_error")
    except IntakeError:
        raise
    except Exception:
        # Do not print responses, API keys, DSNs or potentially sensitive URLs.
        raise IntakeError("provider_unavailable") from None
    try:
        return json.loads(payload, parse_constant=lambda _x: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeDecodeError):
        raise IntakeError("provider_invalid_json") from None


class PostHog:
    def __init__(self, region, project, token, event, group_index, transport=posthog_transport):
        require(region in ("us", "eu"), "invalid_region")
        require(type(project) is int and 0 < project <= 2147483647, "invalid_project")
        require(type(group_index) is int and 0 <= group_index <= 4, "invalid_group_index")
        require(isinstance(event, str) and EVENT_NAME.fullmatch(event) is not None, "invalid_event")
        require(isinstance(token, str) and token.strip() and "\n" not in token, "missing_key")
        self.region, self.project, self.token = region, project, token
        self.event, self.group_index, self.transport = event, group_index, transport

    def query_for_day(self, day):
        require(isinstance(day, date) and type(day) is date, "invalid_utc_day")
        start, end = day.isoformat(), (day + timedelta(days=1)).isoformat()
        group = "events.`$group_" + str(self.group_index) + "`"
        # IDs, region, group index and event name validated before formatting.
        return (
            f"SELECT {group} AS customer, count(DISTINCT uuid) AS amount FROM events "
            f"WHERE event = '{self.event}' "
            f"AND timestamp >= toDateTime('{start} 00:00:00', 'UTC') "
            f"AND timestamp < toDateTime('{end} 00:00:00', 'UTC') "
            f"AND {group} IS NOT NULL AND {group} != '' "
            f"GROUP BY customer ORDER BY customer LIMIT {MAX_CUSTOMERS + 1}"
        )

    def fetch_day(self, day):
        query = self.query_for_day(day)
        url = f"https://{self.region}.posthog.com/api/projects/{self.project}/query/"
        body = json.dumps({"query": {"kind": "HogQLQuery", "query": query},
                           "name": "centerway_m01_daily_outcomes"}, separators=(",", ":")).encode()
        result = self.transport(
            url, {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, body
        )
        require(isinstance(result, dict) and not result.get("error"), "provider_incomplete")
        require(not result.get("has_more") and not result.get("next"), "provider_incomplete")
        columns = result.get("columns")
        require(columns is None or columns == ["customer", "amount"], "provider_columns_changed")
        return normalize_rows(result.get("results"))


def batch_id(tenant, project, event, index, day, rows):
    payload = json.dumps([tenant, project, event, index, day.isoformat(), rows],
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return str(uuid.uuid5(NAMESPACE, hashlib.sha256(payload.encode()).hexdigest()))


class PostgresStore:
    """Database role must be centerway_api member scoped to the SaaS tenant."""
    def __init__(self, dsn):
        try:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            parsed = conninfo_to_dict(dsn)
        except Exception:
            raise IntakeError("invalid_database_settings") from None
        host = parsed.get("host", "")
        local = host in ("localhost", "127.0.0.1", "::1")
        require(local or parsed.get("sslmode") == "verify-full", "database_tls_required")
        self.psycopg, self.dsn = psycopg, dsn

    def completed_days(self, tenant, project, event, group_index, start, end):
        with self.psycopg.connect(self.dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT DISTINCT period_start::date
                    FROM centerway.outcome_imports
                    WHERE tenant_id=%s AND project_id=%s AND event_name=%s
                      AND group_index=%s AND period_start >= %s
                      AND period_start < %s""",
                    (tenant, project, event, group_index, start, end))
                return {r[0] for r in cur.fetchall()}

    def append_day(self, tenant, project, event, group_index, day, rows):
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        ident = batch_id(tenant, project, event, group_index, day, rows)
        with self.psycopg.connect(self.dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT centerway.append_posthog_outcome_import(
                    %s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (tenant, ident, project, event, group_index, start, end,
                     json.dumps(rows, ensure_ascii=False, separators=(",", ":"))))
                returned = str(cur.fetchone()[0])
                require(returned == ident, "unexpected_receipt")
        return ident


def sync(provider, store, tenant, first_day, *, through=None, max_days=MAX_DAYS,
         lookback_days=2):
    """Backfill oldest gaps first; then revisit recent days for late arrivals."""
    require(isinstance(first_day, date), "invalid_utc_day")
    today = datetime.now(timezone.utc).date()
    through = through or today  # exclusive; today is always excluded
    require(isinstance(through, date) and through <= today, "invalid_cutoff")
    require(1 <= max_days <= MAX_DAYS and 0 <= lookback_days <= 7, "invalid_limits")
    require(0 <= (through - first_day).days <= 366, "invalid_history_range")
    days = [first_day + timedelta(days=i) for i in range((through - first_day).days)]
    completed = store.completed_days(tenant, provider.project, provider.event,
                                     provider.group_index, first_day, through)
    missing = [d for d in days if d not in completed]
    if missing:
        selected = missing[:max_days]
    else:
        selected = days[-min(lookback_days, max_days):] if lookback_days else []
    processed = 0
    for day in selected:
        rows = provider.fetch_day(day)  # never commit an incomplete source response
        store.append_day(tenant, provider.project, provider.event, provider.group_index, day, rows)
        processed += 1
    return {"completed_days": processed, "backfill_remaining_days": max(0, len(missing)-processed),
            "mode": "backfill" if missing else "recheck", "live_data_claim": False}


def main(argv=None):
    p = argparse.ArgumentParser(description="CENTERWAY M01 read-only PostHog importer")
    p.add_argument("--since", required=True, help="first UTC day, inclusive (YYYY-MM-DD)")
    p.add_argument("--through", help="last UTC day, exclusive; defaults to current UTC day")
    p.add_argument("--max-days", type=int, default=MAX_DAYS)
    args = p.parse_args(argv)
    try:
        tenant, region, project, idx, event = validate_settings(
            os.environ["CENTERWAY_TENANT_ID"], os.environ["POSTHOG_REGION"],
            os.environ["POSTHOG_PROJECT_ID"], os.environ["POSTHOG_GROUP_INDEX"],
            os.environ["POSTHOG_OUTCOME_EVENT"]
        )
        provider = PostHog(region, project, os.environ["POSTHOG_PERSONAL_API_KEY"], event, idx)
        store = PostgresStore(os.environ["CENTERWAY_INTAKE_DB_DSN"])
        status = sync(provider, store, tenant, utc_day(args.since),
                      through=utc_day(args.through) if args.through else None,
                      max_days=args.max_days)
        print(json.dumps(status, separators=(",", ":")))
        return 0
    except (KeyError, IntakeError):
        print("m01_sync_failed: configuration_or_source_error", file=sys.stderr)
        return 2
    except Exception:
        print("m01_sync_failed: database_or_provider_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
