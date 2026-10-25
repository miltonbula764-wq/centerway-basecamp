"""Declarative SaaS contract v1. No inference, collection, evaluation or execution."""
from datetime import datetime, timezone
import math
import re

from .http_contract import strict_json
from .store import encode

MAX_BYTES = 65536
IDENTIFIER = r'[a-z0-9][a-z0-9_-]{0,63}'
FIELD = r'[a-zA-Z][a-zA-Z0-9_]{0,63}'
TYPES = ('string', 'number', 'integer', 'boolean', 'timestamp')


def reject(path):
    # Never echo supplied content (which could contain an accidental secret).
    raise ValueError('Invalid integration configuration: '+path)


def shape(value, keys, path):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        reject(path)


def text(value, path, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        reject(path)


def identifier(value, path):
    if not isinstance(value, str) or not re.fullmatch(IDENTIFIER, value, re.ASCII):
        reject(path)


def timestamp(value, path):
    text(value, path, 40)
    if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)',value):
        reject(path)
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:
        reject(path)
    if parsed.utcoffset()!=timezone.utc.utcoffset(parsed): reject(path)


def rows(value, path, minimum=0):
    if not isinstance(value, list) or not minimum<=len(value)<=100:
        reject(path)
    return value


def indexed(value, keys, path):
    result={}
    for item in rows(value,path):
        shape(item, keys, path)
        identifier(item['id'],path+'.id')
        if item['id'] in result: reject(path+'.duplicate')
        text(item['description'],path+'.description')
        result[item['id']]=item
    return result


def refs(value, target, path):
    seen=set()
    for ref in rows(value,path):
        identifier(ref,path)
        if ref not in target or ref in seen: reject(path)
        seen.add(ref)


def fields(value, path):
    result={}
    for item in rows(value,path):
        shape(item,'name type required',path)
        name=item['name']
        if not isinstance(name,str) or not re.fullmatch(FIELD,name,re.ASCII) or name in result:
            reject(path+'.name')
        if item['type'] not in TYPES or type(item['required']) is not bool: reject(path+'.type')
        result[name]=item
    return result


def criteria(value, evidence, path, minimum):
    for item in rows(value,path,minimum):
        if not isinstance(item,dict): reject(path)
        operator=item.get('operator')
        shape(item,'evidence_ref field operator' if operator=='exists' else 'evidence_ref field operator value',path)
        identifier(item['evidence_ref'],path+'.evidence_ref')
        source=evidence.get(item['evidence_ref'])
        if not source or source['availability']!='declared': reject(path+'.evidence_ref')
        available=fields(source['fields'],path+'.fields')
        field=item['field']
        if not isinstance(field,str) or field not in available: reject(path+'.field')
        if operator not in ('exists','eq','ne','lt','lte','gt','gte'): reject(path+'.operator')
        if operator=='exists': continue
        kind=available[field]['type'];value=item['value']
        if kind=='boolean': valid=type(value) is bool
        elif kind=='integer': valid=type(value) is int and abs(value)<=2**53-1
        elif kind=='number': valid=type(value) in (int,float) and abs(value)<=2**53-1 and math.isfinite(value)
        else:
            text(value,path+'.value')
            if kind=='timestamp': timestamp(value,path+'.value')
            valid=True
        if not valid or (operator not in ('eq','ne') and kind not in ('integer','number','timestamp')):
            reject(path+'.value')


