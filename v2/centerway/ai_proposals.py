"""Inactive C04 requests/results: provider recommends; Core permissions stay authoritative."""
import argparse
from contextlib import closing
import hashlib
import sqlite3

from .ai_adapter import AIAdapter,Completion,MAX_CONTEXT,ProviderError,configured_adapter,_token
from .c04_contract import RESPONSE_SCHEMA,VALIDATOR,validate
from .core import Core,Problem
from .http_contract import strict_json
from .integration_contract import identifier
from .integrations import canonical,digest
from .investigation import InvestigationRepository
from .store import Store,now

TABLES={
    'c04_metadata': "CREATE TABLE c04_metadata(marker TEXT PRIMARY KEY CHECK(marker='inactive-c04-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')), validator TEXT NOT NULL CHECK(validator='c04-grounded-v1'))",
    'c04_requests': "CREATE TABLE c04_requests(tenant TEXT NOT NULL, customer TEXT NOT NULL, request_id TEXT NOT NULL, c02_run_id INTEGER NOT NULL, c03_version INTEGER NOT NULL, context_hash TEXT NOT NULL, context TEXT NOT NULL, adapter TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,request_id), FOREIGN KEY(tenant,customer,c02_run_id,c03_version) REFERENCES investigation_versions(tenant,customer,c02_run_id,version))",
    'c04_results': "CREATE TABLE c04_results(tenant TEXT NOT NULL, customer TEXT NOT NULL, request_id TEXT NOT NULL, receipt TEXT NOT NULL, response_hash TEXT, payload TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,request_id), FOREIGN KEY(tenant,customer,request_id) REFERENCES c04_requests(tenant,customer,request_id))",
}
GUARDS={f'c04_immutable_{table}_{operation}':f"CREATE TRIGGER c04_immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for table in TABLES for operation in ('UPDATE','DELETE')}
FAILURES={'provider_not_configured','provider_configuration_invalid','provider_data_not_authorized','context_too_large','context_contains_provider_secret',
          'provider_redirect_refused','provider_status_refused','provider_invalid_envelope','provider_response_too_large',
          'provider_secret_echo_refused','provider_incomplete_or_refused','provider_http_failure','provider_transport_failure'}


def _decision(status,code):
    return {'validator':VALIDATOR,'status':status,'reason_codes':[code],'operational_state':'inactive','execution_authorized':False,
            'authorization':'not_granted','human_review_required':True,'causal_status':'not_established','model_response':None,
            'condition_checks':[],'validated_capability_id':None,'verification_status':'not_performed','verification_plan':None}


def install(store):
    investigation=InvestigationRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'c04_*'").fetchone(): raise ValueError('C04 storage exists; no replacement/repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO c04_metadata VALUES (?,?,?)',('inactive-c04-v1',investigation.detection.evidence.integrations.mode,VALIDATOR))
    return {'status':'initialized','operational_state':'inactive','inference':'not_configured'}


class ProposalRepository:
    def __init__(self,store):
        self.store=store;self.investigation=InvestigationRepository(store)
        with closing(store.connect()) as db: self._storage(db)

    def _runtime(self): self.investigation.detection.evidence._runtime()

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'c04_*'")}
        rows=db.execute('SELECT * FROM c04_metadata').fetchall() if 'c04_metadata' in schema else []
        if (any(schema.get(name)!=sql for name,sql in {**TABLES,**GUARDS}.items()) or len(rows)!=1 or rows[0]['marker']!='inactive-c04-v1'
                or rows[0]['mode']!=self.investigation.detection.evidence.integrations.mode or rows[0]['validator']!=VALIDATOR):
            raise Problem(503,'C04 indisponível; preparação/integridade necessária, sem reparação automática.')

    def _context(self,db,user,tenant,customer,c02_run_id,c03_version):
        self._storage(db)
        c02,config,records=self.investigation._context(db,user,tenant,customer,c02_run_id,write=True)
        history=self.investigation._history(db,tenant,customer,c02,config,records)
        if type(c03_version) is not int or not 1<=c03_version<=len(history): raise Problem(404,'Versão C03 inexistente neste escopo.')
        c03=history[c03_version-1];freshness=[]
        if c03_version!=len(history): freshness.append('investigation_superseded')
        detection=self.investigation.detection;configs=detection.evidence.integrations._chain(db,tenant)
        criteria=detection._criteria(db,tenant,configs)
        if c02['payload']['config_version']!=len(configs): freshness.append('configuration_superseded')
        if c02['criteria_version']!=len(criteria): freshness.append('criteria_superseded')
        latest=db.execute('SELECT max(id) FROM detection_runs WHERE tenant=? AND customer=?',(tenant,customer)).fetchone()[0]
        if latest!=c02_run_id: freshness.append('detection_superseded')
        latest_evidence=db.execute('SELECT coalesce(max(id),0) FROM evidence_items WHERE tenant=? AND customer=?',(tenant,customer)).fetchone()[0]
        if latest_evidence!=c02['payload']['through']: freshness.append('new_evidence_requires_new_c02_c03')
        context={'context_version':1,'runtime_mode':detection.evidence.integrations.mode,'classification':config['data_classification'],
                 'lineage':{'tenant':tenant,'customer':customer,'c02_run_id':c02_run_id,'c02_hash':c02['record_hash'],
                            'c03_version':c03_version,'c03_hash':c03['record_hash'],'config_version':c02['payload']['config_version'],
                            'config_hash':c02['payload']['config_hash'],'criteria_version':c02['criteria_version'],
                            'criteria_hash':c02['payload']['criteria_hash'],'as_of':c02['payload']['as_of'],'through':c02['payload']['through']},
                 'permission':{'role':Core(self.store).authorize(db,user,tenant,write=True),'execution_authorized':False},
                 'goal_scope':'saas_contract_for_selected_customer','configuration':config,'investigation':c03['payload'],
                 'freshness_issues':sorted(freshness),
                 'current_heads':{'config_version':len(configs),'criteria_version':len(criteria),'c03_version':len(history),
                                  'c02_run_id':latest,'evidence_id':latest_evidence},'response_contract':RESPONSE_SCHEMA}
        context['context_hash']=digest(context)
        if len(canonical(context).encode('utf-8'))>MAX_CONTEXT: raise Problem(413,'Contexto excede 262144 bytes; não foi truncado nem enviado.')
        return context

    def _read(self,db,user,tenant,customer,request_id):
        row=db.execute('SELECT * FROM c04_requests WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone()
        if not row: raise Problem(404,'Pedido C04 inexistente neste escopo.')
        request=dict(row);claimed=request.pop('record_hash')
        if digest(request)!=claimed: raise Problem(503,'Pedido C04 sem integridade.')
        context=strict_json(request['context'].encode('utf-8'));context_hash=context.pop('context_hash')
        if digest(context)!=context_hash or context_hash!=request['context_hash']: raise Problem(503,'Contexto C04 sem integridade.')
        context['context_hash']=context_hash
        c02,config,records=self.investigation._context(db,user,tenant,customer,request['c02_run_id'])
        history=self.investigation._history(db,tenant,customer,c02,config,records)
        if (not 1<=request['c03_version']<=len(history) or history[request['c03_version']-1]['record_hash']!=context['lineage']['c03_hash']
                or history[request['c03_version']-1]['payload']!=context['investigation'] or config!=context['configuration']):
            raise Problem(503,'Fontes C04 não correspondem ao snapshot auditado.')
        result=db.execute('SELECT * FROM c04_results WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone()
        if not result: raise Problem(409,'Inferência pendente ou interrompida; não será repetida automaticamente.')
        result=dict(result);result_hash=result.pop('record_hash')
        if digest(result)!=result_hash: raise Problem(503,'Resultado C04 sem integridade.')
        payload=strict_json(result['payload'].encode('utf-8'));receipt=strict_json(result['receipt'].encode('utf-8'))
        if payload.get('execution_authorized') is not False or payload.get('authorization')!='not_granted' or payload.get('operational_state')!='inactive': raise Problem(503,'Estado C04 inválido.')
        if payload.get('model_response') is not None:
            original=validate(canonical(payload['model_response']),context)
            # Post-inference revalidation may only downgrade, never grant extra authority.
            if payload['status'] in ('proposal_validated','no_action') and payload!=original: raise Problem(503,'Validação C04 não reproduzível.')
        return {'request':{**request,'record_hash':claimed,'context':context,'adapter':strict_json(request['adapter'].encode('utf-8'))},
                'result':{**result,'record_hash':result_hash,'receipt':receipt,'payload':payload},'reused':True}

    def propose(self,user,tenant,customer,c02_run_id,c03_version,request_id,adapter=None):
        self._runtime();identifier(request_id,'request_id');adapter=adapter or AIAdapter()
        descriptor=adapter.descriptor()
        if (not isinstance(descriptor,dict) or set(descriptor)-{'protocol','requested_model','inference_kind','endpoint','authorization_hash'}
                or not {'protocol','requested_model','inference_kind'}<=set(descriptor)
                or descriptor.get('inference_kind') not in ('unavailable','configured_provider','test_fixture')
                or not _token(descriptor['protocol']) or descriptor['requested_model'] is not None and not _token(descriptor['requested_model'])):
            raise ValueError('Untrusted adapter descriptor.')
        with self.store.transaction() as db:
            context=self._context(db,user,tenant,customer,c02_run_id,c03_version)
            previous=db.execute('SELECT context_hash,adapter FROM c04_requests WHERE tenant=? AND customer=? AND request_id=?',(tenant,customer,request_id)).fetchone()
            if previous:
                if previous['context_hash']!=context['context_hash'] or previous['adapter']!=canonical(descriptor): raise Problem(409,'request_id já ligado a outro contexto/modelo.')
                return self._read(db,user,tenant,customer,request_id)
            request={'tenant':tenant,'customer':customer,'request_id':request_id,'c02_run_id':c02_run_id,'c03_version':c03_version,
                     'context_hash':context['context_hash'],'context':canonical(context),'adapter':canonical(descriptor),'actor':user,'created_at':now()}
            request['record_hash']=digest(request)
            db.execute('INSERT INTO c04_requests VALUES (?,?,?,?,?,?,?,?,?,?,?)',tuple(request.values()))
        # No SQLite transaction is held during inference. The reservation prevents duplicate calls.
        completion=None;failure=None
        if context['runtime_mode']=='production' and descriptor['inference_kind']=='test_fixture': failure='fixture_forbidden_in_production'
        else:
            try:
                completion=adapter.generate(strict_json(canonical(context).encode('utf-8')))
                if not isinstance(completion,Completion) or not _token(completion.reported_model) or not _token(completion.response_id):
                    completion=None;failure='provider_invalid_envelope'
            except ProviderError as error: failure=error.code if error.code in FAILURES else 'provider_failure'
            except Exception: failure='provider_failure'  # Never echo SDK/network exception messages.
        receipt={'inference_kind':descriptor['inference_kind'],'requested_model':descriptor.get('requested_model'),
                 'reported_model':completion.reported_model if completion else None,'response_id':completion.response_id if completion else None,
                 'completion_received':completion is not None,'failure':failure}
        if failure:
            decision=_decision('refused' if failure=='fixture_forbidden_in_production' else 'unavailable' if descriptor['inference_kind']=='unavailable' or failure=='provider_data_not_authorized' else 'human_review',failure)
        else:
            try: decision=validate(completion.content,context)
            except Exception: decision=_decision('refused','validator_failure')
        response_hash=hashlib.sha256(completion.content.encode('utf-8')).hexdigest() if completion and isinstance(completion.content,str) else None
        runtime_failed=False
        try: self._runtime()
        except (Problem,ValueError,sqlite3.Error): runtime_failed=True
        denied=None
        receipt.update(revalidation='not_completed',post_context_hash=None,post_current_heads=None)
        with self.store.transaction() as db:
            self._storage(db)
            try:
                Core(self.store).authorize(db,user,tenant,write=True)
                if runtime_failed: raise Problem(503,'Runtime indisponível após inferência.')
                latest=self._context(db,user,tenant,customer,c02_run_id,c03_version)
                receipt.update(revalidation='matched',post_context_hash=latest['context_hash'],post_current_heads=latest['current_heads'])
                if latest['context_hash']!=context['context_hash']:
                    receipt['revalidation']='context_changed'
                    decision=_decision('human_review','context_changed_during_inference')
            except Problem as error:
                receipt['revalidation']='authorization_changed' if error.status==403 else 'revalidation_failed'
                decision=_decision('refused',receipt['revalidation']);denied=error
            result={'tenant':tenant,'customer':customer,'request_id':request_id,'receipt':canonical(receipt),'response_hash':response_hash,
                    'payload':canonical(decision),'created_at':now()}
            result['record_hash']=digest(result)
            db.execute('INSERT INTO c04_results VALUES (?,?,?,?,?,?,?,?)',tuple(result.values()))
        if denied: raise denied
        with self.store.transaction() as db:
            Core(self.store).authorize(db,user,tenant,write=True)
            output=self._read(db,user,tenant,customer,request_id);output['reused']=False;return output

    def get(self,user,tenant,customer,request_id):
        self._runtime();identifier(request_id,'request_id')
        with self.store.transaction() as db:
            Core(self.store).authorize(db,user,tenant);self._storage(db)
            return self._read(db,user,tenant,customer,request_id)


def main():
    parser=argparse.ArgumentParser(description='Inactive grounded C04; no default provider, simulation, authorization or execution.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--db',required=True)
    for command in ('propose','get'):
        child=sub.add_parser(command)
        for name in ('db','user','tenant','customer','request-id'): child.add_argument('--'+name,required=True)
        if command=='propose':
            child.add_argument('--c02-run-id',type=int,required=True);child.add_argument('--c03-version',type=int,required=True)
            child.add_argument('--ai-config')
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        if args.command=='init': output=install(store)
        else:
            repository=ProposalRepository(store)
            if args.command=='propose': output=repository.propose(args.user,args.tenant,args.customer,args.c02_run_id,args.c03_version,args.request_id,configured_adapter(args.ai_config))
            else: output=repository.get(args.user,args.tenant,args.customer,args.request_id)
    except (ValueError,OSError,sqlite3.Error,Problem,RecursionError): parser.exit(1,'{"status":"error","code":"c04_refused"}\n')
    print(canonical(output))


if __name__=='__main__': main()
