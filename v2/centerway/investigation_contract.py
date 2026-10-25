"""Structured C03 v1: recorded observations and declarations, never causal inference."""
from fractions import Fraction
import operator

from .evidence import customer_id,scalar,utc
from .http_contract import strict_json
from .integration_contract import fields,identifier,shape,text,timestamp
from .integrations import canonical

ALGORITHM='c03-structured-v1'
COMPARISONS={'eq':operator.eq,'ne':operator.ne,'lt':operator.lt,'lte':operator.le,'gt':operator.gt,'gte':operator.ge}


def _list(value,label):
    if not isinstance(value,list) or len(value)>100: raise ValueError('Invalid '+label+' list.')
    return value


def _ref(ref,facts):
    shape(ref,'evidence_id field','fact_reference')
    if type(ref['evidence_id']) is not int or ref['evidence_id']<1 or not isinstance(ref['field'],str): raise ValueError('Invalid fact reference.')
    fact=facts.get(ref['evidence_id'])
    if not fact or ref['field'] not in fact['payload']: raise ValueError('Fact absent from the pinned C02 evidence snapshot.')
    return (ref['evidence_id'],ref['field'])


def validate(document,c02,config,records):
    raw=canonical(document).encode('utf-8')
    if len(raw)>65536: raise ValueError('Investigation declaration exceeds 65536 bytes.')
    document=strict_json(raw)
    shape(document,'schema_version tenant customer c02_run_id provenance hypotheses requirements','investigation')
    if type(document['schema_version']) is not int or document['schema_version']!=1: raise ValueError('Unknown investigation schema.')
    identifier(document['tenant'],'tenant');customer_id(document['customer'])
    if (type(document['c02_run_id']) is not int or document['c02_run_id']!=c02['id']
            or document['tenant']!=c02['tenant'] or document['customer']!=c02['customer']):
        raise ValueError('Investigation/C02 scope mismatch.')
    provenance=document['provenance'];shape(provenance,'source_ref supplied_by recorded_at','provenance')
    text(provenance['source_ref'],'source_ref',256);text(provenance['supplied_by'],'supplied_by',128);timestamp(provenance['recorded_at'],'recorded_at')
    facts={r['id']:r for r in records};expected={r['id']:r['record_hash'] for r in c02['payload']['evidence']}
    if ({key:r['record_hash'] for key,r in facts.items()}!=expected
            or any(r['tenant']!=document['tenant'] or r['customer']!=document['customer'] or r['config_version']!=c02['payload']['config_version'] for r in records)):
        raise ValueError('Mixed or incomplete C02 evidence snapshot.')
    criteria={r['criterion_id']:r for r in c02['payload']['criteria_results']}
    seen=set()
    for hypothesis in _list(document['hypotheses'],'hypotheses'):
        shape(hypothesis,'id statement support_refs contrary_refs','hypothesis')
        identifier(hypothesis['id'],'hypothesis.id');text(hypothesis['statement'],'hypothesis.statement')
        if hypothesis['id'] in seen: raise ValueError('Duplicate hypothesis id.')
        seen.add(hypothesis['id']);sides=[]
        for name in ('support_refs','contrary_refs'):
            values=[_ref(ref,facts) for ref in _list(hypothesis[name],name)]
            if any(facts[id]['occurred_at']>c02['payload']['as_of'] for id,_ in values):
                raise ValueError('Future observations cannot support/refute the pinned C02 time.')
            if len(values)!=len(set(values)): raise ValueError('Duplicate fact reference.')
            sides.append(set(values))
        if sides[0]&sides[1]: raise ValueError('Support/contrary declarations overlap.')
    seen=set()
    definitions={kind:{d['id']:d for d in config[key]} for kind,key in (('event','events'),('metric','metrics'),('evidence','evidence'))}
    for requirement in _list(document['requirements'],'requirements'):
        shape(requirement,'id declaration criterion_id window selector comparison expected','requirement')
        identifier(requirement['id'],'requirement.id');text(requirement['declaration'],'requirement.declaration')
        if requirement['id'] in seen: raise ValueError('Duplicate requirement id.')
        seen.add(requirement['id']);identifier(requirement['criterion_id'],'criterion_id')
        criterion=criteria.get(requirement['criterion_id'])
        if not criterion or requirement['window'] not in ('current','baseline') or requirement['window'] not in criterion['windows']:
            raise ValueError('Required C02 criterion/window does not exist.')
        selector=requirement['selector'];shape(selector,'kind definition_id field','selector')
        if selector['kind'] not in ('event','metric','evidence'): raise ValueError('Unknown selector kind.')
        identifier(selector['definition_id'],'selector.definition_id')
        definition=definitions[selector['kind']].get(selector['definition_id'])
        if not definition: raise ValueError('Selector absent from configuration.')
        available={'value':{'type':definition['value_type']}} if selector['kind']=='metric' else fields(definition['fields'],'selector.fields')
        if not isinstance(selector['field'],str) or selector['field'] not in available: raise ValueError('Selector field is not declared.')
        kind=available[selector['field']]['type'];comparison=requirement['comparison']
        if comparison not in tuple(COMPARISONS) or (comparison not in ('eq','ne') and kind not in ('integer','number','timestamp')):
            raise ValueError('Unsupported typed comparison.')
        requirement['expected']=scalar(requirement['expected'],kind)
        if selector['field']=='occurred_at': requirement['expected']=utc(requirement['expected'])
    return document


