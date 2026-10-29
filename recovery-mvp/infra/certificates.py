"""Disposable local PKI only. Never installs trust or obtains a public certificate."""
import os
from pathlib import Path
import subprocess


def command(*args):
    result = subprocess.run(['openssl',*map(str,args)],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Local synthetic certificate generation failed')


def generate(directory):
    path=Path(directory); path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.stat().st_mode & 0o077:
        raise ValueError('Private PKI directory required')
    previous=os.umask(0o077)
    try:
        command('req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-days','2',
                '-subj','/CN=CENTERWAY SYNTHETIC LOCAL CA','-addext','basicConstraints=critical,CA:TRUE',
                '-keyout',path/'ca.key','-out',path/'ca.crt')
        extension=path/'leaf.ext'
        extension.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n')
        for name in ('edge','api','db'):
            command('req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes',
                    '-subj','/CN=localhost','-keyout',path/f'{name}.key','-out',path/f'{name}.csr')
            command('x509','-req','-in',path/f'{name}.csr','-CA',path/'ca.crt','-CAkey',path/'ca.key',
                    '-CAcreateserial','-days','2','-extfile',extension,'-out',path/f'{name}.crt')
    finally:
        os.umask(previous)
