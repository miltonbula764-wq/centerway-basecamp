"""Bounded readiness after a deliberate outage. A gateway HTML 502 is not readiness."""
import json
import time


def wait_rest(probe, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if probe()[0] == 200:
                return
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(.1)
    raise RuntimeError('PostgREST did not recover before readiness deadline')
