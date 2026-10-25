"""Adaptive C02 v1: explicit numeric criteria, complete aligned samples, no actions."""
from datetime import datetime, timedelta
from fractions import Fraction
import math
import operator

from .evidence import utc
from .http_contract import strict_json
from .integration_contract import fields, identifier, refs, shape, text, timestamp, validate as validate_config
from .integrations import canonical

ALGORITHM = 'c02-adaptive-v1'
COMPARISONS = {'lt':operator.lt,'lte':operator.le,'gt':operator.gt,'gte':operator.ge}


def validate(document, config):
    config=validate_config(config)
    payload=canonical(document).encode('utf-8')
    if len(payload)>65536: raise ValueError('Criteria exceed 65536 bytes.')
    document=strict_json(payload)
    shape(document,'schema_version tenant config_version provenance criteria','criteria_document')
    if type(document['schema_version']) is not int or document['schema_version']!=1: raise ValueError('Unknown criteria schema.')
    identifier(document['tenant'],'tenant')
    if document['tenant']!=config['tenant']: raise ValueError('Criteria/configuration tenant mismatch.')
    version=document['config_version']
    if type(version) is not int or not 1<=version<=2**31-1: raise ValueError('Explicit configuration version required.')
    shape(document['provenance'],'source_ref supplied_by recorded_at','provenance')
    text(document['provenance']['source_ref'],'source_ref',256)
    text(document['provenance']['supplied_by'],'supplied_by',128)
    timestamp(document['provenance']['recorded_at'],'recorded_at')
    criteria=document['criteria']
    if not isinstance(criteria,list) or not 1<=len(criteria)<=100: raise ValueError('Between 1 and 100 explicit criteria required.')
    metrics={d['id']:d for d in config['metrics']};evidence={d['id']:d for d in config['evidence']};goals={d['id']:d for d in config['value_goals']}
    seen=set()
    for criterion in criteria:
        shape(criterion,'id description dimension metric_ref goal_refs evidence_refs source method aggregation comparison threshold threshold_unit window_seconds cadence_seconds coverage','criterion')
        identifier(criterion['id'],'criterion.id');text(criterion['description'],'criterion.description')
        if criterion['id'] in seen: raise ValueError('Duplicate criterion id.')
        seen.add(criterion['id'])
        if criterion['dimension'] not in ('operational','value'): raise ValueError('Explicit dimension required.')
        identifier(criterion['metric_ref'],'metric_ref')
        if criterion['metric_ref'] not in metrics: raise ValueError('Unknown metric reference.')
        metric=metrics[criterion['metric_ref']]
        refs(criterion['goal_refs'],goals,'goal_refs');refs(criterion['evidence_refs'],evidence,'evidence_refs')
        if not criterion['goal_refs'] or not criterion['evidence_refs']: raise ValueError('Explicit goals and evidence required.')
        if any(metric['id'] not in goals[g]['metric_refs'] for g in criterion['goal_refs']): raise ValueError('Goal/metric association missing.')
        if any(evidence[e]['availability']!='declared' or metric['id'] not in evidence[e]['metric_refs'] for e in criterion['evidence_refs']):
            raise ValueError('Evidence unavailable or unrelated to metric.')
        source=criterion['source'];shape(source,'kind definition_id field','source')
        identifier(source['definition_id'],'source.definition_id')
        if source['kind']=='metric':
            if source['definition_id']!=metric['id'] or source['field']!='value': raise ValueError('Invalid metric source.')
        elif source['kind']=='evidence':
            if source['definition_id'] not in criterion['evidence_refs']: raise ValueError('Evidence source not referenced.')
            declared=fields(evidence[source['definition_id']]['fields'],'source.fields')
            if not isinstance(source['field'],str) or source['field'] not in declared or declared[source['field']]['type'] not in ('integer','number'):
                raise ValueError('Explicit numeric evidence field required.')
        else: raise ValueError('Unsupported source kind; events are not inferred into counts.')
        if criterion['dimension']=='value':
            if source['kind']!='evidence' or evidence[source['definition_id']]['kind']!='metric' or any(source['definition_id'] not in goals[g]['evidence_refs'] for g in criterion['goal_refs']):
                raise ValueError('Value loss requires direct numeric goal evidence, not operational/usage inference.')
        if criterion['method'] not in ('threshold','absolute_change','relative_change'): raise ValueError('Unsupported method.')
        if criterion['aggregation'] not in ('mean','sum','min','max') or criterion['comparison'] not in tuple(COMPARISONS):
            raise ValueError('Explicit supported aggregation/comparison required.')
        threshold=criterion['threshold']
        if type(threshold) not in (int,float) or not abs(threshold)<=2**53-1 or not math.isfinite(threshold): raise ValueError('Finite explicit numeric threshold required.')
        if criterion['threshold_unit']!=('ratio' if criterion['method']=='relative_change' else metric['unit']): raise ValueError('Threshold unit mismatch.')
        window,cadence=criterion['window_seconds'],criterion['cadence_seconds']
        if any(type(v) is not int or not 1<=v<=2**31-1 for v in (window,cadence)) or window%cadence:
            raise ValueError('Positive integral window/cadence alignment required.')
        if window//cadence*(1 if criterion['method']=='threshold' else 2)>1000: raise ValueError('At most 1000 sample buckets per criterion.')
        if criterion['coverage']!='aligned_complete': raise ValueError('Explicit complete aligned coverage required.')
    return document


