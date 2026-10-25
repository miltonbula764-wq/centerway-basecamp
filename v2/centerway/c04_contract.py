"""Deterministic independent C04 validation. No authorization or execution pathway."""
from fractions import Fraction
import json
from pathlib import Path

from .evidence import scalar,utc
from .http_contract import strict_json
from .integration_contract import fields,identifier,shape
from .integrations import canonical
from .investigation_contract import COMPARISONS

VALIDATOR='c04-grounded-v1'
RESPONSE_SCHEMA=json.loads((Path(__file__).resolve().parents[1]/'contracts/c04-response.schema.json').read_text())


class InvalidResponse(ValueError): pass


def _unique(value,maximum=100):
    if not isinstance(value,list) or len(value)>maximum or len({canonical(v) for v in value})!=len(value): raise InvalidResponse('invalid_list')
    return value


def _refs(values,context):
    facts={f['evidence_id']:f for f in context['investigation']['facts']}
    for ref in _unique(values):
        shape(ref,'evidence_id field','reference')
        if type(ref['evidence_id']) is not int or not isinstance(ref['field'],str): raise InvalidResponse('invalid_evidence_reference')
        fact=facts.get(ref['evidence_id'])
        if not fact or ref['field'] not in fact['payload'] or fact['temporal_relation']!='at_or_before_c02_as_of': raise InvalidResponse('invalid_evidence_reference')
    return values


def _condition(condition,context):
    definition=next(d for d in context['configuration']['evidence'] if d['id']==condition['evidence_ref'])
    candidates=[f for f in context['investigation']['facts'] if f['kind']=='evidence' and f['definition_id']==definition['id']
                and f['provenance']['occurred_at']==context['lineage']['as_of'] and f['provenance']['period_start'] is None]
    usable=[f for f in candidates if condition['field'] in f['payload']]
    result={'condition':condition,'fact_refs':[{'evidence_id':f['evidence_id'],'field':condition['field']} for f in usable]}
    if not usable: return {**result,'state':'unknown'}
    if any(condition['field'] in f['disputed_fields'] for f in usable) or len({canonical(f['payload'][condition['field']]) for f in usable})!=1:
        return {**result,'state':'contradictory'}
    if condition['operator']=='exists': return {**result,'state':'satisfied'}
    kind=fields(definition['fields'],'condition.fields')[condition['field']]['type']
    expected=scalar(condition['value'],kind)
    if condition['field']=='occurred_at': expected=utc(expected)
    observed=usable[0]['payload'][condition['field']]
    if type(observed) in (int,float): observed,expected=Fraction(str(observed)),Fraction(str(expected))
    return {**result,'state':'satisfied' if COMPARISONS[condition['operator']](observed,expected) else 'not_satisfied'}


