"""Explicit synthetic external checks. Private credentials/state, no token output.
Run before and after a manually confirmed redeploy, never retrying POST.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import uuid

T='a1000000-0000-0000-0000-000000000001'
B='b1000000-0000-0000-0000-000000000001'
C='a2000000-0000-0000-0000-000000000001'
BC='b2000000-0000-0000-0000-000000000001'


def request(base,method,path,data=None,token=None,headers=None):
    h={'Content-Type':'application/json'}
    if token: h['Authorization']='Bearer '+token
    h.update(headers or {})
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers=h)
    try:
        response=urllib.request.urlopen(req,timeout=90,context=ssl.create_default_context())
    except urllib.error.HTTPError as error:
        response=error
    with response:
        payload=response.read()
        return response.status,{k.lower():v for k,v in response.headers.items()},json.loads(payload) if payload else None


def stable_journey(value):
    value=json.loads(json.dumps(value))
    value['data']['work_items']=sorted(value['data'].get('work_items',[]),key=lambda x:json.dumps(x,sort_keys=True))
    return value


def private(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o077:
        raise ValueError('private file required')
    return p


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['before','after'])
    p.add_argument('--url',required=True)
    p.add_argument('--credentials',required=True)
    p.add_argument('--state',required=True)
    a=p.parse_args()
    u=urlsplit(a.url)
    if u.scheme!='https' or not u.hostname or not u.hostname.endswith('.onrender.com') or a.url!=f'https://{u.netloc}' or u.username or u.password:
        raise ValueError('assigned public HTTPS URL required')
    route=f'/v1/tenants/{T}/clients/{C}/journey'
    operations=f'/v1/tenants/{T}/clients/{C}/operations'
    checks=[]
    def check(label,condition):
        if not condition: raise RuntimeError('failed check: '+label)
        checks.append(label)
    status,_,body=request(a.url,'GET','/health')
    check('public_https_liveness',status==200 and body.get('readiness')=='not_assessed')
    if a.phase=='before':
        credentials=json.loads(private(a.credentials).read_text())
        tokens={}
        for name in ('alice','bob','reader'):
            status,headers,body=request(a.url,'POST','/v1/sessions',dict(username=name,password=credentials[name]))
            check('login_'+name,status==201 and headers.get('cache-control')=='no-store')
            tokens[name]=body['access_token']
        token=tokens['alice']
        check('identity',request(a.url,'GET','/v1/session',token=token)[2]['principal']=='http_alice')
        check('tenant_isolation_alice',request(a.url,'GET',f'/v1/tenants/{B}/clients/{BC}/journey',token=token)[0]==403)
        check('tenant_isolation_bob',request(a.url,'GET',route,token=tokens['bob'])[0]==403)
        check('directory',request(a.url,'GET',f'/v1/tenants/{T}/clients',token=token)[0]==200)
        check('cors_rejected',request(a.url,'GET',route,token=token,headers={'Origin':'https://evil.invalid'})[0]==403)
        status,headers,_=request(a.url,'OPTIONS',route,headers={'Origin':'https://getcenterway.com','Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'})
        check('cors_preflight',status==204 and headers.get('access-control-allow-origin')=='https://getcenterway.com')
        check('forwarded_headers_ignored',request(a.url,'GET','/v1/session',token=token,headers={'Forwarded':'proto=http;host=evil.invalid','X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.invalid'})[0]==200)
        command=dict(request_id=str(uuid.uuid4()),operation='append_value',arguments=dict(kind='source',id=str(uuid.uuid4()),expected_revision=0,reason='SYNTHETIC M67 public persistence probe',data=dict(name='SYNTHETIC public probe',locator='synthetic://m67',method='synthetic fixture')))
        check('reader_operation_forbidden',request(a.url,'POST',operations,command,token=tokens['reader'])[0]==403)
        status,_,receipt=request(a.url,'POST',operations,command,token=token)
        check('synthetic_write',status==200 and receipt['data']['status']=='completed')
        check('idempotent_replay',request(a.url,'POST',operations,command,token=token)[2]==receipt)
        check('logout',request(a.url,'DELETE','/v1/session',token=tokens['reader'])[0]==204)
        check('logout_revoked',request(a.url,'GET','/v1/session',token=tokens['reader'])[0]==401)
        journey=request(a.url,'GET',route,token=token)[2]
        state=dict(url=a.url,tokens=tokens,command=command,receipt=receipt,journey=journey)
        fd=os.open(a.state,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream: json.dump(state,stream)
    else:
        state=json.loads(private(a.state).read_text())
        check('same_target',state['url']==a.url)
        token=state['tokens']['alice']
        check('session_survives_redeploy',request(a.url,'GET','/v1/session',token=token)[0]==200)
        check('journey_survives_redeploy',stable_journey(request(a.url,'GET',route,token=token)[2])==stable_journey(state['journey']))
        check('replay_survives_redeploy',request(a.url,'POST',operations,state['command'],token=token)[2]==state['receipt'])
        check('revocation_survives_redeploy',request(a.url,'GET','/v1/session',token=state['tokens']['reader'])[0]==401)
        check('isolation_after_redeploy',request(a.url,'GET',route,token=state['tokens']['bob'])[0]==403)
        for name in ('alice','bob'):
            check('final_logout_'+name,request(a.url,'DELETE','/v1/session',token=state['tokens'][name])[0]==204)
    print(json.dumps(dict(phase=a.phase,url=a.url,checks=checks,passed=len(checks),synthetic_only=True)))


if __name__=='__main__':
    try: main()
    except Exception as error:
        # No response bodies, URL queries, credentials or bearer tokens in logs.
        print('Public probe failed: '+type(error).__name__,file=sys.stderr)
        sys.exit(1)
