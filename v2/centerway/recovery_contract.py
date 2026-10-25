"""Inactive C06 v1: explicit windows over pinned catalogue targets, no actions."""
from datetime import datetime, timedelta
from fractions import Fraction

from .evidence import utc
from .http_contract import strict_json
from .integration_contract import fields, identifier, shape, text, timestamp
from .integrations import canonical
from .investigation_contract import COMPARISONS

ALGORITHM='c06-recovery-v1'


def instant(value): return datetime.fromisoformat(utc(value).replace('Z','+00:00'))


def fraction(value): return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def validate(document,binding,dispatch_at):
    raw=canonical(document).encode('utf-8')
    if len(raw)>65536: raise ValueError('C06 plan exceeds 65536 bytes.')
    document=strict_json(raw)
    shape(document,'schema_version tenant customer execution_id config_version capability_id provenance checks','plan')
    if type(document['schema_version']) is not int or document['schema_version']!=1: raise ValueError('Unknown C06 schema.')
    for key in ('tenant','execution_id','capability_id'): identifier(document[key],key)
    if any(document[k]!=binding[k] for k in ('tenant','customer','execution_id','config_version','capability_id')): raise ValueError('C06 plan scope mismatch.')
    if type(document['config_version']) is not int: raise ValueError('Explicit configuration version required.')
    provenance=document['provenance'];shape(provenance,'source_ref supplied_by recorded_at','provenance')
    text(provenance['source_ref'],'source_ref',256);text(provenance['supplied_by'],'supplied_by',128);timestamp(provenance['recorded_at'],'recorded_at')
    checks=document['checks'];verification=binding['capability']['verification']
    if not isinstance(checks,list) or not 1<=len(checks)<=100: raise ValueError('1–100 explicit checks required.')
    total_buckets=0
    required={(d,i) for d in ('operational','value') for i in range(len(verification[d]))};seen=set()
    definitions={d['id']:d for d in binding['configuration']['evidence']}
    for check in checks:
        shape(check,'dimension criterion_index sampling aggregation method coverage before after','check')
        dimension,index=check['dimension'],check['criterion_index']
        if not isinstance(dimension,str) or type(index) is not int or (dimension,index) not in required or (dimension,index) in seen: raise ValueError('Unknown or duplicate declared target.')
        seen.add((dimension,index));target=verification[dimension][index];definition=definitions[target['evidence_ref']]
        kind=fields(definition['fields'],'fields')[target['field']]['type']
        if check['sampling']!=('period' if definition['kind']=='metric' else 'point'): raise ValueError('Sampling must match the evidence definition.')
        if check['aggregation'] not in ('all','mean','sum','min','max'): raise ValueError('Explicit supported aggregation required.')
        if check['aggregation']!='all' and (kind not in ('integer','number') or target['operator']=='exists'): raise ValueError('Numeric aggregation needs a numeric comparison.')
        if check['method']!='transition_to_target' or check['coverage']!='aligned_complete': raise ValueError('Explicit transition and full coverage required.')
        for name in ('before','after'):
            window=check[name];shape(window,'start end cadence_seconds',name)
            window['start'],window['end']=utc(window['start']),utc(window['end'])
            duration=instant(window['end'])-instant(window['start']);cadence=window['cadence_seconds']
            if type(cadence) is not int or not 1<=cadence<=2**31-1: raise ValueError('Positive integral cadence required.')
            if duration<=timedelta(0) or duration%timedelta(seconds=cadence) or duration//timedelta(seconds=cadence)>1000: raise ValueError('Window requires 1–1000 complete aligned buckets.')
            total_buckets+=duration//timedelta(seconds=cadence)
            if total_buckets>2000: raise ValueError('At most 2000 sample buckets per plan.')
        if instant(check['before']['end'])>instant(dispatch_at) or instant(check['after']['start'])<=instant(dispatch_at): raise ValueError('Windows must be strictly separated by intervention dispatch.')
    if seen!=required: raise ValueError('Every declared operational/value target must be included exactly once.')
    return document


