"""HTTP-only compatibility rules. No product state or authorization lives here."""
import json
from urllib.parse import parse_qs

API_VERSION = '1.2.0'
API_METHODS = {
    '/api/evidence':'POST', '/api/evidence/view':'GET',
    '/api/login':'POST', '/api/logout':'POST', '/api/view':'GET',
    '/api/customers':'POST', '/api/observations':'POST', '/api/advance':'POST',
    '/api/execute':'POST', '/api/verify':'POST', '/api/simulate-usage':'POST',
}
ERROR_CODES = {400:'invalid_request',401:'unauthenticated',403:'forbidden',
               404:'not_found',405:'method_not_allowed',409:'conflict',
               413:'payload_too_large',415:'unsupported_media_type',
               421:'misdirected_request',429:'rate_limited',500:'internal_error',503:'unavailable'}


def view_query(query):
    values = parse_qs(query,keep_blank_values=True,strict_parsing=True,
                      encoding='utf-8',errors='strict',max_num_fields=3)
    if set(values)-{'tenant','customer','case_id'} or any(len(rows)!=1 or not rows[0] or len(rows[0])>128 for rows in values.values()):
        raise ValueError('Invalid or repeated query parameter')
    if ('customer' in values and 'tenant' not in values) or ('case_id' in values and 'customer' not in values):
        raise ValueError('Incomplete scope')
    return tuple(values.get(key,[None])[0] for key in ('tenant','customer','case_id'))


def evidence_query(query):
    values = parse_qs(query,keep_blank_values=True,strict_parsing=True,
                     encoding='utf-8',errors='strict',max_num_fields=6)
    if set(values)-{'tenant','customer','config_version','after','through','limit'} or not {'tenant','customer','config_version'}<=set(values):
        raise ValueError('Explicit evidence scope/configuration required')
    if any(len(v)!=1 or not v[0] or len(v[0])>128 for v in values.values()): raise ValueError('Invalid query')
    result={k:v[0] for k,v in values.items()}
    for key in ('config_version','after','through','limit'):
        if key in result:
            if not result[key].isascii() or not result[key].isdecimal() or len(result[key])>16: raise ValueError('Invalid integer query')
            result[key]=int(result[key])
    return result


def strict_json(payload):
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError('Non-finite JSON number')

    return json.loads(payload.decode('utf-8'),object_pairs_hook=pairs,parse_constant=reject_constant)
