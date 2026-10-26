"""Minimal HTTPS sender example, no vendor connector and no automatic retries.

Run from v2: python examples/webhooks/send.py --help
Private key files must be outside the checkout, owner-only. Never use verify=False.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import ssl
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from centerway.webhooks import PATH,private_bytes,signed_bytes


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def main():
    parser=argparse.ArgumentParser(description='Explicitly signed source-claim example; no real supplier integration.')
    for arg in ('url','source','key-id','secret-file','body-file'): parser.add_argument('--'+arg,required=True)
    parser.add_argument('--ca-file',help='Optional test CA; standard HTTPS verification remains enabled.')
    args=parser.parse_args()
    try:
        url=urlsplit(args.url)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.path!=PATH or url.query or url.fragment:
            raise ValueError('Exact HTTPS endpoint required.')
        for value in (args.source,args.key_id):
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value): raise ValueError('Invalid source/key identifier.')
        secret=private_bytes(args.secret_file,128).strip()
        if not re.fullmatch(b'[0-9a-f]{64}',secret): raise ValueError('Invalid private key.')
        with open(args.body_file,'rb') as stream: raw=stream.read(65537)
        if not 1<=len(raw)<=65536: raise ValueError('Invalid body size.')
        stamp=str(int(time.time()));nonce=secrets.token_hex(16)
        signature='v1='+hmac.new(bytes.fromhex(secret.decode()),signed_bytes(args.source,args.key_id,stamp,nonce,raw),hashlib.sha256).hexdigest()
        request=Request(args.url,raw,{'Content-Type':'application/json','X-CW-Source':args.source,'X-CW-Key-Id':args.key_id,
                                   'X-CW-Timestamp':stamp,'X-CW-Nonce':nonce,'X-CW-Signature':signature},method='POST')
        opener=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=args.ca_file)),NoRedirect())
        try: response=opener.open(request,timeout=20)
        except HTTPError as error: response=error
        with response:
            # Never echo an untrusted response (a redirect/error could contain credentials).
            status=response.status
        print(json.dumps({'http_status':status,'delivery':'acknowledged' if status==200 else 'rejected_or_uncertain','automatic_retry':False}))
        return 0 if status==200 else 1
    except (OSError,ValueError):
        print('{"delivery":"unavailable_or_uncertain","automatic_retry":false}',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
