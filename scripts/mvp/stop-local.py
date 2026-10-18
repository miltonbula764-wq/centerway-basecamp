"""Remove only explicitly labelled disposable MVP resources; never another demo or remote DB."""
import json
import subprocess

names=[]
# Preflight ALL resources before removing anything, including when Codespaces owns the names.
for name in ['cw-gateway','cw-rest','cw-auth','cw-mvp-db']:
    r=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
    if r.returncode: continue
    labels=json.loads(r.stdout)[0]['Config'].get('Labels',{})
    expected='mvp' if name=='cw-mvp-db' else 'true'
    if labels.get('centerway.disposable')!=expected or labels.get('centerway.demo')=='codespaces':
        raise SystemExit('Refuse to remove another stack: '+name)
    names.append(name)
r=subprocess.run(['docker','network','inspect','cw-e2e'],capture_output=True,text=True)
network=r.returncode==0
if network:
    labels=json.loads(r.stdout)[0].get('Labels',{})
    if labels.get('centerway.disposable')!='true' or labels.get('centerway.demo')=='codespaces':
        raise SystemExit('Refuse to remove another network')
for name in names: subprocess.run(['docker','rm','-f',name],check=True)
if network: subprocess.run(['docker','network','rm','cw-e2e'],check=True)
