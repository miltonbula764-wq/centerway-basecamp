"""Capture sanitized examples from a fresh real C03 stack, never from external hosts."""
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'cloud-demo'))
from runtime import PersistentDemo
from scenario import Scenario, now, uid
from demo.provision import T,B,C,C2,BC
from contracts import validate_record, ContractError, source_hashes, fixture_difference
from sanitize import Sanitizer


class CaptureScenario(Scenario):
    def __init__(self,demo):
        super().__init__(demo)
        from psycopg.conninfo import conninfo_to_dict
        secrets=list(demo.credentials.values())
        for user in demo.config['users'].values():
            secrets.extend([user['dsn'],user['password_hash'],conninfo_to_dict(user['dsn'])['password']])
        self.sanitizer=Sanitizer(secrets)
        self.records=[]; self.counts=Counter(); self.operation_counts=Counter(); self.uncertain=False

    def request(self,method,path,data=None,user='alice',*,case=None):
        status,body=super().request(method,path,data,user)
        kind=data['operation'] if method=='POST' and path.endswith('/operations') and isinstance(data,dict) and 'operation' in data else method.lower()+'-'+path.split('?')[0].split('/')[-1]
        self.counts[kind]+=1
        ident=case or f'{kind}-{self.counts[kind]:02}'
        record=self.sanitizer.record(ident,user,method,path,data,status,body)
        validate_record(record)
        self.records.append(record)
        return status,body

    def login(self,user):
        super().login(user)
        self.request('GET','/v1/session',user=user,case=f'session-{user}-{self.sanitizer.logins[user]}')

    def journey(self,case):
        return self.request('GET',f'/v1/tenants/{T}/clients/{C}/journey',case=case)

    def command(self,operation,arguments,user='alice',key=None):
        result,payload=super().command(operation,arguments,user,key)
        self.operation_counts[operation]+=1
        n=self.operation_counts[operation]
        if operation in {'detect','open_investigation','investigate','intervene','evaluate_recovery'} or (operation=='append_value' and n==1):
            self.journey(f'journey-after-{operation}-{n}')
        return result,payload

    def investigation(self,inv,kind,data,user='alice'):
        # Additional test-only checkpoint: ask unchanged F03/F04 before any review exists.
        if kind=='verification' and not self.uncertain:
            self.uncertain=True
            report,_=self.command('investigate',dict(investigation_id=inv,as_of=now()))
            blocked,_=self.command('intervene',dict(investigation_id=inv,report_id=report['id']))
            if report['result']['status']!='inconclusivo' or blocked['status']!='blocked':
                raise ContractError('Missing-evidence checkpoint must not authorize execution')
        return super().investigation(inv,kind,data,user)


def require(status,expected):
    if status!=expected: raise ContractError('Unexpected live HTTP outcome')


