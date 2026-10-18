"""Local HTTPS proxy for tests only. This is NOT a Codespaces URL or GitHub access gate."""
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/mvp'))
from disposable import require_local_database
require_local_database()
if '127.0.0.1 demo.centerway.test' not in Path('/etc/hosts').read_text():
    subprocess.run(['sudo','tee','-a','/etc/hosts'],input='\n127.0.0.1 demo.centerway.test\n',text=True,stdout=subprocess.DEVNULL,check=True)
root=Path.cwd().resolve()
private=root/'e2e/private/tls'
private.mkdir(parents=True,exist_ok=True,mode=0o700)
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=demo.centerway.test','-addext','subjectAltName=DNS:demo.centerway.test','-keyout',str(private/'key.pem'),'-out',str(private/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(private/'key.pem').chmod(0o600)
pub=subprocess.check_output(['openssl','x509','-in',str(private/'cert.pem'),'-pubkey','-noout'])
der=subprocess.run(['openssl','pkey','-pubin','-outform','DER'],input=pub,check=True,capture_output=True).stdout
(private/'spki.txt').write_text(base64.b64encode(hashlib.sha256(der).digest()).decode())
# Test TLS termination mirrors the HTTPS edge; Vite proxies the real API.
# nginx binds loopback and runs as this user; installed by the devcontainer Dockerfile.
(private/'nginx.conf').write_text('pid PID;\nerror_log ERROR;\nevents {}\nhttp { access_log off; client_body_temp_path TEMP;\nserver { listen 127.0.0.1:8443 ssl; server_name demo.centerway.test;\nssl_certificate CERT; ssl_certificate_key KEY;\nlocation / { proxy_pass http://127.0.0.1:8080; proxy_http_version 1.1;\nproxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto https;\nproxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }\n} }\n'.replace('PID',str(private/'nginx.pid')).replace('ERROR',str(private/'nginx-error.log')).replace('TEMP',str(private/'temp')).replace('CERT',str(private/'cert.pem')).replace('KEY',str(private/'key.pem')))
subprocess.run(['nginx','-c',str(private/'nginx.conf'),'-p',str(private)],check=True)
print('Local HTTPS test proxy ready on loopback 8443; not a remote Codespace.')