def _reference(record,field): return {'evidence_id':record['id'],'field':field}


def _contradictions(c02,records):
    indexed={r['id']:r for r in records};groups={};candidates=[]
    for record in records:
        if record['kind']!='event': groups.setdefault(record['fact_hash'],[]).append(record['id'])
    candidates += [(ids,{'kind':'snapshot'}) for ids in groups.values() if len(ids)>1]
    for result in c02['payload']['criteria_results']:
        candidates += [(c['evidence_ids'],{'kind':'c02_result','criterion_id':result['criterion_id'],'window':c['window']}) for c in result['contradictions']]
    found={}
    for ids,basis in candidates:
        group=[indexed[id] for id in ids];names=sorted({field for r in group for field in r['payload']})
        for field in names:
            claims=[r for r in group if field in r['payload']]
            if len({canonical(r['payload'][field]) for r in claims})<=1: continue
            refs=[_reference(r,field) for r in claims];key=tuple(sorted((r['evidence_id'],r['field']) for r in refs))
            if key not in found: found[key]={'fact_refs':refs,'detected_by':[]}
            if basis not in found[key]['detected_by']: found[key]['detected_by'].append(basis)
    return [found[key] for key in sorted(found)]


def _requirement(requirement,c02,config,records,disputed):
    criterion=next(r for r in c02['payload']['criteria_results'] if r['criterion_id']==requirement['criterion_id'])
    window=criterion['windows'][requirement['window']];selector=requirement['selector'];field=selector['field']
    definition=next(d for d in config[{'metric':'metrics','event':'events','evidence':'evidence'}[selector['kind']]] if d['id']==selector['definition_id'])
    periodic=selector['kind']=='metric' or (selector['kind']=='evidence' and definition['kind']=='metric')
    checked=[];violations=[];compliant=[];missing=[];incompatible=[]
    for record in records:
        if record['kind']!=selector['kind'] or record['definition_id']!=selector['definition_id'] or record['occurred_at']>c02['payload']['as_of']: continue
        if periodic:
            if record['period_end']<=window['start'] or record['period_start']>=window['end']: continue
            if record['period_start']<window['start'] or record['period_end']>window['end']:
                incompatible.append(record['id']);continue
        elif not window['start']<record['occurred_at']<=window['end']: continue
        if field not in record['payload']: missing.append(record['id']);continue
        ref=_reference(record,field);checked.append(ref)
        value,expected=record['payload'][field],requirement['expected']
        if type(value) in (int,float): value,expected=Fraction(str(value)),Fraction(str(expected))
        # Timestamp strings are normalized by the evidence/contract validators.
        passed=COMPARISONS[requirement['comparison']](value,expected)
        (compliant if passed else violations).append(ref)
    is_disputed=any((r['evidence_id'],r['field']) in disputed for r in checked)
    status='contradictory' if is_disputed else 'supported' if violations else 'insufficient' if not checked or missing or incompatible else 'not_observed'
    result={'requirement_id':requirement['id'],'declared_requirement':requirement,'status':status,
            'claim_type':'observed_requirement_noncompliance','support_scope':'observed_condition_only',
            'causal_status':'not_established','checked_refs':checked,'violation_refs':violations,'compliant_refs':compliant}
    gaps=[]
    if not checked or missing or incompatible:
        gaps.append({'kind':'requirement_gap','requirement_id':requirement['id'],'criterion_id':requirement['criterion_id'],
                     'window':requirement['window'],'selector':selector,'no_observation':not checked,
                     'missing_field_evidence_ids':missing,'incompatible_period_evidence_ids':incompatible})
    return result,gaps


