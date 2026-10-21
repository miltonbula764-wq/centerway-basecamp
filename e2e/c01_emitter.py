"""Independent C01 HTTP sender; Python standard library, no database or Supabase SDK.

CLI: C01_SECRET_FILE=/private/key python3 e2e/c01_emitter.py PAYLOAD OPERATION_UUID
Set C01_ENDPOINT and optionally C01_CA_FILE. Keep the same file and UUID on retry.
"""
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request


def send(endpoint, secret, payload, operation, ca_file=None, timeout=40):
    if not endpoint.startswith('https://'):
        raise ValueError('C01 requires HTTPS')
    request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={
        'Authorization': 'Bearer ' + secret,
        'Idempotency-Key': operation,
        'Content-Type': 'application/json',
    }, method='POST')
    context = ssl.create_default_context(cafile=ca_file)
    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            return response.status, json.loads(response.read()), dict(response.headers)
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read()), dict(response.headers)
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        # Delivery is uncertain. The caller must retain BOTH identities and payload.
        return None, {'code': 'connection_failed', 'retry_same_idempotency_key': True}, {}


if __name__ == '__main__':
    status, body, _ = send(os.environ['C01_ENDPOINT'],
        Path(os.environ['C01_SECRET_FILE']).read_text().strip(),
        json.loads(Path(sys.argv[1]).read_text()), sys.argv[2], os.environ.get('C01_CA_FILE'))
    print(json.dumps({'http_status': status, 'result': body}))
    sys.exit(0 if status == 200 else 1)