def validate(config):
    """Validate and return a detached canonical document; no defaults or fetched data."""
    try:
        payload=encode(config).encode('utf-8')
    except (TypeError,ValueError,RecursionError):
        reject('json')
    if len(payload)>MAX_BYTES: reject('size')
    config=strict_json(payload)
    shape(config,'schema_version tenant data_classification provenance product customers value_goals metrics events evidence capabilities','root')
    if type(config['schema_version']) is not int or config['schema_version']!=1: reject('schema_version')
    identifier(config['tenant'],'tenant')
    if config['data_classification'] not in ('synthetic','declared'): reject('data_classification')
    provenance=config['provenance']
    shape(provenance,'source_ref supplied_by recorded_at','provenance')
    text(provenance['source_ref'],'provenance.source_ref',256)
    text(provenance['supplied_by'],'provenance.supplied_by',128)
    timestamp(provenance['recorded_at'],'provenance.recorded_at')
    shape(config['product'],'name description','product')
    text(config['product']['name'],'product.name',128);text(config['product']['description'],'product.description')
    shape(config['customers'],'entity id_field description','customers')
    text(config['customers']['entity'],'customers.entity',128)
    text(config['customers']['description'],'customers.description')
    id_field=config['customers']['id_field']
    if not isinstance(id_field,str) or not re.fullmatch(FIELD,id_field,re.ASCII): reject('customers.id_field')
    events=indexed(config['events'],'id description source_ref customer_id_field fields','events')
    for event in events.values():
        text(event['source_ref'],'events.source_ref',256)
        available=fields(event['fields'],'events.fields')
        customer_field=event['customer_id_field']
        if not isinstance(customer_field,str) or customer_field not in available or available[customer_field]['type']!='string' or not available[customer_field]['required']:
            reject('events.customer_id_field')
    metrics=indexed(config['metrics'],'id description unit value_type source_ref event_refs','metrics')
    for metric in metrics.values():
        text(metric['unit'],'metrics.unit',64);text(metric['source_ref'],'metrics.source_ref',256)
        if metric['value_type'] not in ('integer','number'): reject('metrics.value_type')
        refs(metric['event_refs'],events,'metrics.event_refs')
    evidence=indexed(config['evidence'],'id description kind source_ref availability event_refs metric_refs fields','evidence')
    for item in evidence.values():
        if item['kind'] not in ('event','metric','document','state') or item['availability'] not in ('declared','unavailable'):
            reject('evidence.kind/availability')
        text(item['source_ref'],'evidence.source_ref',256)
        refs(item['event_refs'],events,'evidence.event_refs');refs(item['metric_refs'],metrics,'evidence.metric_refs')
        fields(item['fields'],'evidence.fields')
        if item['kind']=='event' and not item['event_refs']: reject('evidence.event_refs')
        if item['kind']=='metric' and not item['metric_refs']: reject('evidence.metric_refs')
    goals=indexed(config['value_goals'],'id description metric_refs evidence_refs','value_goals')
    for goal in goals.values():
        refs(goal['metric_refs'],metrics,'value_goals.metric_refs');refs(goal['evidence_refs'],evidence,'value_goals.evidence_refs')
        if not goal['metric_refs'] and not goal['evidence_refs']: reject('value_goals.unmeasurable')
    capabilities=indexed(config['capabilities'],'id description conditions permissions verification','capabilities')
    for capability in capabilities.values():
        criteria(capability['conditions'],evidence,'capabilities.conditions',1)
        permissions=capability['permissions']
        shape(permissions,'required_role requires_human_approval','capabilities.permissions')
        if permissions['required_role']!='operator' or type(permissions['requires_human_approval']) is not bool:
            reject('capabilities.permissions')
        verification=capability['verification']
        shape(verification,'operational value value_goal_refs','capabilities.verification')
        criteria(verification['operational'],evidence,'capabilities.verification.operational',1)
        criteria(verification['value'],evidence,'capabilities.verification.value',0)
        refs(verification['value_goal_refs'],goals,'capabilities.verification.value_goal_refs')
        selected=[goals[ref] for ref in verification['value_goal_refs']]
        def linked(criterion,goal):
            ref=criterion['evidence_ref']
            return ref in goal['evidence_refs'] or bool(set(evidence[ref]['metric_refs']) & set(goal['metric_refs']))
        if any(not any(linked(c,g) for g in selected) for c in verification['value']):
            reject('capabilities.verification.value.unlinked_evidence')
        if any(not any(linked(c,g) for c in verification['value']) for g in selected):
            reject('capabilities.verification.value.unmeasured_goal')
    return config


def load(path):
    with open(path,'rb') as source:
        payload=source.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES: reject('size')
    try:
        return validate(strict_json(payload))
    except (RecursionError,UnicodeError):
        reject('json')