def build(document,c02,config,records,version):
    document=validate(document,c02,config,records);contradictions=_contradictions(c02,records)
    disputed={(r['evidence_id'],r['field']) for conflict in contradictions for r in conflict['fact_refs']}
    facts=[]
    for record in records:
        facts.append({'evidence_id':record['id'],'claim_scope':'recorded_observation',
                      'temporal_relation':'after_c02_as_of' if record['occurred_at']>c02['payload']['as_of'] else 'at_or_before_c02_as_of','kind':record['kind'],
                      'definition_id':record['definition_id'],'payload':record['payload'],
                      'disputed_fields':sorted(field for field in record['payload'] if (record['id'],field) in disputed),
                      'provenance':{key:record[key] for key in ('tenant','customer','config_version','config_hash','source_ref','external_id','occurred_at','received_at','period_start','period_end','actor','record_hash')}})
    hypotheses=[{**h,'state':'unconfirmed','support_scope':'operator_declared_references_only','causal_status':'not_established',
                 'disputed_refs':[r for r in h['support_refs']+h['contrary_refs'] if (r['evidence_id'],r['field']) in disputed]} for h in document['hypotheses']]
    requirements=[];gaps=[];limitations=[]
    for requirement in document['requirements']:
        result,missing=_requirement(requirement,c02,config,records,disputed);requirements.append(result);gaps.extend(missing)
    for criterion in c02['payload']['criteria_results']:
        for issue in criterion['issues']:
            (gaps if issue['code']=='missing_samples' else limitations).append(
                {'kind':'c02_gap','criterion_id':criterion['criterion_id'],'issue':issue})
    dimensions={key:c02['payload'][key] for key in ('operational_deterioration','value_loss')}
    for key,value in dimensions.items():
        if not value['criterion_ids']: gaps.append({'kind':'unconfigured_c02_dimension','dimension':key})
    return {'algorithm':ALGORITHM,'tenant':document['tenant'],'customer':document['customer'],
            'investigation_version':version,'c02_run_id':c02['id'],'c02_run_hash':c02['record_hash'],
            'config_version':c02['payload']['config_version'],'config_hash':c02['payload']['config_hash'],
            'criteria_version':c02['payload']['criteria_version'],'criteria_hash':c02['payload']['criteria_hash'],
            'as_of':c02['payload']['as_of'],'through':c02['payload']['through'],'classification':config['data_classification'],
            'operational_state':'inactive','causal_status':'not_established','declaration_provenance':document['provenance'],
            'facts':facts,'c02_findings':{'algorithm':c02['payload']['algorithm'],'proof_scope':c02['payload']['proof_scope'],
                            'dimensions':dimensions,'criteria_snapshot':c02['payload']['criteria_snapshot'],'criteria_results':c02['payload']['criteria_results']},
            'hypotheses':hypotheses,'requirements':requirements,
            'supported_impediments':[r for r in requirements if r['status']=='supported'],
            'missing_information':gaps,'analysis_limitations':limitations,'contradictions':contradictions}