def _window(check,name,target,definition,records,as_of,post_boundary):
    window=check[name];start,end=instant(window['start']),instant(window['end'])
    step=timedelta(seconds=window['cadence_seconds']);count=(end-start)//step
    buckets={(start+i*step,start+(i+1)*step):[] for i in range(count)}
    point_buckets={right:(left,right) for left,right in buckets}
    result={'window':window,'target':target,'evidence_refs':[],'excluded':[],'issues':[],'contradictions':[],'samples':[],
            'aggregate':None,'target_state':'insufficient'}
    if end>instant(as_of): result['issues'].append({'code':'window_not_complete_at_as_of'})
    if name=='after' and start<=instant(post_boundary): result['issues'].append({'code':'window_not_after_receipt_or_dispatch'})
    for row in records:
        if row['kind']!='evidence' or row['definition_id']!=target['evidence_ref']: continue
        occurred=instant(row['occurred_at'])
        left=instant(row['period_start']) if row['period_start'] else None
        right=instant(row['period_end']) if row['period_end'] else None
        overlaps=left<end and right>start if left is not None else start<occurred<=end
        if not overlaps: continue
        ref={'evidence_id':row['id'],'record_hash':row['record_hash'],'source_ref':row['source_ref'],'external_id':row['external_id'],
             'config_version':row['config_version'],'config_hash':row['config_hash'],'occurred_at':row['occurred_at'],
             'period_start':row['period_start'],'period_end':row['period_end'],'received_at':row['received_at'],'actor':row['actor']}
        if occurred>instant(as_of):
            result['excluded'].append({**ref,'code':'observed_after_as_of'});continue
        if name=='after' and (occurred<=instant(post_boundary) or left is not None and left<=instant(post_boundary)):
            result['excluded'].append({**ref,'code':'not_strictly_post_intervention'});continue
        result['evidence_refs'].append(ref)
        key=(left,right) if check['sampling']=='period' else point_buckets.get(occurred)
        if key not in buckets:
            result['issues'].append({'code':'incompatible_sampling','evidence_id':row['id']});continue
        buckets[key].append(row)
    values=[];target_states=[];kind=fields(definition['fields'],'fields')[target['field']]['type']
    for (left,right),group in sorted(buckets.items()):
        if not group:
            result['issues'].append({'code':'missing_sample','start':utc(left.isoformat()),'end':utc(right.isoformat())});continue
        by_field={}
        for row in group:
            for key,value in row['payload'].items(): by_field.setdefault(key,set()).add(canonical(value))
        if any(len(v)>1 for v in by_field.values()):
            result['contradictions'].append({'start':utc(left.isoformat()),'end':utc(right.isoformat()),'evidence_ids':[r['id'] for r in group]});continue
        candidates=[r['payload'][target['field']] for r in group if target['field'] in r['payload']]
        if not candidates:
            result['issues'].append({'code':'missing_field','evidence_ids':[r['id'] for r in group]});continue
        value=candidates[0];values.append(value)
        actual=Fraction(str(value)) if kind in ('integer','number') else utc(value) if kind=='timestamp' else value
        expected=target.get('value')
        if kind in ('integer','number') and expected is not None: expected=Fraction(str(expected))
        elif kind=='timestamp' and expected is not None: expected=utc(expected)
        met=target['operator']=='exists' or COMPARISONS[target['operator']](actual,expected)
        target_states.append(met)
        result['samples'].append({'start':utc(left.isoformat()),'end':utc(right.isoformat()),'value':value,'meets_target':met,'evidence_ids':[r['id'] for r in group]})
    if result['contradictions']: result['target_state']='contradictory'
    elif not result['issues']:
        if check['aggregation']=='all': met=all(target_states)
        else:
            numeric=[Fraction(str(v)) for v in values]
            aggregate={'mean':lambda:sum(numeric,Fraction(0))/len(numeric),'sum':lambda:sum(numeric,Fraction(0)),
                       'min':lambda:min(numeric),'max':lambda:max(numeric)}[check['aggregation']]()
            result['aggregate']=fraction(aggregate);met=COMPARISONS[target['operator']](aggregate,Fraction(str(target['value'])))
        result['target_state']='demonstrated' if met else 'not_demonstrated'
    return result


