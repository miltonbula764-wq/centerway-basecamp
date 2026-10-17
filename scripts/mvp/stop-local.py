"""Remove only explicitly labelled disposable MVP resources; never remote databases."""
import json
import subprocess

for name in ['cw-gateway', 'cw-rest', 'cw-auth', 'cw-mvp-db']:
    r = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
    if r.returncode:
        continue
    info = json.loads(r.stdout)[0]
    expected = 'mvp' if name == 'cw-mvp-db' else 'true'
    if info['Config'].get('Labels', {}).get('centerway.disposable') != expected:
        raise SystemExit('Refuse to remove unlabelled container ' + name)
    subprocess.run(['docker', 'rm', '-f', name], check=True)
r = subprocess.run(['docker', 'network', 'inspect', 'cw-e2e'], capture_output=True, text=True)
if r.returncode == 0:
    if json.loads(r.stdout)[0].get('Labels', {}).get('centerway.disposable') != 'true':
        raise SystemExit('Refuse to remove unlabelled network')
    subprocess.run(['docker', 'network', 'rm', 'cw-e2e'], check=True)
