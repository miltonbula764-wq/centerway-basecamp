"""CI permits only exact reviewed OPTIONS and M67 session extraction changes."""
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
if base!=current and not managed_session_change and (base.count(OLD)!=1 or base.replace(OLD,NEW)!=current):
    raise SystemExit('Unexpected API change beyond reviewed OPTIONS/session-store changes')
print('API preserved except exact reviewed OPTIONS/session-store changes')