def rational(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator)}


def _collect(records, config, criterion, start, end, observed_through):
    cadence=timedelta(seconds=criterion['cadence_seconds'])
    count=criterion['window_seconds']//criterion['cadence_seconds']
    buckets={(start+i*cadence,start+(i+1)*cadence) for i in range(count)}
    point_buckets={right:(left,right) for left,right in buckets}
    evidence={d['id']:d for d in config['evidence']}
    primary=criterion['source'];sources=[(primary['kind'],primary['definition_id'])]
    sources += [('evidence',ref) for ref in criterion['evidence_refs'] if ('evidence',ref) not in sources]
    used=set();issues=[];primary_values=[];contradictions=[]
    for kind,definition_id in sources:
        grouped={};incompatible=[]
        periodic=kind=='metric' or evidence[definition_id]['kind']=='metric'
        for row in records:
            if row['kind']!=kind or row['definition_id']!=definition_id: continue
            occurred=datetime.fromisoformat(row['occurred_at'].replace('Z','+00:00'))
            if occurred>observed_through: continue  # No future observation can prove a past result.
            if periodic:
                left=datetime.fromisoformat(row['period_start'].replace('Z','+00:00'))
                right=datetime.fromisoformat(row['period_end'].replace('Z','+00:00'))
                if right<=start or left>=end: continue
                key=(left,right)
            else:
                if not start<occurred<=end: continue
                key=point_buckets.get(occurred)
            used.add(row['id'])
            if key not in buckets:
                incompatible.append(row['id']);continue
            grouped.setdefault(key,[]).append(row)
        if incompatible: issues.append({'code':'incompatible_sampling','kind':kind,'definition_id':definition_id,'evidence_ids':sorted(incompatible)})
        present=0
        for (left,right),group in sorted(grouped.items()):
            values={}
            for row in group:
                for field,value in row['payload'].items(): values.setdefault(field,set()).add(canonical(value))
            if any(len(v)>1 for v in values.values()):
                contradictions.append({'kind':kind,'definition_id':definition_id,'start':utc(left.isoformat()),'end':utc(right.isoformat()),'evidence_ids':[r['id'] for r in group]})
            if (kind,definition_id)==(primary['kind'],primary['definition_id']):
                candidates={Fraction(str(r['payload'][primary['field']])) for r in group if primary['field'] in r['payload']}
                if len(candidates)==1: primary_values.append(next(iter(candidates)));present+=1
            else: present+=1
        if present<count: issues.append({'code':'missing_samples','kind':kind,'definition_id':definition_id,'missing_buckets':count-present})
    value=None
    if not issues and not contradictions:
        value={'sum':lambda:sum(primary_values,Fraction(0)),
               'mean':lambda:sum(primary_values,Fraction(0))/len(primary_values),
               'min':lambda:min(primary_values),'max':lambda:max(primary_values)}[criterion['aggregation']]()
    return {'start':utc(start.isoformat()),'end':utc(end.isoformat()),'aggregate':rational(value) if value is not None else None,
            'evidence_ids':sorted(used),'issues':issues,'contradictions':contradictions},value


def assess(document, config, records, as_of):
    """Pure evaluation of an already authorized immutable snapshot; no database writes."""
    document=validate(document,config);as_of=utc(as_of)
    if any(r['tenant']!=document['tenant'] or r['config_version']!=document['config_version'] for r in records):
        raise ValueError('Mixed evidence tenant/configuration scope.')
    end=datetime.fromisoformat(as_of.replace('Z','+00:00'));results=[]
    for criterion in document['criteria']:
        try:
            start=end-timedelta(seconds=criterion['window_seconds'])
            current,current_value=_collect(records,config,criterion,start,end,end)
            windows={'current':current};baseline_value=None
            if criterion['method']!='threshold':
                baseline,baseline_value=_collect(records,config,criterion,start-timedelta(seconds=criterion['window_seconds']),start,end)
                windows['baseline']=baseline
        except OverflowError: raise ValueError('Evaluation window outside supported calendar.')
        issues=[{**issue,'window':name} for name,window in windows.items() for issue in window['issues']]
        conflicts=[{**conflict,'window':name} for name,window in windows.items() for conflict in window['contradictions']]
        measured=None
        if conflicts: state='contradictory'
        elif issues: state='insufficient'
        elif criterion['method']=='relative_change' and baseline_value==0:
            state='insufficient';issues.append({'code':'zero_baseline'})
        else:
            measured=current_value if criterion['method']=='threshold' else current_value-baseline_value
            if criterion['method']=='relative_change': measured/=abs(baseline_value)
            state='demonstrated' if COMPARISONS[criterion['comparison']](measured,Fraction(str(criterion['threshold']))) else 'stable'
        results.append({'criterion_id':criterion['id'],'dimension':criterion['dimension'],'state':state,
                        'measured':rational(measured) if measured is not None else None,'windows':windows,'issues':issues,'contradictions':conflicts})
    dimensions={}
    for dimension in ('operational','value'):
        selected=[r for r in results if r['dimension']==dimension];states={r['state'] for r in selected}
        state='contradictory' if 'contradictory' in states else 'insufficient' if not selected or 'insufficient' in states else 'demonstrated' if 'demonstrated' in states else 'stable'
        dimensions['operational_deterioration' if dimension=='operational' else 'value_loss']={'state':state,'criterion_ids':[r['criterion_id'] for r in selected]}
    return {**dimensions,'criteria_results':results}
