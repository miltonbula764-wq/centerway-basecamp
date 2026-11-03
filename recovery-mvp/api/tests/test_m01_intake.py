"""M01 deterministic tests. No external network, credentials or cloud changes."""
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "intake"))
from posthog import (IntakeError, MAX_CUSTOMERS, PostHog, normalize_rows,
                     batch_id, sync, utc_day, validate_settings)


TENANT = "a1000000-0000-0000-0000-000000000001"


class FakeStore:
    def __init__(self):
        self.days = set()
        self.rows = {}
        self.writes = []
    def completed_days(self, tenant, project, event, group, start, end):
        return {d for d in self.days if start <= d < end}
    def append_day(self, tenant, project, event, group, day, rows):
        self.days.add(day)
        ident = batch_id(tenant, project, event, group, day, rows)
        self.rows[day] = rows
        self.writes.append((day, ident))
        return ident


class FakeProvider:
    project, event, group_index = 7, "workflow_completed", 0
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []
        self.results = [["company-a", 3]]
    def fetch_day(self, day):
        self.calls.append(day)
        if self.fail == day:
            raise IntakeError("simulated_connection_failure")
        return normalize_rows(self.results)


class M01Tests(unittest.TestCase):
    def test_configuration_rejects_injection_and_wrong_scope(self):
        self.assertEqual(validate_settings(TENANT, "eu", "12", "0", "workflow_completed")[2], 12)
        for args in [(TENANT, "elsewhere", 12, 0, "ok"),
                     (TENANT, "us", 0, 0, "ok"),
                     (TENANT, "us", 12, 5, "ok"),
                     (TENANT, "us", 12, 0, "x';DELETE FROM events;--"),
                     ("not-a-uuid", "us", 12, 0, "ok")]:
            with self.subTest(args=args), self.assertRaises(IntakeError):
                validate_settings(*args)

    def test_query_fixed_domain_group_and_utc_window(self):
        seen = []
        def transport(url, headers, body):
            seen.append((url, headers, json.loads(body)))
            return {"results": [["account-b", 4], ["account-a", 2]], "columns": ["customer", "amount"]}
        client = PostHog("us", 123, "in-memory-private-key", "workflow_completed", 2, transport)
        result = client.fetch_day(date(2026, 1, 12))
        self.assertEqual(result, [{"customer": "account-a", "count": 2},
                                  {"customer": "account-b", "count": 4}])
        url, headers, payload = seen[0]
        self.assertEqual(url, "https://us.posthog.com/api/projects/123/query/")
        self.assertNotIn("in-memory-private-key", url)
        self.assertEqual(headers["Authorization"], "Bearer in-memory-private-key")
        q = payload["query"]["query"]
        self.assertIn("events.\`$group_2\`", q)
        self.assertIn("2026-01-12 00:00:00", q)
        self.assertIn("2026-01-13 00:00:00", q)
        self.assertIn("count(DISTINCT uuid)", q)
        self.assertIn("LIMIT 201", q)

    def test_rejects_missing_incomplete_or_bad_provider_data(self):
        cases = [
            {}, {"error": "failed", "results": []}, {"results": None},
            {"results": [["c", -1]]}, {"results": [["c", True]]},
            {"results": [["c", 1.1]]}, {"results": [["c", "1"]]},
            {"results": [["c", 1], ["c", 3]]}, {"results": [[" c", 1]]},
            {"results": [["c", 1]], "next": "page2"},
            {"results": [["c", 1]], "columns": ["unexpected", "columns"]},
            {"results": [["x", 1]] * (MAX_CUSTOMERS + 1)}
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:100]):
                client = PostHog("eu", 99, "private", "workflow_completed", 0,
                                 lambda *_: payload)
                with self.assertRaises(IntakeError):
                    client.fetch_day(date(2026, 1, 1))

    def test_empty_result_is_observation_not_zero_for_every_customer(self):
        client = PostHog("eu", 99, "private", "workflow_completed", 0,
                         lambda *_: {"results": []})
        self.assertEqual(client.fetch_day(date(2026, 2, 3)), [])

    def test_oldest_history_first_then_late_event_recheck(self):
        provider, store = FakeProvider(), FakeStore()
        start, through = date(2026, 1, 1), date(2026, 1, 6)
        result = sync(provider, store, TENANT, start, through=through, max_days=3)
        self.assertEqual(result["completed_days"], 3)
        self.assertEqual(result["backfill_remaining_days"], 2)
        result = sync(provider, store, TENANT, start, through=through, max_days=3)
        self.assertEqual(result["completed_days"], 2)
        self.assertEqual(result["backfill_remaining_days"], 0)
        provider.results = [["company-a", 4]]
        result = sync(provider, store, TENANT, start, through=through, max_days=3)
        self.assertEqual(result["mode"], "recheck")
        self.assertEqual(result["completed_days"], 2)
        self.assertEqual(store.rows[date(2026, 1, 5)][0]["count"], 4)
        a, b = batch_id(TENANT, 7, provider.event, 0, through - timedelta(days=1),
                        [{"customer": "company-a", "count": 3}]), store.writes[-1][1]
        self.assertNotEqual(a, b)

    def test_failed_day_does_not_advance_checkpoint(self):
        d = date(2026, 1, 1)
        p, s = FakeProvider(fail=d), FakeStore()
        with self.assertRaises(IntakeError):
            sync(p, s, TENANT, d, through=date(2026, 1, 2))
        self.assertEqual(s.days, set())
        p.fail = None
        sync(p, s, TENANT, d, through=date(2026, 1, 2))
        self.assertEqual(s.days, {d})

    def test_invalid_time_and_limits_fail_closed(self):
        with self.assertRaises(IntakeError):
            utc_day("2026-1-1")
        p, s = FakeProvider(), FakeStore()
        for kw in [{"max_days": 100}, {"lookback_days": 100},
                   {"through": date(2027, 1, 1)}]:
            with self.subTest(kw=kw), self.assertRaises(IntakeError):
                sync(p, s, TENANT, date(2026, 1, 1), **kw)
        with self.assertRaises(IntakeError):
            sync(p, s, TENANT, date(2024, 1, 1), through=date(2026, 1, 1))

    def test_receipts_are_deterministic(self):
        a = [{"customer": "x", "count": 1}]
        self.assertEqual(batch_id(TENANT, 7, "workflow_completed", 0, date(2026, 1, 1), a),
                         batch_id(TENANT, 7, "workflow_completed", 0, date(2026, 1, 1), a))
        self.assertNotEqual(batch_id(TENANT, 7, "workflow_completed", 0, date(2026, 1, 1), a),
                            batch_id(TENANT, 7, "workflow_completed", 0, date(2026, 1, 2), a))


if __name__ == "__main__":
    unittest.main()