def capture(caddy):
    with tempfile.TemporaryDirectory(prefix='centerway-handoff-') as temporary:
        state=Path(temporary)/'state'
        demo=PersistentDemo(state,caddy)
        try:
            demo.initialize(); demo.__enter__()
            client=CaptureScenario(demo)
            directory=f'/v1/tenants/{T}/clients'
            route=f'{directory}/{C}/operations'
            require(client.request('GET',directory,case='authentication-required-401')[0],401)
            for user in ('reader','bob','alice'): client.login(user)
            client.journey('journey-initial')
            result=client.run()  # Original C03 fixture/motors, not a hand-built response.
            for user in ('alice','reviewer','reader'):
                require(client.request('GET',directory,user=user,case=f'directory-{user}')[0],200)
            require(client.request('GET',f'/v1/tenants/{B}/clients',user='bob',case='directory-bob')[0],200)
            require(client.request('GET',directory,user='bob',case='bob-denied-company-a-403')[0],403)
            require(client.request('GET',f'/v1/tenants/{B}/clients',user='alice',case='alice-denied-company-b-403')[0],403)
            require(client.request('GET',f'{directory}/{C2}/journey',user='reader',case='reader-denied-client-403')[0],403)
            for user in ('reader','reviewer'):
                require(client.request('POST',route,result['intervention_request'],user=user,case=f'{user}-denied-intervention-403')[0],403)
            # Same committed receipt; then same key with conflicting content. Never issue a new intervention key.
            require(client.request('POST',route,result['intervention_request'],case='intervention-idempotent-replay')[0],200)
            changed=copy.deepcopy(result['intervention_request']); changed['arguments']['report_id']=uid()
            require(client.request('POST',route,changed,case='idempotency-conflict-409')[0],409)
            invalid=dict(request_id=uid(),operation='append_value',arguments=dict(kind='source',id=uid(),expected_revision=0,
                reason='SYNTHETIC intentionally invalid source fixture',data={}))
            require(client.request('POST',route,invalid,case='engine-error-receipt-422')[0],422)
            invalid_envelope=dict(invalid,unexpected=True)
            require(client.request('POST',route,invalid_envelope,case='invalid-envelope-422')[0],422)
            require(client.request('GET','/v1/not-a-route',case='unknown-route-404')[0],404)
            client.journey('journey-with-error-receipt')
            import psycopg
            with psycopg.connect(demo.config['users']['alice']['dsn']) as conn:
                if conn.execute('SELECT count(*) FROM centerway.intervention_executions WHERE decision_id=%s',(result['decision_id'],)).fetchone()[0]!=1:
                    raise ContractError('Duplicate execution')
                if conn.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s",(result['intervention_request']['request_id'],)).fetchone()[0]!=1:
                    raise ContractError('Duplicate receipt audit')
            with psycopg.connect(demo.config['users']['bob']['dsn']) as conn:
                if conn.execute('SELECT session_user::text').fetchone()[0]!='http_bob' or conn.execute('SELECT count(*) FROM centerway.recovery_runs WHERE tenant_id=%s',(T,)).fetchone()[0]!=0:
                    raise ContractError('PostgreSQL identity/isolation violated')
            # EXPLICIT TEST-ONLY grant: existing A2 is added to reader's temporary HTTP scope.
            # This is operator configuration, not a product endpoint or a grant in the shipped C03.
            config=copy.deepcopy(demo.config); config['users']['reader']['clients'][T].append(C2)
            (state/'config.json').write_text(json.dumps(config))
            demo.stop(demo.api); demo.start_api()
            require(client.request('GET',directory,user='reader',case='changed-scope-invalidates-session-401')[0],401)
            client.login('reader')
            status,first=client.request('GET',directory+'?limit=1',user='reader',case='directory-page-1')
            require(status,200)
            if first['next_cursor']!=C: raise ContractError('Incorrect first cursor')
            status,last=client.request('GET',directory+'?limit=1&after='+first['next_cursor'],user='reader',case='directory-page-2')
            require(status,200)
            if last['next_cursor'] is not None or [row['client_id'] for row in first['data']+last['data']]!=[C,C2]:
                raise ContractError('Pagination missing/duplicated authorized clients')
            require(client.request('GET',directory+'?after='+C2,user='reader',case='directory-page-empty')[0],200)
            require(client.request('GET',directory+'?limit=101',user='reader',case='directory-invalid-limit-422')[0],422)
            require(client.request('DELETE','/v1/session',user='reader',case='logout-204')[0],204)
            require(client.request('GET',directory,user='reader',case='revoked-session-401')[0],401)
            demo.run('docker','stop',demo.container)
            try:
                require(client.request('GET',directory,case='database-unavailable-503')[0],503)
            finally:
                demo.run('docker','start',demo.container); demo.ready_database()
            demo.stop(demo.api)
            try:
                require(client.request('GET',directory,case='api-unavailable-503')[0],503)
            finally: demo.start_api()
            demo.stop(demo.proxy)
            try:
                client.request('GET',directory,case='must-not-exist')
            except ConnectionRefusedError:
                record=client.sanitizer.record('network-failure','alice','GET',directory,None,None,None,'connection_refused')
                validate_record(record); client.records.append(record)
            else: raise ContractError('Stopped proxy must yield network failure, not synthetic HTTP')
            document=dict(fixture_version='l03-prep-v1',synthetic_only=True,source='real-local-c03-https-api',
                base_commit='eeae52ef4d1fbf3bdc524299203098fe75f6badd',contracts=source_hashes(),
                sanitization='typed-placeholders-v1',cases=client.sanitizer.finalize_times(client.records))
            client.sanitizer.secret_safe(document)
            return document
        finally:
            demo.close()
            manifest=state/'manifest.json'
            if manifest.exists():
                m=json.loads(manifest.read_text())
                subprocess.run(['docker','rm','-f',m['container']],capture_output=True)
                for volume in (m['volume'],m['volume']+'-tls'):
                    subprocess.run(['docker','volume','rm',volume],capture_output=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caddy',required=True)
    parser.add_argument('--write',action='store_true',help='Regenerate committed sanitized fixtures after explicit review')
    args=parser.parse_args()
    result=capture(args.caddy)
    target=HERE/'fixtures'/'v1'/'capture.json'
    if args.write:
        target.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
        from matrix import render
        target.with_name('CASE_MATRIX.md').write_text(render(result))
        print(f'SYNTHETIC sanitized cases exported: {len(result["cases"])}')
    else:
        difference=fixture_difference(json.loads(target.read_text()),result)
        if difference is not None: raise ContractError('Live capture differs at '+difference)
        print('Canonical fixtures match actual local C03 API')
