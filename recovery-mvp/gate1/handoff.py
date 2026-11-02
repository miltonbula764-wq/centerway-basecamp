"""Offline public-recipient and ciphertext handoff checks. No database/network."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys

NAMES={'database.age','manifest.age','checksums.json'}
LIMIT=64*1024*1024

def require(condition):
    if not condition: raise ValueError('handoff_rejected')

def recipient_fingerprint(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size<=128)
    value=p.read_text().strip()
    require(re.fullmatch(r'age1[0-9a-z]{58}',value) is not None)
    return hashlib.sha256(value.encode('ascii')).hexdigest()

def check_recipient(path,expected):
    require(re.fullmatch(r'[0-9a-f]{64}',expected) is not None)
    require(hmac.compare_digest(recipient_fingerprint(path),expected))
    return {'status':'public_recipient_matches','private_key_match':'requires_holder_local_check'}

def bundle(path):
    p=Path(path)
    require(p.is_dir() and not p.is_symlink() and not p.stat().st_mode & 0o077)
    require({f.name for f in p.iterdir()}==NAMES)
    for f in p.iterdir():
        s=f.lstat()
        require(stat.S_ISREG(s.st_mode) and not s.st_mode & 0o077 and s.st_size<=LIMIT)
    require((p/'checksums.json').stat().st_size<=1024)
    checks=json.loads((p/'checksums.json').read_bytes())
    require(set(checks)==NAMES-{'checksums.json'})
    for name in ('database.age','manifest.age'):
        raw=(p/name).read_bytes()
        require(raw.startswith(b'age-encryption.org/v1\n'))
        require(checks[name]==hashlib.sha256(raw).hexdigest())
    return {name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in sorted(NAMES)}

def verify_return(original,download):
    require(Path(original).resolve()!=Path(download).resolve())
    a,b=bundle(original),bundle(download)
    require(a==b)
    return {'status':'ciphertext_return_matches','bundle_fingerprint':hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest(),
            'provider_acl_verified':False,'restore_verified':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='operation',required=True)
    f=sub.add_parser('fingerprint'); f.add_argument('--public-key',required=True)
    c=sub.add_parser('recipient'); c.add_argument('--public-key',required=True); c.add_argument('--expected',required=True)
    v=sub.add_parser('custody'); v.add_argument('--original',required=True); v.add_argument('--download',required=True)
    args=p.parse_args()
    if args.operation=='fingerprint': result={'public_recipient_sha256':recipient_fingerprint(args.public_key)}
    elif args.operation=='recipient': result=check_recipient(args.public_key,args.expected)
    else: result=verify_return(args.original,args.download)
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception:
        print('handoff_rejected',file=sys.stderr);sys.exit(1)
