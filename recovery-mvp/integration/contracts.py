"""Test/export contract only. No production API, UI or business engine logic."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit,parse_qs

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT/'api'/'openapi.json'
OPENAPI = json.loads(OPENAPI_PATH.read_text())


class ContractError(ValueError):
    pass


def validate(schema, value):
    # Local references only: schema validation must never fetch remote URLs.
    wrapped = dict(schema, components=OPENAPI['components'])
    def local_refs(value):
        if isinstance(value,dict):
            if '$ref' in value and not value['$ref'].startswith('#/'):
                raise ContractError('External schema references are forbidden')
            for child in value.values(): local_refs(child)
        elif isinstance(value,list):
            for child in value: local_refs(child)
    local_refs(wrapped)
    errors = list(Draft202012Validator(wrapped,format_checker=FormatChecker()).iter_errors(value))
    if errors:
        error = errors[0]
        # Never format a ValidationError: it may embed a password/token/raw instance.
        raise ContractError('Contract rejected at /'+'/'.join(map(str,error.absolute_path)))


def exact(obj, keys):
    if not isinstance(obj,dict) or set(obj) != set(keys.split()):
        raise ContractError('Unexpected object fields')


def operation_spec(method, path):
    route = urlsplit(path).path
    for template, item in OPENAPI['paths'].items():
        pattern = re.sub(r'\{[^}]+\}',r'[^/]+',template)
        if re.fullmatch(pattern,route) and method.lower() in item:
            return item[method.lower()]
    return None


def validate_record(record):
    exact(record,'id actor request response transport_error')
    exact(record['request'],'method path json')
    if record['transport_error'] is not None:
        if record['response'] is not None or record['transport_error'] != 'connection_refused':
            raise ContractError('Network failure is not an HTTP response')
        return
    exact(record['response'],'status json')
    status, body = record['response']['status'],record['response']['json']
    method,path = record['request']['method'],record['request']['path']
    spec = operation_spec(method,path)
    if spec is None:
        if not (path=='/v1/not-a-route' and status==404):
            raise ContractError('Undocumented endpoint')
    else:
        response = spec['responses'].get(str(status))
        if response is None:
            raise ContractError('Undocumented HTTP status')
        if '$ref' in response:
            response = OPENAPI['components']['responses'][response['$ref'].split('/')[-1]]
        schema = response.get('content',{}).get('application/json',{}).get('schema')
        if schema:
            validate(schema,body)
        request_schema = spec.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema')
        # Intentional negative envelope (extra field) is the only invalid OpenAPI request.
        negative = record['id']=='invalid-envelope-422'
        if request_schema:
            if negative:
                try: validate(request_schema,record['request']['json'])
                except ContractError: pass
                else: raise ContractError('Negative request must violate OpenAPI')
            else: validate(request_schema,record['request']['json'])
        if urlsplit(path).path.endswith('/clients'):
            query=parse_qs(urlsplit(path).query,keep_blank_values=True)
            parameters={p['name']:p['schema'] for p in spec.get('parameters',[]) if p['in']=='query'}
            def validate_query():
                if not set(query)<=parameters.keys() or any(len(v)!=1 for v in query.values()):
                    raise ContractError('Invalid query parameters')
                for name,values in query.items():
                    schema=parameters[name]; value=values[0]
                    if schema['type']=='integer':
                        if not re.fullmatch('[1-9][0-9]*',value): raise ContractError('Invalid query integer')
                        value=int(value)
                    validate(schema,value)
            if record['id']=='directory-invalid-limit-422':
                try: validate_query()
                except ContractError: pass
                else: raise ContractError('Negative query must violate OpenAPI')
            else: validate_query()
    if status==204:
        if body is not None: raise ContractError('204 must have no JSON body')
    elif isinstance(body,dict) and 'error' in body:
        exact(body,'error'); exact(body['error'],'code')
        if status<400 or not isinstance(body['error']['code'],str): raise ContractError('Invalid HTTP error')
    elif path=='/v1/sessions':
        exact(body,'access_token token_type expires_in demo')
        if status!=201 or not re.fullmatch(r'<SESSION:[a-z]+:[0-9]+>',body['access_token']):
            raise ContractError('Only typed session placeholders may be exported')
    elif path=='/v1/session':
        exact(body,'username principal operations clients company_tenants')
    elif path.endswith('/clients') or '/clients?' in path:
        exact(body,'data next_cursor demo')
        for client in body['data']:
            if not client['display_name'].startswith('SYNTHETIC'):
                raise ContractError('Only explicitly synthetic names may be exported')
    elif path.endswith('/operations'):
        exact(body,'data demo'); validate_receipt(body['data'])
    elif path.endswith('/journey'):
        exact(body,'data demo'); validate_journey(body['data'])
    else:
        raise ContractError('Missing strict integration contract')


def validate_receipt(receipt):
    exact(receipt,'tenant_id client_id request_id operation arguments status result actor recorded_at')
    if receipt['status'] not in ('completed','error'):
        raise ContractError('blocked is a business result, never a receipt status')
    if receipt['status']=='error':
        exact(receipt['result'],'sqlstate code')
        if receipt['result']['code']!='engine_rejected': raise ContractError('Unsanitized engine error')
    if receipt['operation']=='intervene' and receipt['status']=='completed':
        if receipt['result']['status'] not in ('blocked','executed','failed'):
            raise ContractError('Unknown intervention business state')
    if receipt['operation']=='evaluate_recovery' and receipt['status']=='completed':
        result=receipt['result']['result']
        if result['status'] not in ('recuperacao_completa','recuperacao_parcial','ausencia_de_recuperacao','resultado_inconclusivo'):
            raise ContractError('Unknown recovery state')
        if result['causal_attribution']!='not_established' or result['independent_verification']!='not_established':
            raise ContractError('Unsupported causal/independent verification claim')
        for key in ('execution_succeeded','improvement_observed','minimum_met','baseline_met'):
            if result[key] is not None and type(result[key]) is not bool:
                raise ContractError('Invalid recovery flag')


def validate_journey(journey):
    exact(journey,'contract_version tenant_id client_id authorization_basis causal_attribution contracts sources evidence_history detections investigations decisions executions recovery_plans operations work_items')
    if journey['contract_version']!='f06-v1' or journey['causal_attribution']!='not_established' or journey['authorization_basis']!='engine_checks_required_at_execution':
        raise ContractError('Unknown journey version or authorization semantics')
    for key in ('contracts','sources','evidence_history','detections','investigations','decisions','executions','recovery_plans','operations','work_items'):
        if not isinstance(journey[key],list): raise ContractError('Expected journey array')
    for receipt in journey['operations']:
        validate_receipt(receipt)
    for investigation in journey['investigations']:
        result=investigation.get('result')
        if result is not None and result['independent_verification']!='not_established':
            raise ContractError('Independent verification not established')


def source_hashes():
    paths=[OPENAPI_PATH,ROOT/'ORCHESTRATION.md',ROOT/'RECOVERY.md',ROOT/'INTERVENTION.md',ROOT/'cloud-demo'/'scenario.py']
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def first_difference(expected, actual, path=''):
    """Never dump either document on failure: only a JSON pointer, no secret values."""
    if type(expected) is not type(actual): return path or '/'
    if isinstance(expected,dict):
        if expected.keys()!=actual.keys(): return path or '/'
        for key in expected:
            result=first_difference(expected[key],actual[key],path+'/'+str(key).replace('~','~0').replace('/','~1'))
            if result is not None: return result
    elif isinstance(expected,list):
        if len(expected)!=len(actual): return path or '/'
        for index,(left,right) in enumerate(zip(expected,actual)):
            result=first_difference(left,right,path+'/'+str(index))
            if result is not None: return result
    elif expected!=actual: return path or '/'
    return None


def fixture_difference(expected, actual):
    """Strict structural/value comparison with bijective bindings for declared volatile slots.
    Fixed tenant/client IDs, source hashes, content digests and business windows are exact.
    Clock metadata, generated UUIDs and input fingerprints preserve reference identity.
    """
    bindings={}; inverse={}
    uuid_pattern=re.compile(r'00000000-0000-4000-8000-[0-9a-f]{12}')
    date_pattern=re.compile(r'2025-01-01T[^ ]+[+]00:00')
    business_times={'baseline_start','baseline_end','period_start','period_end','assessment_at'}
    def visit(left,right,path='',key=''):
        if type(left) is not type(right): return path or '/'
        if isinstance(left,dict):
            if left.keys()!=right.keys(): return path or '/'
            for child in left:
                diff=visit(left[child],right[child],path+'/'+child.replace('~','~0').replace('/','~1'),child)
                if diff is not None: return diff
        elif isinstance(left,list):
            if len(left)!=len(right): return path or '/'
            for n,(a,b) in enumerate(zip(left,right)):
                diff=visit(a,b,path+'/'+str(n),key)
                if diff is not None: return diff
        elif isinstance(left,str):
            pattern=uuid_pattern if uuid_pattern.fullmatch(left) else date_pattern if key not in business_times and date_pattern.fullmatch(left) else re.compile('[0-9a-f]{64}') if key in {'input_hash','request_key'} else None
            if pattern:
                if not pattern.fullmatch(right): return path or '/'
                category='uuid' if pattern is uuid_pattern else 'time' if pattern is date_pattern else 'hash'
                if bindings.get((category,left),right)!=right or inverse.get((category,right),left)!=left:
                    return path or '/'
                bindings[category,left]=right; inverse[category,right]=left
            elif left!=right: return path or '/'
        elif left!=right: return path or '/'
        return None
    return visit(expected,actual)