def assess(document,binding,c05,records,as_of):
    """Pure, reproducible assessment. A receipt is never recovery evidence."""
    document=validate(document,binding,c05['dispatch_at']);as_of=utc(as_of)
    config=binding['configuration'];definitions={d['id']:d for d in config['evidence']}
    if any(r['tenant']!=binding['tenant'] or r['customer']!=binding['customer'] or r['config_version']!=binding['config_version'] for r in records): raise ValueError('Mixed C06 evidence scope.')
    receipt=c05['result'];execution_state='execution_uncertain';reason='no_final_receipt'
    boundary=c05['dispatch_at']
    if receipt:
        boundary=utc(receipt['payload']['created_at'])
        if instant(boundary)<instant(c05['dispatch_at']):
            reason='receipt_temporal_conflict';boundary=c05['dispatch_at']
        elif instant(boundary)>instant(as_of): reason='receipt_after_as_of'
        elif receipt['payload']['status']=='test_applied': execution_state='demonstrated';reason='adapter_reports_test_effect'
        elif receipt['payload']['status']=='failed_no_effect': execution_state='not_demonstrated';reason='adapter_reports_no_effect'
        else: reason='uncertain_receipt'
    results=[]
    for check in document['checks']:
        target=binding['capability']['verification'][check['dimension']][check['criterion_index']]
        windows={name:_window(check,name,target,definitions[target['evidence_ref']],records,as_of,boundary) for name in ('before','after')}
        states={w['target_state'] for w in windows.values()};delta=None
        if 'contradictory' in states: state='contradictory';code='conflicting_evidence'
        elif 'insufficient' in states: state='insufficient';code='incomplete_or_incompatible_windows'
        elif windows['before']['target_state']=='not_demonstrated' and windows['after']['target_state']=='demonstrated': state='demonstrated';code='declared_transition_observed'
        else: state='not_demonstrated';code='target_already_met_before' if windows['before']['target_state']=='demonstrated' else 'target_not_met_after'
        if all(w['aggregate'] is not None for w in windows.values()):
            a,b=(w['aggregate'] for w in (windows['after'],windows['before']))
            delta=fraction(Fraction(int(a['numerator']),int(a['denominator']))-Fraction(int(b['numerator']),int(b['denominator'])))
        results.append({'dimension':check['dimension'],'criterion_index':check['criterion_index'],'criterion':target,
                        'method':check['method'],'aggregation':check['aggregation'],'state':state,'reason_code':code,'windows':windows,'delta':delta})
    dimensions={}
    for dimension in ('operational','value'):
        selected=[r for r in results if r['dimension']==dimension];states={r['state'] for r in selected}
        state='contradictory' if 'contradictory' in states else 'insufficient' if not selected or 'insufficient' in states else 'not_demonstrated' if 'not_demonstrated' in states else 'demonstrated'
        dimensions[dimension]={'state':state,'criterion_indices':[r['criterion_index'] for r in selected],
                               'reason_code':'no_declared_value_criteria' if not selected else 'all_declared_targets_required',
                               'claim_scope':'synthetic_observation_only'}
    states={d['state'] for d in dimensions.values()}
    overall='execution_uncertain' if execution_state=='execution_uncertain' else 'contradictory' if 'contradictory' in states else 'insufficient' if 'insufficient' in states else 'not_demonstrated' if 'not_demonstrated' in states or execution_state=='not_demonstrated' else 'demonstrated'
    return {'algorithm':ALGORITHM,'operational_state':'inactive','assessment_scope':'synthetic_test_only','real_recovery_demonstrated':False,
            'operational_recovered':None,'value_recovered':None,'causal_attribution':'not_established','execution_authorized':False,
            'core_transition_authorized':False,'automatic_closure':False,'external_execution':'blocked',
            'execution':{'state':execution_state,'reason_code':reason,'claim_scope':'test_adapter_receipt_only'},
            'operational_recovery':dimensions['operational'],'value_recovery':dimensions['value'],'criteria_results':results,
            'summary_state':overall,'core_follow_up':'human_review_required' if overall in ('execution_uncertain','contradictory') else 'inactive_observation_only'}
