"""Regression of the actual C01 outage probe; no product clocks or hosted services."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('readiness', Path(__file__).parents[1]/'readiness.py')
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def test_html_gateway_error_then_actual_json_readiness(self):
        statuses = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status = 502 if not statuses else 200
                statuses.append(status)
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b'<html>Bad Gateway</html>' if status == 502 else b'[]')
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def probe():
            try:
                with urlopen('http://127.0.0.1:'+str(server.server_port), timeout=1) as r:
                    return r.status, json.loads(r.read())
            except HTTPError as r:
                return r.code, json.loads(r.read())
        try:
            readiness.wait_rest(probe, timeout=2)
            self.assertEqual(statuses, [502, 200])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_never_accepts_persistent_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'readiness deadline'):
            readiness.wait_rest(lambda: (503, {}), timeout=.15)


if __name__ == '__main__':
    unittest.main()