def validate(raw,context):
    base={'validator':VALIDATOR,'operational_state':'inactive','execution_authorized':False,'authorization':'not_granted',
          'human_review_required':True,'causal_status':'not_established','condition_checks':[],'verification_status':'not_performed',
          'verification_plan':None,'validated_capability_id':None,'model_response':None}
    try:
        if not isinstance(raw,str) or len(raw.encode('utf-8'))>65536: raise InvalidResponse('invalid_response_size')
        response=strict_json(raw.encode('utf-8'))
        shape(response,'schema_version context_hash hypothesis_reviews impediment_refs contradiction_refs missing_information_refs analysis_limitation_refs recommendation','response')
        if type(response['schema_version']) is not int or response['schema_version']!=1: raise InvalidResponse('invalid_response_schema')
        if response['context_hash']!=context['context_hash']: raise InvalidResponse('context_hash_mismatch')
        investigation=context['investigation'];hypotheses={h['id']:h for h in investigation['hypotheses']}
        reviews=_unique(response['hypothesis_reviews']);ids=[]
        for review in reviews:
            shape(review,'hypothesis_id disposition support_refs contrary_refs','hypothesis_review')
            identifier(review['hypothesis_id'],'hypothesis_id');ids.append(review['hypothesis_id'])
            if review['hypothesis_id'] not in hypotheses or review['disposition'] not in ('retain_unconfirmed','human_review'): raise InvalidResponse('invalid_hypothesis_review')
            for side in ('support_refs','contrary_refs'):
                if any(ref not in hypotheses[review['hypothesis_id']][side] for ref in _refs(review[side],context)): raise InvalidResponse('invented_hypothesis_support')
        if len(ids)!=len(set(ids)) or set(ids)!=set(hypotheses): raise InvalidResponse('incomplete_hypothesis_review')
        for key,source in (('contradiction_refs','contradictions'),('missing_information_refs','missing_information'),('analysis_limitation_refs','analysis_limitations')):
            refs=_unique(response[key],1000)
            if any(type(i) is not int for i in refs) or set(refs)!=set(range(len(investigation[source]))): raise InvalidResponse('omitted_or_invented_uncertainty')
        impediments={r['requirement_id'] for r in investigation['supported_impediments']}
        for ref in _unique(response['impediment_refs']):
            identifier(ref,'impediment_ref')
            if ref not in impediments: raise InvalidResponse('invented_impediment')
        proposal=response['recommendation'];shape(proposal,'kind capability_id reason_code evidence_refs criterion_refs','recommendation')
        if proposal['kind'] not in ('action_proposal','no_action','human_review'): raise InvalidResponse('invalid_recommendation')
        reasons=RESPONSE_SCHEMA['properties']['recommendation']['properties']['reason_code']['enum']
        if proposal['reason_code'] not in reasons: raise InvalidResponse('invalid_justification')
        _refs(proposal['evidence_refs'],context)
        criteria={r['criterion_id']:r for r in investigation['c02_findings']['criteria_results']}
        for ref in _unique(proposal['criterion_refs']):
            identifier(ref,'criterion_ref')
            if ref not in criteria: raise InvalidResponse('invalid_criterion_reference')
        capability=None
        if proposal['kind']=='action_proposal':
            identifier(proposal['capability_id'],'capability_id')
            capability=next((c for c in context['configuration']['capabilities'] if c['id']==proposal['capability_id']),None)
            if not capability: raise InvalidResponse('capability_not_declared')
            if proposal['reason_code']!='catalogue_match': raise InvalidResponse('unsupported_justification')
            if not proposal['evidence_refs'] or not any(criteria[i]['state']=='demonstrated' for i in proposal['criterion_refs']): raise InvalidResponse('unsupported_action_proposal')
            if any(ref['field'] in next(f for f in investigation['facts'] if f['evidence_id']==ref['evidence_id'])['disputed_fields'] for ref in proposal['evidence_refs']): raise InvalidResponse('disputed_action_support')
        elif proposal['capability_id'] is not None or proposal['reason_code']=='catalogue_match': raise InvalidResponse('invalid_no_action_proposal')
        dimensions=investigation['c02_findings']['dimensions']
        if proposal['reason_code']=='no_deterioration' and any(d['state']!='stable' for d in dimensions.values()): raise InvalidResponse('unsupported_justification')
        if proposal['reason_code']=='contradictory_evidence' and not investigation['contradictions']: raise InvalidResponse('unsupported_justification')
        base['model_response']=response
    except InvalidResponse as error:
        return {**base,'status':'refused','reason_codes':[str(error)]}
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
        return {**base,'status':'refused','reason_codes':['invalid_response_schema']}
    review=[]
    if investigation['contradictions']: review.append('contradictory_evidence')
    if investigation['missing_information'] or investigation['analysis_limitations']: review.append('insufficient_evidence')
    dimensions=investigation['c02_findings']['dimensions']
    if any(d['state'] in ('insufficient','contradictory') for d in dimensions.values()): review.append('incomplete_or_disputed_c02')
    review.extend(context['freshness_issues'])
    if any(r['disposition']=='human_review' for r in response['hypothesis_reviews']): review.append('hypothesis_review_requested')
    if proposal['kind']=='human_review': review.append('model_requested_review')
    if capability:
        if context['permission']['role']!=capability['permissions']['required_role']:
            return {**base,'status':'refused','reason_codes':['permission_denied']}
        checks=[_condition(condition,context) for condition in capability['conditions']];base['condition_checks']=checks
        required={canonical(ref) for check in checks for ref in check['fact_refs']}
        supplied={canonical(ref) for ref in proposal['evidence_refs']}
        if required-supplied: return {**base,'status':'refused','reason_codes':['condition_evidence_not_cited']}
        if any(c['state']!='satisfied' for c in checks): review.append('conditions_not_demonstrated')
        if review: return {**base,'status':'human_review','reason_codes':sorted(set(review))}
        return {**base,'status':'proposal_validated','reason_codes':['declared_conditions_and_evidence_match'],
                'validated_capability_id':capability['id'],'verification_plan':capability['verification']}
    return {**base,'status':'human_review' if review else 'no_action','reason_codes':sorted(set(review)) or ['model_recommends_no_action']}
