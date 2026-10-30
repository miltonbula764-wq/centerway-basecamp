"""CI permits only the reviewed C04 OPTIONS correction in existing API code."""
from pathlib import Path
import subprocess
import sys

OLD="            if request.headers.get('Access-Control-Request-Method') not in request.url_rule.methods or not headers <= {'authorization', 'content-type'}:"
NEW="            methods = app.url_map.bind_to_environ(request.environ).allowed_methods()\n            if request.headers.get('Access-Control-Request-Method') not in (set(methods) & {'GET', 'POST', 'DELETE'}) or not headers <= {'authorization', 'content-type'}:"
path='recovery-mvp/api/app.py'
base=subprocess.run(['git','show',sys.argv[1]+':'+path],capture_output=True,text=True,check=True).stdout
current=Path(path).read_text()
if base!=current and (base.count(OLD)!=1 or base.replace(OLD,NEW)!=current):
    raise SystemExit('Unexpected API change beyond reviewed OPTIONS correction')
print('API preserved except reviewed OPTIONS correction')
