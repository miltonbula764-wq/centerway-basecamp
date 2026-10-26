"""Private per-SaaS analysis pilot. No account administration or execution API."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import sqlite3
import time
from urllib.parse import parse_qs

from .core import Core,Problem
from .evidence import customer_id,utc
from .http_contract import strict_json
from .integration_contract import identifier,shape,text
from .integrations import canonical,digest
from .store import Store,now

TABLES={
 'pilot_metadata':"CREATE TABLE pilot_metadata(marker TEXT PRIMARY KEY CHECK(marker='private-analysis-pilot-v1'), mode TEXT NOT NULL CHECK(mode='production'))",
 'pilot_grants':"CREATE TABLE pilot_grants(tenant TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,version))",
 'pilot_customers':"CREATE TABLE pilot_customers(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer,version))",
 'pilot_reviews':"CREATE TABLE pilot_reviews(tenant TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,customer,case_id,request_id), FOREIGN KEY(tenant,customer,case_id) REFERENCES orchestration_cases(tenant,customer,case_id))",
 'pilot_jobs':"CREATE TABLE pilot_jobs(tenant TEXT NOT NULL, request_id TEXT NOT NULL, customer TEXT NOT NULL, case_id TEXT NOT NULL, request_hash TEXT NOT NULL, actor TEXT NOT NULL, created_at INTEGER NOT NULL, grant_version INTEGER NOT NULL, as_of TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,request_id))",
 'pilot_results':"CREATE TABLE pilot_results(tenant TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, record_hash TEXT NOT NULL, PRIMARY KEY(tenant,request_id), FOREIGN KEY(tenant,request_id) REFERENCES pilot_jobs(tenant,request_id))",
}
GUARDS={f'pilot_immutable_{t}_{op}':f"CREATE TRIGGER pilot_immutable_{t}_{op} BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for t in TABLES for op in ('UPDATE','DELETE')}
for table in ('c05_intents','c05_approvals','c05_attempts','c05_results','recovery_plans','recovery_runs'):
    GUARDS['pilot_no_execution_'+table]=f"CREATE TRIGGER pilot_no_execution_{table} BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'pilot_analysis_only'); END"


def storage(db):
    schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'pilot_*'")}
    if any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS}.items()): raise Problem(503,'Piloto não preparado ou sem integridade.')
    rows=db.execute('SELECT * FROM pilot_metadata').fetchall()
    if len(rows)!=1 or rows[0]['marker']!='private-analysis-pilot-v1' or rows[0]['mode']!='production': raise Problem(503,'Modo piloto incompatível.')


def checked(row):
    row=dict(row);claimed=row.pop('record_hash')
    if digest(row)!=claimed: raise Problem(503,'Registo piloto sem integridade.')
    if 'payload' in row: row['payload']=strict_json(row['payload'].encode())
    return {**row,'record_hash':claimed}


def grant(db,tenant):
    storage(db)
    row=db.execute('SELECT * FROM pilot_grants WHERE tenant=? ORDER BY version DESC LIMIT 1',(tenant,)).fetchone()
    return checked(row) if row else None


def access(db,user,tenant,write=False):
    identifier(tenant,'tenant');Core(None).authorize(db,user,tenant,write=write)
    current=grant(db,tenant)
    if not current or current['payload']['enabled'] is not True: raise Problem(403,'Piloto não autorizado para esta SaaS.')
    return current


def install(store):
    from .orchestration import Orchestrator
    orch=Orchestrator(store)
    if orch.execution.mode!='production': raise ValueError('Pilot requires an isolated permanent declared-data foundation.')
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'pilot_*'").fetchone(): raise ValueError('Pilot exists; no repair.')
        for sql in {**TABLES,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO pilot_metadata VALUES (?,?)',('private-analysis-pilot-v1','production'))
    return {'status':'initialized','external_execution':'blocked'}


def authorize(store,user,tenant,enabled,allow_ai,reason,expected_version):
    from .integrations import runtime_mode
    if runtime_mode(store)!='production' or type(enabled) is not bool or type(allow_ai) is not bool: raise ValueError('Explicit production consent required.')
    text(reason,'reason',1000)
    if type(expected_version) is not int or expected_version<0 or (allow_ai and not enabled): raise ValueError('Invalid grant request.')
    with store.transaction() as db:
        identifier(tenant,'tenant');Core(store).authorize(db,user,tenant,write=True);current=grant(db,tenant)
        if expected_version!=(current['version'] if current else 0): raise Problem(409,'Autorização piloto alterada.')
        row={'tenant':tenant,'version':expected_version+1,'payload':canonical({'enabled':enabled,'allow_ai':allow_ai,'reason':reason,
             'scope':'declared_analysis_only','previous_hash':current['record_hash'] if current else None}), 'actor':user,'created_at':now()}
        row['record_hash']=digest(row);db.execute('INSERT INTO pilot_grants VALUES (?,?,?,?,?,?)',tuple(row.values()))
        return checked(row)


EXPLANATIONS={
 'awaiting_data':'Aguardam-se configuração, critérios ou evidências compatíveis e suficientes.',
 'awaiting_investigation':'C02 registou deterioração segundo os critérios declarados. Falta investigação explícita do operador.',
 'awaiting_ai':'Falta uma proposta de IA autorizada. Pode registar revisão humana para acompanhamento, sem simular IA.',
 'stable':'Não foi demonstrada deterioração pelos critérios e evidências utilizados. Não comprova recuperação.',
 'no_action':'A proposta validada recomenda não intervir; não autoriza execução nem demonstra recuperação.',
 'needs_review':'O caso exige revisão ou acompanhamento humano. Nenhuma intervenção foi autorizada.',
 'awaiting_execution':'Execução bloqueada no piloto. Apenas análise e acompanhamento são permitidos.',
}


def page_query(query,allowed,required):
    values=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=8,encoding='utf-8',errors='strict')
    if set(values)-set(allowed.split()) or not set(required.split())<=set(values) or any(len(v)!=1 or not v[0] or len(v[0])>128 for v in values.values()): raise ValueError('Invalid explicit pilot query.')
    result={k:v[0] for k,v in values.items()}
    for key in ('after','limit','version','run_id','c03_version'):
        if key in result:
            if not result[key].isascii() or not result[key].isdecimal() or len(result[key])>10: raise ValueError('Invalid pilot pagination/version.')
            result[key]=int(result[key])
    if 'limit' in result and not 1<=result['limit']<=50: raise ValueError('Limit is 1–50.')
    return result


class Pilot:
    def __init__(self,store):
        from .orchestration import Orchestrator
        self.store=store;self.orch=Orchestrator(store,analysis_only=True)
        if self.orch.execution.mode!='production': raise Problem(503,'Piloto exige fundação permanente isolada.')
        with closing(store.connect()) as db: storage(db)

    def _access(self,db,user,tenant,write=False,token=None):
        current=access(db,user,tenant,write)
        if token is not None: self.orch.execution._session(db,user,token)
        return current

    def status(self,user,tenant):
        self.orch.evidence._runtime()
        with self.store.transaction() as db:
            identifier(tenant,'tenant');Core(self.store).authorize(db,user,tenant)
            current=grant(db,tenant);configs=self.orch.detection._scope(db,user,tenant);criteria=self.orch.detection._criteria(db,tenant,configs)
            count=db.execute('SELECT count(DISTINCT customer) FROM pilot_customers WHERE tenant=?',(tenant,)).fetchone()[0]
            blockers=[]
            if not current or not current['payload']['enabled']: blockers.append('pilot_not_authorized')
            if not configs: blockers.append('configuration_missing')
            if not criteria or not configs or criteria[-1]['config_version']!=len(configs): blockers.append('current_criteria_missing')
            if not count: blockers.append('customers_missing')
            return {'tenant':tenant,'pilot_authorized':bool(current and current['payload']['enabled']),
                    'grant_version':current['version'] if current else 0,'ai_consent':bool(current and current['payload']['enabled'] and current['payload']['allow_ai']),
                    'customer_count':count,'configuration_version':len(configs),'criteria_version':len(criteria),
                    'analysis_ready':not blockers,'blockers':blockers,'external_execution':'blocked','real_recovery_demonstrated':False}

    def context(self,user,tenant,after=0,limit=25):
        self.orch.evidence._runtime()
        with self.store.transaction() as db:
            self._access(db,user,tenant);configs=self.orch.detection._scope(db,user,tenant);criteria=self.orch.detection._criteria(db,tenant,configs)
            metadata=lambda rows:[{k:r[k] for k in ('version','content_hash','record_hash','actor','created_at')} for r in rows if after<r['version']<=after+limit]
            return {'tenant':tenant,'configuration':configs[-1] if configs else None,'criteria':criteria[-1] if criteria else None,
                    'configuration_history':metadata(configs),'criteria_history':metadata(criteria),
                    'next_after':after+limit if max(len(configs),len(criteria))>after+limit else None,'scope':'declared_analysis_only'}

    def configuration(self,user,tenant,version):
        with self.store.transaction() as db: self._access(db,user,tenant)
        return self.orch.evidence.integrations.get(user,tenant,version)

    def criteria(self,user,tenant,version):
        with self.store.transaction() as db: self._access(db,user,tenant)
        return self.orch.detection.criteria(user,tenant,version)

    def _revision_guard(self,db,user,tenant,token,table):
        self._access(db,user,tenant,True,token)
        if db.execute('SELECT count(*) FROM '+table+' WHERE tenant=?',(tenant,)).fetchone()[0]>=100:
            raise Problem(413,'Limite de 100 versões de configuração/critérios por SaaS piloto.')

    def configure(self,user,tenant,config,expected_version,token):
        if not isinstance(config,dict) or config.get('data_classification')!='declared': raise Problem(403,'Piloto aceita apenas contrato declarado.')
        return self.orch.evidence.integrations.append(user,tenant,config,expected_version,
                _guard=lambda db:self._revision_guard(db,user,tenant,token,'integration_versions'))

    def append_criteria(self,user,tenant,document,expected_version,token):
        return self.orch.detection.append_criteria(user,tenant,document,expected_version,
                _guard=lambda db:self._revision_guard(db,user,tenant,token,'detection_criteria'))

    def _customer(self,db,tenant,customer):
        customer_id(customer)
        rows=db.execute('SELECT * FROM pilot_customers WHERE tenant=? AND customer=? ORDER BY version',(tenant,customer)).fetchall()
        history=[checked(r) for r in rows]
        if any(r['version']!=i+1 or r['payload']['previous_hash']!=(history[i-1]['record_hash'] if i else None) for i,r in enumerate(history)): raise Problem(503,'Histórico de cliente sem integridade.')
        return history

    def customer(self,user,tenant,customer,name,context,expected_version,token):
        text(name,'customer.name',200);text(context,'customer.context',2000)
        if type(expected_version) is not int or not 0<=expected_version<100: raise ValueError('Customer revision limit/version invalid.')
        with self.store.transaction() as db:
            self._access(db,user,tenant,True,token);history=self._customer(db,tenant,customer)
            if expected_version<len(history):
                old=history[expected_version]
                if old['payload']['name']==name and old['payload']['context']==context: return old
                raise Problem(409,'Cliente alterado; consultar versão atual.')
            if expected_version!=len(history): raise Problem(409,'Versão do cliente alterada.')
            if not history and db.execute('SELECT count(DISTINCT customer) FROM pilot_customers WHERE tenant=?',(tenant,)).fetchone()[0]>=1000: raise Problem(413,'Limite de 1000 clientes piloto.')
            row={'id':db.execute('SELECT coalesce(max(id),0)+1 FROM pilot_customers').fetchone()[0], 'tenant':tenant,'customer':customer,'version':len(history)+1,
                 'payload':canonical({'name':name,'context':context,'previous_hash':history[-1]['record_hash'] if history else None}), 'actor':user,'created_at':now()}
            row['record_hash']=digest(row);db.execute('INSERT INTO pilot_customers VALUES (?,?,?,?,?,?,?,?)',tuple(row.values()))
            return checked(row)

    def customers(self,user,tenant,customer=None,after=0,limit=25):
        with self.store.transaction() as db:
            self._access(db,user,tenant)
            if customer is not None:
                history=self._customer(db,tenant,customer)
                return {'tenant':tenant,'items':[r for r in history if after<r['version']<=after+limit], 'next_after':after+limit if len(history)>after+limit else None}
            rows=db.execute('SELECT c.* FROM pilot_customers c WHERE tenant=? AND id>? AND version=(SELECT max(v.version) FROM pilot_customers v WHERE v.tenant=c.tenant AND v.customer=c.customer) ORDER BY id LIMIT ?',(tenant,after,limit+1)).fetchall()
            return {'tenant':tenant,'items':[checked(r) for r in rows[:limit]],'next_after':rows[limit-1]['id'] if len(rows)>limit else None}

    def _case(self,db,user,tenant,customer,case_id,write=False,token=None):
        self._access(db,user,tenant,write,token)
        if not self._customer(db,tenant,customer): raise Problem(404,'Cliente piloto não registado neste escopo.')
        case=self.orch._case(db,tenant,customer,case_id)
        from .continuity import active
        if write: active(db,case)
        return case,self.orch._history(db,case)

    def analysis(self,user,tenant,customer,case_id,after=0,limit=25,version=None):
        with self.store.transaction() as db:
            case,history=self._case(db,user,tenant,customer,case_id)
            if version is not None and not 1<=version<=len(history): raise Problem(404,'Checkpoint inexistente.')
            selected=history[version-1] if version else history[-1] if history else None
            reviews=[checked(r) for r in db.execute('SELECT * FROM pilot_reviews WHERE tenant=? AND customer=? AND case_id=? ORDER BY created_at,request_id',(tenant,customer,case_id))]
        refs=selected['payload']['refs'] if selected else {};c02=c03=c04=None
        if refs.get('c02'): c02=self.orch.detection.get(user,tenant,customer,refs['c02']['id'])
        if refs.get('c03'): c03=self.orch.investigation.get(user,tenant,customer,refs['c02']['id'],refs['c03']['version'])
        if refs.get('c04'):
            try:
                source=self.orch.proposals.get(user,tenant,customer,refs['c04']['request_id']);result=source['result']
                c04={'request_id':refs['c04']['request_id'],'record_hash':result['record_hash'],'created_at':result['created_at'],
                     'receipt':{k:result['receipt'][k] for k in ('inference_kind','requested_model','reported_model','completion_received','failure','revalidation')},
                     'decision':result['payload']}
            except Problem as e:
                if e.status not in (404,409): raise
                c04={'request_id':refs['c04']['request_id'],'status':'not_requested' if e.status==404 else 'pending_or_interrupted','execution_authorized':False}
        state=selected['payload']['state'] if selected else 'awaiting_data'
        result={'tenant':tenant,'customer':customer,'case_id':case_id,'checkpoint':selected,
                'history':[r for r in history if after<r['version']<=after+limit],'next_after':after+limit if len(history)>after+limit else None,
                'c02':c02,'c03':c03,'c04':c04,'human_reviews':reviews,'explanation':EXPLANATIONS.get(state,'Acompanhamento técnico; execução e recuperação real não autorizadas.'),
                'interpretation':{'evidence':'Declarações da origem; autenticidade de transporte não prova verdade.',
                    'operational_deterioration':c02['payload']['operational_deterioration']['state'] if c02 else 'not_evaluated',
                    'value_loss':c02['payload']['value_loss']['state'] if c02 else 'not_evaluated',
                    'c02_states':{'demonstrated':'Os critérios declarados foram satisfeitos pelas evidências usadas; não prova uma causa.',
                        'stable':'Não foi demonstrada deterioração; não equivale a recuperação.',
                        'insufficient':'Faltam dados compatíveis/suficientes; ausência de dados não prova deterioração.',
                        'contradictory':'As evidências divergem; nenhuma foi escolhida arbitrariamente.'},
                    'c03':'Factos, hipóteses não confirmadas, impedimentos observados e lacunas permanecem separados.',
                    'c04':'Recomendação validada não é autorização; nenhuma intervenção pode ser executada no piloto.'},
                'external_execution':'blocked','real_recovery_demonstrated':False,'scope':'declared_analysis_only'}
        if len(canonical(result).encode())>1048576: raise Problem(413,'Análise excede 1 MiB; consultar evidências paginadas e um checkpoint histórico explícito.')
        return result

    def investigate(self,user,tenant,customer,case_id,c02_run_id,document,expected_version,token):
        if type(expected_version) is not int or not 0<=expected_version<100: raise ValueError('Pilot C03 revision limit/version invalid.')
        def guard(db):
            _,history=self._case(db,user,tenant,customer,case_id,True,token)
            if not history or history[-1]['payload']['refs'].get('c02',{}).get('id')!=c02_run_id: raise Problem(409,'Investigação exige C02 atual do caso.')
        return self.orch.investigation.append(user,tenant,customer,c02_run_id,document,expected_version,_guard=guard)

    def review(self,user,tenant,customer,case_id,request_id,expected_checkpoint_hash,note,token):
        identifier(request_id,'request_id');text(note,'review.note',2000)
        with self.store.transaction() as db:
            _,history=self._case(db,user,tenant,customer,case_id,True,token)
            old=db.execute('SELECT * FROM pilot_reviews WHERE tenant=? AND customer=? AND case_id=? AND request_id=?',(tenant,customer,case_id,request_id)).fetchone()
            if old:
                old=checked(old)
                if old['actor']!=user or old['payload']['note']!=note or old['payload']['checkpoint_hash']!=expected_checkpoint_hash: raise Problem(409,'request_id de revisão já utilizado.')
                return old
            if not history or history[-1]['record_hash']!=expected_checkpoint_hash: raise Problem(409,'Rever o checkpoint atual antes de registar acompanhamento.')
            refs=history[-1]['payload']['refs']
            if not refs.get('c03') or refs.get('c05'): raise Problem(409,'Revisão piloto exige C03 e nenhuma execução.')
            if db.execute('SELECT count(*) FROM pilot_reviews WHERE tenant=? AND customer=? AND case_id=?',(tenant,customer,case_id)).fetchone()[0]>=100: raise Problem(413,'Limite de 100 revisões por caso.')
            row={'tenant':tenant,'customer':customer,'case_id':case_id,'request_id':request_id,
                 'payload':canonical({'note':note,'checkpoint_hash':expected_checkpoint_hash,'lineage':{'c02':refs['c02']['record_hash'],'c03':refs['c03']['record_hash']},
                          'session_hash':hashlib.sha256(token.encode()).hexdigest(),'execution_authorized':False,'status':'human_follow_up'}),
                 'actor':user,'created_at':now()}
            row['record_hash']=digest(row);db.execute('INSERT INTO pilot_reviews VALUES (?,?,?,?,?,?,?,?)',tuple(row.values()))
            return checked(row)

    def process(self,user,tenant,customer,case_id,request_id,as_of,token,ai_config=None):
        identifier(request_id,'request_id');identifier(case_id,'case_id');customer_id(customer);as_of=utc(as_of)
        if as_of>utc(now()): raise ValueError('Future cutoff refused.')
        self.orch.analysis_session=token
        request_hash=digest({'customer':customer,'case_id':case_id,'as_of':as_of,'actor':user})
        current=int(time.time())
        with self.store.transaction() as db:
            consent=self._access(db,user,tenant,True,token)
            if not self._customer(db,tenant,customer): raise Problem(404,'Cliente piloto não registado.')
            old=db.execute('SELECT * FROM pilot_jobs WHERE tenant=? AND request_id=?',(tenant,request_id)).fetchone()
            if old:
                old=checked(old)
                if old['request_hash']!=request_hash: raise Problem(409,'request_id já utilizado para outro processamento.')
                result=db.execute('SELECT * FROM pilot_results WHERE tenant=? AND request_id=?',(tenant,request_id)).fetchone()
                if not result: raise Problem(409,'Processamento pendente/interrompido; consultar caso. Não há repetição automática de inferência.')
                return checked(result)['payload']
            if db.execute('SELECT count(*) FROM pilot_jobs WHERE tenant=? AND created_at>?',(tenant,current-60)).fetchone()[0]>=10: raise Problem(429,'Limite de 10 processamentos por minuto/SaaS.')
            if db.execute('SELECT 1 FROM pilot_jobs j WHERE tenant=? AND created_at>? AND NOT EXISTS (SELECT 1 FROM pilot_results r WHERE r.tenant=j.tenant AND r.request_id=j.request_id)',(tenant,current-60)).fetchone(): raise Problem(409,'Processamento desta SaaS em curso; aguardar ou consultar o caso.')
            if db.execute('SELECT count(*) FROM pilot_jobs WHERE tenant=?',(tenant,)).fetchone()[0]>=10000: raise Problem(413,'Limite de 10000 pedidos de processamento.')
            job={'tenant':tenant,'request_id':request_id,'customer':customer,'case_id':case_id,'request_hash':request_hash,'actor':user,
                 'created_at':current,'grant_version':consent['version'],'as_of':as_of}
            job['record_hash']=digest(job);db.execute('INSERT INTO pilot_jobs VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(job.values()))
        adapter=pilot_adapter(self,user,tenant,token,consent,ai_config)
        try:
            self.orch.register(user,tenant,customer,case_id)
            self.orch.process_case(user,tenant,customer,case_id,as_of,ai_adapter=adapter,max_steps=8,deadline=time.monotonic()+10)
            output=self.analysis(user,tenant,customer,case_id,limit=1)
            # Processing replies are compact; GET analysis provides the source detail/history.
            output={k:output[k] for k in ('tenant','customer','case_id','checkpoint','explanation','external_execution','real_recovery_demonstrated','scope')}
        except Exception:
            # The reserved job/checkpoints remain auditable. No inferred completion/retry.
            raise
        with self.store.transaction() as db:
            self._access(db,user,tenant,True,token)
            row={'tenant':tenant,'request_id':request_id,'payload':canonical(output)};row['record_hash']=digest(row)
            db.execute('INSERT INTO pilot_results VALUES (?,?,?,?)',tuple(row.values()))
        return output


def follow_up(db,tenant,customer,case_id,refs):
    lineage={'c02':refs['c02']['record_hash'],'c03':refs['c03']['record_hash']}
    for row in db.execute('SELECT * FROM pilot_reviews WHERE tenant=? AND customer=? AND case_id=? ORDER BY created_at DESC,request_id DESC',(tenant,customer,case_id)):
        review=checked(row)
        if review['payload']['lineage']==lineage: return {'request_id':review['request_id'],'record_hash':review['record_hash']}
    return None


def pilot_adapter(pilot,user,tenant,token,consent,config_file):
    from .ai_adapter import AIAdapter,HTTPSChatAdapter,ProviderError
    if not consent['payload']['allow_ai'] or config_file is None: return AIAdapter()
    try: provider=HTTPSChatAdapter(config_file)
    except (ValueError,OSError,TypeError,KeyError,RecursionError): return AIAdapter('provider_configuration_invalid')
    cfg=provider._config
    if (tenant not in cfg['allowed_tenants'] or 'declared' not in cfg['allowed_classifications'] or not cfg['allow_production_inference'] or cfg['timeout_seconds']>5): return AIAdapter('provider_data_not_authorized')
    class AuthorizedProvider(AIAdapter):
        def descriptor(self): return provider.descriptor()
        def generate(self,context):
            def check():
                try:
                    with pilot.store.transaction() as db:
                        current=pilot._access(db,user,tenant,True,token)
                        if current['version']!=consent['version'] or not current['payload']['allow_ai']: raise ValueError('Consent changed.')
                except (Problem,ValueError): raise ProviderError('provider_data_not_authorized') from None
            check();result=provider.generate(context);check();return result
    return AuthorizedProvider()


def main():
    parser=argparse.ArgumentParser(description='Local optional pilot setup/consent only; never an HTTP administration endpoint.')
    sub=parser.add_subparsers(dest='command',required=True);init=sub.add_parser('init');init.add_argument('--db',required=True)
    consent=sub.add_parser('authorize')
    for arg in ('db','user','tenant','reason'): consent.add_argument('--'+arg,required=True)
    consent.add_argument('--expected-version',required=True,type=int);consent.add_argument('--enabled',choices=['yes','no'],required=True);consent.add_argument('--allow-ai',choices=['yes','no'],required=True)
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        result=install(store) if args.command=='init' else authorize(store,args.user,args.tenant,args.enabled=='yes',args.allow_ai=='yes',args.reason,args.expected_version)
        print(canonical(result))
    except (ValueError,OSError,Problem,sqlite3.Error,RecursionError): parser.exit(1,'Pilot preparation refused; verify mode, permissions and explicit consent.\n')


if __name__=='__main__': main()
