"""CI permits only exact reviewed transport changes; never a broad API exception."""
from pathlib import Path
import hashlib
import subprocess
import sys

OLD="            if request.headers.get('Access-Control-Request-Method') not in request.url_rule.methods or not headers <= {'authorization', 'content-type'}:"
NEW="            methods = app.url_map.bind_to_environ(request.environ).allowed_methods()\n            if request.headers.get('Access-Control-Request-Method') not in (set(methods) & {'GET', 'POST', 'DELETE'}) or not headers <= {'authorization', 'content-type'}:"
path='recovery-mvp/api/app.py'
base=subprocess.run(['git','show',sys.argv[1]+':'+path],capture_output=True,text=True,check=True).stdout
current=Path(path).read_text()
managed_session_change = (hashlib.sha256(base.encode()).hexdigest() == '2ac3a53a29af29ffc03d91f10ba6854934abee9d371d02e85c7fd9306683e07b' and
                          hashlib.sha256(current.encode()).hexdigest() == '4c9007e4b6fa27081ffb3eb1b0f6be1bca4ad3711f9eef0c28e063f8da3cabb6')
t02_read_change = (hashlib.sha256(base.encode()).hexdigest() == '4c9007e4b6fa27081ffb3eb1b0f6be1bca4ad3711f9eef0c28e063f8da3cabb6' and
                   hashlib.sha256(current.encode()).hexdigest() == '0f905173c0799c669f38a9c78b7dd19d91267d6e814e6b76725a5b75a5cba799')
if base!=current and not managed_session_change and not t02_read_change and (base.count(OLD)!=1 or base.replace(OLD,NEW)!=current):
    raise SystemExit('Unexpected API change beyond exact reviewed OPTIONS/session-store/T02 read-only changes')
spec='recovery-mvp/api/openapi.json'
base_spec=subprocess.run(['git','show',sys.argv[1]+':'+spec],capture_output=True,check=True).stdout
current_spec=Path(spec).read_bytes()
if base_spec != current_spec:
    raise SystemExit('Existing OpenAPI contract changed; preserve canonical 71-case capture')
t02_spec=Path('recovery-mvp/api/openapi-t02.json')
if hashlib.sha256(t02_spec.read_bytes()).hexdigest() != 'c29afae4da27b23fb00c7d45274271a27bd84781fa397a34cb5b922aa4f61321':
    raise SystemExit('Unexpected T02 additive OpenAPI contract change')
print('API/OpenAPI preserved except exact reviewed T02 read-only addition')
