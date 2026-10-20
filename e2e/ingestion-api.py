"""Real local TLS + shared Edge handler + GoTrue/PostgREST/PostgreSQL17; no hosted requests."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request
import urllib.error
import uuid

if os.environ.get('CW_LOCAL_MVP') == '1':
    info=json.loads(subprocess.check_output(['docker','inspect','cw-mvp-db']))[0]
    assert info['Config']['Image']=='postgres:17' and info['Config'].get('Labels',{}).get('centerway.disposable')=='mvp'
    assert '/var/lib/postgresql/data' in info['HostConfig'].get('Tmpfs',{})
    assert all(m['Type']=='tmpfs' for m in info.get('Mounts',[]))
    assert info['HostConfig']['PortBindings']['5432/tcp']==[{'HostIp':'127.0.0.1','HostPort':'5432'}]
else:
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
assert os.environ.get('PGHOST')=='127.0.0.1' and os.environ.get('PGDATABASE')=='cw_e2e'
cfg=json.loads(Path('e2e/private/public.json').read_text());assert cfg['url']=='http://127.0.0.1:54321'
f=json.loads(Path('e2e/operational-fixtures.json').read_text());users=json.loads(Path('e2e/private/mvp-users.json').read_text())
private=Path('e2e/private');private.mkdir(exist_ok=True)
newid=lambda:str(uuid.uuid4())
env={k:v for k,v in os.environ.items() if k not in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS')};env['PGPASSFILE']='/dev/null'
def sql(query):
    r=subprocess.run(['psql','-X','-qAt','-v','ON_ERROR_STOP=1'],input=query,text=True,capture_output=True,env=env)
    assert r.returncode==0, r.stderr
    return r.stdout.strip()
def literal(v):return "'"+str(v).replace("'","''")+"'"
def http(url,body=None,headers=None,method='POST',context=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers or {},method=method)
    try:
        with urllib.request.urlopen(req,context=context,timeout=40) as r:return r.status,json.loads(r.read() or 'null'),r.headers
    except urllib.error.HTTPError as r:return r.code,json.loads(r.read() or 'null'),r.headers

def rest(path,user='admin',body=None,method='POST'):
    token=users[user]['token'] if user else cfg['anon']
    return http(cfg['url']+path,body,{'apikey':cfg['anon'],'Authorization':'Bearer '+token,'Content-Type':'application/json','Prefer':'return=representation'},method)
def rpc(name,args,user='admin'):return rest('/rest/v1/rpc/'+name,user,args)
users['ownerB']=json.loads(Path('e2e/private/users.json').read_text())['ownerB']
for role in ['admin','operator','viewer','ownerB']:
    s,r,_=rest('/auth/v1/token?grant_type=password',None,{'email':users[role]['email'],'password':users[role]['password']});assert s==200;users[role]['token']=r['access_token'];assert r['user']['email_confirmed_at']

subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/ingestion_privileges_test.sql'],env=env,check=True)
for suite,marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
    r=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+suite+'_test.sql'],env=env,text=True,capture_output=True)
    output=r.stdout+r.stderr
    Path('e2e/logs/api-regression-'+suite+'.log').write_text(output)
    assert r.returncode==3 and re.search(marker+r' pass=\d+ fail=0(?: |$)',output) and not re.search(r'not_run=[1-9]',output),suite+' regression failed (see log)'
    print(re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output).group(0))
tenant=f['tenant'];profile=f['profile'];source='synthetic-atlas';secrets=[]
def credential(role='admin',expires=None,rotate=None,operation=None):
    args={'_tenant_id':tenant,'_name':'[SYNTHETIC] API probe','_source':source,'_expires_at':expires or (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),'_operation_id':operation or newid()}
    if rotate:args['_rotate_from']=rotate
    status,result,_=rpc('create_ingestion_credential',args,role)
    if status==200 and result.get('secret'):secrets.append(result['secret'])
    return status,result,args
for role in ['operator','viewer','ownerB']:
    assert credential(role)[0]==403
status,c,args=credential();assert status==200 and c['secret'].startswith('cw_ingest_v1_')
assert rpc('create_ingestion_credential',args)[1]['secret'] is None
args_changed={**args,'_name':'different'};assert rpc('create_ingestion_credential',args_changed)[0]==400
assert sql('SELECT secret_hash FROM ingestion_credentials WHERE id='+literal(c['id']))==hashlib.sha256(c['secret'].encode()).hexdigest()
assert rest('/rest/v1/ingestion_credentials?select=secret_hash','admin',None,'GET')[0]==403
for role in ['operator','viewer']:
    assert rest('/rest/v1/ingestion_credentials?select=id',role,None,'GET')[1]==[]
assert rest('/rest/v1/ingestion_credentials?select=id&tenant_id=neq.'+tenant,'admin',None,'GET')[1]==[]
external_ref='api-client-'+newid()
status,subjects,_=rest('/rest/v1/subjects?select=id',body={'tenant_id':tenant,'external_ref':external_ref,'display_name':'[SYNTHETIC] API client'});assert status==201;subject=subjects[0]['id']
midnight=dt.datetime.now(dt.timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
def date(days):return (midnight+dt.timedelta(days=days)).isoformat().replace('+00:00','Z')
def row(day=-2,value='50',key=None):return {'line':1,'subject_external_ref':external_ref,'indicator_key':'cycle_minutes','observed_at':date(day),'value_numeric':value,'unit':'min','idempotency_key':key or newid()}
def payload(rows=None):return {'profile_id':profile,'source':source,'coverage':{'start':date(-40),'end':date(0),'declared':True},'rows':rows if rows is not None else [row()]}
# Every business table other than C01 must remain byte-for-byte unchanged during ingestion.
tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE 'c0%' OR tablename LIKE 'cw_%') ORDER BY tablename").splitlines()
def snapshot():return [sql('SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),\'[]\')::text,\'UTF8\')),\'hex\') FROM public."'+t+'" x') for t in tables]
before=snapshot()
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(private/'ingestion-key.pem'),'-out',str(private/'ingestion-cert.pem')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
(private/'ingestion-key.pem').chmod(0o600)
context=ssl.create_default_context(cafile=str(private/'ingestion-cert.pem'))
endpoint='https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
log=open('e2e/logs/ingestion-http.log','w')
server=subprocess.Popen(['bun','run','e2e/ingestion-server.ts'],stdout=log,stderr=subprocess.STDOUT)
def ingest(p=None,key=None,op=None):
    return http(endpoint,p if p is not None else payload(),{'Authorization':'Bearer '+(key or c['secret']),'Idempotency-Key':op or newid(),'Content-Type':'application/json'},context=context)
try:
    for _ in range(50):
        try:
            if http(endpoint,method='GET',context=context)[0]==405:break
        except urllib.error.URLError:time.sleep(.1)
    else:raise AssertionError('HTTPS handler not ready')
    p=payload([row(-4,'100'),row(-3,'75'),row(-2,'50')]);op=newid()
    status,result,_=ingest(p,op=op);assert status==200, (status,result);assert result['status']=='completed';batch=result['batch_id']
    assert sql('SELECT count(*) FROM observations WHERE batch_id='+literal(batch))=='3'
    assert sql('SELECT count(*) FROM observations WHERE batch_id='+literal(batch)+' AND created_by IS NULL AND integration_credential_id='+literal(c['id']))=='3'
    assert sql("SELECT count(*) FROM audit_log WHERE entity_type='observations' AND details->>'actor_kind'='integration' AND actor_id IS NULL AND details->>'integration_credential_id'="+literal(c['id']))=='3'
    assert ingest(p,op=op)[1]['batch_id']==batch
    conflict={**p,'rows':[row(-2,'999')]};assert ingest(conflict,op=op)[0]==409
    # Different transport, same unchanged C01 row identity; CSV does not insert duplicates.
    csv={'_tenant_id':tenant,'_expected_profile_id':profile,'_source':source,'_coverage_start':date(-40),'_coverage_end':date(0),'_coverage_declared':True,'_file_name':'synthetic-api-compat.csv','_rows':p['rows']}
    s,duplicate,_=rpc('import_observations',csv);assert s==200 and duplicate['inserted']==0 and duplicate['duplicates']==3,(s,duplicate)
    p2=payload([row(-2,'999',p['rows'][0]['idempotency_key'])]);assert ingest(p2)[0]==409
    badtests=[({'rows':[row() for _ in range(1001)]},400),({'rows':[{**row(),'indicator_key':'does_not_exist'}]},422),({'rows':[{**row(),'unit':'hours'}]},422),({'rows':[{**row(),'subject_external_ref':'not-in-this-tenant'}]},422),({'rows':[{**row(),'observed_at':'2026-02-30T00:00:00Z'}]},422),({'tenant_id':newid()},400),({'source':'forged-source'},400),({'profile_id':newid()},400),({'rows':[{**row(),'observed_at':'tomorrow'}]},422)]
    for patch,expected in badtests:
        status,result,_=ingest({**payload(),**patch});assert status==expected,(patch.keys(),status,result)
    # Invalid batch is atomic: its valid first row cannot leak into observations.
    atomic=[row(),{**row(),'unit':'bad'}];status,result,_=ingest(payload(atomic));assert status==422
    assert sql('SELECT count(*) FROM observations WHERE idempotency_key='+literal(atomic[0]['idempotency_key']))=='0'
    # Corrections remain versioned rows, with original history intact.
    original=sql('SELECT id FROM observations WHERE idempotency_key='+literal(p['rows'][2]['idempotency_key']))
    correction={**row(-2,'45'),'corrects_observation_id':original}
    assert ingest(payload([correction]))[0]==200
    assert sql('SELECT count(*) FROM observations WHERE id='+literal(original))=='1'
    # Concurrent requests serialize under the same tenant lock and reuse one request/batch.
    _,parallel,_=credential();parallel_payload=payload([row(-1,'40')]);parallel_op=newid()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:ingest(parallel_payload,parallel['secret'],parallel_op),range(8)))
    assert all(r[0]==200 for r in results),[r[0] for r in results]
    assert len({r[1]['batch_id'] for r in results})==1
    # Expiration uses the real server clock, no clock manipulation or timestamp backfill.
    _,expired,_=credential(expires=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=1)).isoformat());time.sleep(1.1)
    assert ingest(key=expired['secret'])[0]==401
    assert rpc('revoke_ingestion_credential',{'_tenant_id':tenant,'_credential_id':c['id']},'operator')[0]==403
    _,rotated,_=credential(rotate=c['id']);assert ingest(p,key=c['secret'],op=op)[0]==401
    assert ingest(p,key=rotated['secret'],op=op)[1]['batch_id']==batch
    assert rpc('revoke_ingestion_credential',{'_tenant_id':tenant,'_credential_id':rotated['id']})[0]==204
    assert ingest(key=rotated['secret'])[0]==401
    assert ingest(key='cw_ingest_v1_'+newid()+'.'+'0'*64)[0]==401
    # Real minute quota. If near the bucket boundary, wait at most two seconds.
    if dt.datetime.now(dt.timezone.utc).second>=58:time.sleep(2.1)
    _,limited,_=credential()
    for i in range(30):assert ingest({'invalid':True},limited['secret'])[0]==400
    status,result,headers=ingest(key=limited['secret']);assert status==429 and headers.get('Retry-After'),(status,result)
    assert ingest(key=limited['secret'])[0]==429
    assert sql("SELECT count(*) FROM ingestion_api_events WHERE credential_id="+literal(limited['id'])+" AND code='rate_limited'")=='1'
    # Unknown tenant cannot be selected by the caller; a real foreign customer reference is rejected.
    other=json.loads(Path('e2e/fixtures.json').read_text())
    foreign_ref=sql('SELECT external_ref FROM subjects WHERE tenant_id<>'+literal(tenant)+' ORDER BY id LIMIT 1')
    _,foreign_key,_=credential();assert ingest(payload([{**row(),'subject_external_ref':foreign_ref}]),foreign_key['secret'])[0]==422
    s,b_key,_=rpc('create_ingestion_credential',{'_tenant_id':other['tenantB'],'_name':'[SYNTHETIC] B isolated key','_source':source,'_expires_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),'_operation_id':newid()},'ownerB');assert s==200
    secrets.append(b_key['secret'])
    assert ingest(payload(),b_key['secret'])[0]==400,'B credential cannot select A profile or customer'
    assert rest('/rest/v1/ingestion_credentials?select=id&tenant_id=eq.'+other['tenantB'],'admin',None,'GET')[1]==[]
    assert rpc('revoke_ingestion_credential',{'_tenant_id':other['tenantB'],'_credential_id':b_key['id']})[0]==403
    assert snapshot()==before,'Ingestion must not execute C02-Core/C10 or mutate histories'
    # Explicit HUMAN analysis can consume the API's normal C01 observations.
    status,run,_=rpc('run_deterioration_analysis',{'_tenant_id':tenant,'_subject_id':subject,'_expected_profile_id':profile,'_as_of':date(0)});assert status==200
    status,bundle,_=rpc('build_evidence_bundle',{'_tenant_id':tenant,'_run_id':run['run_id']});assert status==200 and bundle['status']=='built',(status,bundle)
    assert int(sql('SELECT count(*) FROM c03_refs WHERE bundle_id='+literal(bundle['bundle_id'])))>0
    after=snapshot()
    assert all(after[i]==before[i] for i,t in enumerate(tables) if t.startswith(('cw_','c04_'))),'Explicit C02/C03 must not change C04/Core/C05-C10'
    # A later real HTTPS API measurement remains unanalysed for monitoring; no automatic C02/Core work.
    status,new_measurement,_=ingest(payload([row(-1,'65')]),foreign_key['secret']);assert status==200
    assert snapshot()==after,'New API measurement must not automatically analyse or change cases'
    # Private engine and all writes are denied, even to authenticated users.
    assert rest('/rest/v1/rpc/_c01_import',body={'_tenant_id':tenant})[0] in (401,403,404)
    assert rest('/rest/v1/observations',body={'tenant_id':tenant})[0]==403
    assert rest('/rest/v1/ingestion_credentials',body={'tenant_id':tenant})[0]==403
    for t in ['ingestion_api_requests','ingestion_api_events']:
        assert rest('/rest/v1/'+t,body={'tenant_id':tenant})[0]==403
    assert sql("SELECT bool_and(relrowsecurity) FROM pg_class WHERE relname IN ('ingestion_credentials','ingestion_api_requests','ingestion_api_events')")=='t'
    assert sql("SELECT has_function_privilege('anon','public._c01_import(uuid,uuid,text,timestamptz,timestamptz,boolean,text,jsonb,uuid)','EXECUTE')")=='f'
    # No literal integration secrets persisted in public tables or audit.
    dump=sql("SELECT jsonb_agg(to_jsonb(x)) FROM ingestion_credentials x")+sql("SELECT jsonb_agg(to_jsonb(x)) FROM ingestion_api_events x")+sql("SELECT jsonb_agg(to_jsonb(x)) FROM ingestion_api_requests x")+sql("SELECT jsonb_agg(to_jsonb(x)) FROM audit_log x")
    assert all(secret not in dump for secret in secrets)
    Path('e2e/api-fixtures.json').write_text(json.dumps({'tenant':tenant,'subject':subject,'batch':batch}))
    print('PASS: local HTTPS, real GoTrue/RLS, C01 shared CSV/API engine, immutable provenance, idempotence/conflicts, corrections, atomicity, two tenants, role ACLs, expiry/revocation/rotation, concurrency, quota, C02/C03 consumption, unchanged Core/C04-C10. Hosted deployment NOT tested.')
finally:
    server.terminate();server.wait(timeout=10);log.close()
