"""Typed placeholders, never exported live secrets, random IDs, times or fingerprints.
Business scalars, nulls, states, revisions and exact object fields are preserved.
"""
from datetime import datetime,timedelta,timezone
import json
import re
from uuid import UUID

from contracts import ContractError

UUID_RE = re.compile(r'(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])',re.I)
TIME_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$')
FIXED_IDS = {
 'a1000000-0000-0000-0000-000000000001','b1000000-0000-0000-0000-000000000001',
 'a2000000-0000-0000-0000-000000000001','a2000000-0000-0000-0000-000000000002',
 'b2000000-0000-0000-0000-000000000001','a3000000-0000-0000-0000-000000000001',
 'a4000000-0000-0000-0000-000000000001',
}
FORBIDDEN_KEYS={'dsn','password_hash','authorization','cookie','set-cookie','secret','private_key','refresh_token','token','api_key','client_secret'}


class Sanitizer:
    def __init__(self,secrets):
        self.secrets=list(secrets)
        self.ids={}; self.times={}; self.hashes={}; self.logins={}

    def secret_safe(self,value):
        encoded=json.dumps(value,sort_keys=True,ensure_ascii=False)
        if any(secret and secret in encoded for secret in self.secrets):
            raise ContractError('Secret detected; export refused')
        if re.search(r'Bearer\s+\S+|password=|postgres(?:ql)?://|BEGIN (?:EC |RSA )?PRIVATE KEY|[\w.+-]+@[\w.-]+\.[a-z]{2,}',encoded,re.I):
            raise ContractError('Credential or PII pattern detected; export refused')
        def check(x):
            if isinstance(x,dict):
                if any(k.lower() in FORBIDDEN_KEYS for k in x): raise ContractError('Secret field detected')
                for k,v in x.items():
                    if k=='access_token' and (not isinstance(v,str) or not re.fullmatch(r'<SESSION:[a-z]+:[0-9]+>',v)):
                        raise ContractError('Live token detected; export refused')
                    if k=='password' and (not isinstance(v,str) or not re.fullmatch(r'<PASSWORD:[a-z]+>',v)):
                        raise ContractError('Password detected; export refused')
                    check(v)
            elif isinstance(x,list):
                for v in x: check(v)
        check(value)

    def uuid(self,value):
        original=value.lower()
        if original in FIXED_IDS: return original
        if original not in self.ids:
            self.ids[original]=f'00000000-0000-4000-8000-{len(self.ids)+1:012x}'
        return self.ids[original]

    def normalize(self,value,key=''):
        if isinstance(value,dict):
            return {self.normalize(k):self.normalize(v,k) for k,v in sorted(value.items())}
        if isinstance(value,list):
            rows=[self.normalize(v,key) for v in value]
            # These journey collections are keyed records; SQL sorts by ephemeral IDs.
            # No reordering of pagination, detection periods or evidence-reference arrays.
            if key in {'contracts','sources','evidence_history','investigations','work_items','factors','evidence','verifications','recovery_plans'}:
                rows.sort(key=lambda v:json.dumps(v,sort_keys=True))
            return rows
        if isinstance(value,str):
            if TIME_RE.fullmatch(value):
                instant=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
                if instant not in self.times:
                    self.times[instant]=(datetime(2000,1,1,tzinfo=timezone.utc)+timedelta(seconds=len(self.times))).isoformat()
                return self.times[instant]
            if key in {'input_hash','request_key'}:
                if not re.fullmatch('[0-9a-f]{64}',value): raise ContractError('Invalid fingerprint')
                if value not in self.hashes: self.hashes[value]=f'{len(self.hashes)+1:064x}'
                return self.hashes[value]
            return UUID_RE.sub(lambda m:self.uuid(m.group()),value)
        return value

    def record(self,ident,actor,method,path,request_body,status,response_body,transport_error=None):
        import copy
        request_body=copy.deepcopy(request_body); response_body=copy.deepcopy(response_body)
        if method=='POST' and path=='/v1/sessions':
            request_body['password']=f'<PASSWORD:{request_body["username"]}>'
            if status==201:
                token=response_body['access_token']; self.secrets.append(token)
                n=self.logins.get(actor,0)+1; self.logins[actor]=n
                response_body['access_token']=f'<SESSION:{actor}:{n}>'
        record=dict(id=ident,actor=actor,request=dict(method=method,path=path,json=request_body),
            response=None if transport_error else dict(status=status,json=response_body),transport_error=transport_error)
        self.secret_safe(record)
        return self.normalize(record)

    def finalize_times(self, records):
        """Remove clock jitter while retaining chronology and declared equal windows.
        Anchors come from actual contract requests and the actual executed F04 row.
        This is example sanitization, never engine input or a new business conclusion.
        """
        import bisect
        reverse={alias:datetime.fromisoformat(raw) for raw,alias in self.times.items()}
        operations=[r for r in records if r['request']['method']=='POST' and r['request']['path'].endswith('/operations') and r['response'] and r['response']['status']==200]
        contracts=[r['request']['json']['arguments'] for r in operations if r['request']['json']['operation']=='append_value' and r['request']['json']['arguments']['kind']=='contract']
        if len(contracts)!=4: raise ContractError('Unexpected C03 contract windows')
        first=reverse[contracts[0]['data']['baseline_start']]
        base=datetime(2025,1,1,tzinfo=timezone.utc)
        executed=next(r['response']['json']['data']['result'] for r in operations if r['request']['json']['operation']=='intervene' and r['response']['json']['data']['result']['status']=='executed')
        execution=next(e for r in records if r['request']['path'].endswith('/journey') and r['response'] and r['response']['status']==200 for e in r['response']['json']['data']['executions'] if e['id']==executed['execution_id'])
        anchor=reverse[execution['recorded_at']]; canonical_anchor=base+timedelta(minutes=5)
        anchors={anchor:canonical_anchor}
        def put(alias,canonical):
            raw=reverse[alias]
            if raw in anchors and anchors[raw]!=canonical: raise ContractError('Inconsistent timestamp anchors')
            anchors[raw]=canonical
        for args in contracts:
            for key in ('baseline_start','baseline_end','period_start','period_end'):
                alias=args['data'][key]; raw=reverse[alias]
                target=canonical_anchor+(raw-anchor) if key.startswith('period_') and args['expected_revision']>=2 else base+(raw-first)
                put(alias,target)
        for record in records:
            body=record['request']['json']
            if isinstance(body,dict) and body.get('operation')=='append_investigation' and body['arguments']['kind']=='factor':
                alias=body['arguments']['data']['assessment_at']; put(alias,base+(reverse[alias]-first))
        # C03's initial provisioned contract uses fixed 2024 business dates, never wall-clock metadata.
        initial=next(r['response']['json']['data'] for r in records if r['id']=='journey-initial')
        for contract in initial['contracts']:
            for key in ('baseline_start','baseline_end','period_start','period_end'):
                alias=contract[key]; put(alias,reverse[alias])
        boundaries=sorted(anchors)
        if any(anchors[a]>=anchors[b] for a,b in zip(boundaries,boundaries[1:])):
            raise ContractError('Sanitization must preserve chronology')
        groups={}
        for raw in sorted(reverse.values()):
            if raw not in anchors: groups.setdefault(bisect.bisect_left(boundaries,raw),[]).append(raw)
        for position, values in groups.items():
            if position==0:
                right=anchors[boundaries[0]]; left=right-timedelta(days=1)
            elif position==len(boundaries):
                left=anchors[boundaries[-1]]; right=left+timedelta(minutes=1)
            else:
                left=anchors[boundaries[position-1]]; right=anchors[boundaries[position]]
            for n,raw in enumerate(values,1): anchors[raw]=left+(right-left)*n/(len(values)+1)
        replacement={alias:anchors[raw].isoformat() for alias,raw in reverse.items()}
        if len(set(replacement.values()))!=len(replacement): raise ContractError('Timestamp placeholder collision')
        def replace(value):
            if isinstance(value,dict): return {k:replace(v) for k,v in value.items()}
            if isinstance(value,list): return [replace(v) for v in value]
            return replacement.get(value,value) if isinstance(value,str) else value
        return replace(records)
