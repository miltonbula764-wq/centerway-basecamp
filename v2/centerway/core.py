"""Core — server-side identity, tenancy, transitions and atomic execution."""
import json
import hashlib
import re
from datetime import date, timedelta
import uuid
from . import c01, c02, c03, c04, c05, c06
from .store import encode, now


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class Core:
    def __init__(self, store):
        self.store = store

    def authorize(self, db, user, tenant, write=False):
        member = db.execute('SELECT role FROM memberships WHERE user_id=? AND tenant=?', (user, tenant)).fetchone()
        if not member or (write and member['role'] != 'operator'):
            raise Problem(403, 'Sem permissão para esta SaaS ou operação.')
        return member['role']

    def audit(self, db, tenant, case_id, user, stage, detail):
        db.execute('INSERT INTO history(tenant,case_id,actor,stage,detail,created_at) VALUES (?,?,?,?,?,?)', (tenant, case_id, user, stage, encode(detail), now()))

    def environment(self, db, tenant, customer):
        row = db.execute('SELECT * FROM environments WHERE tenant=? AND customer=?', (tenant, customer)).fetchone()
        if not row:
            raise Problem(404, 'Ambiente não encontrado.')
        return {**dict(row), 'state': json.loads(row['state'])}

    def case(self, db, tenant, customer, case_id):
        row = db.execute('SELECT * FROM cases WHERE id=? AND tenant=? AND customer=?', (case_id, tenant, customer)).fetchone()
        if not row:
            raise Problem(404, 'Caso não encontrado nesta SaaS e cliente.')
        return self.decode_case(row)

    @staticmethod
    def decode_case(row):
        result = dict(row)
        for key in ('observation', 'detection', 'investigation', 'decision', 'verification'):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    @staticmethod
    def bucket(case):
        if not case:
            return 'observation'
        stage = case['stage']
        if stage == 'verified':
            result = case['verification']
            if result['operational_recovered'] and result['value_recovered']:
                return 'recovery'
            return 'intervention' if result['operational_recovered'] else 'exceptions'
        return {'observed': 'observation', 'detected': 'deterioration',
                'investigated': 'investigation', 'decided': 'intervention',
                'executed': 'intervention', 'healthy': 'stable'}.get(stage, 'exceptions')

    def view(self, user, tenant=None, customer=None, case_id=None):
        with self.store.transaction() as db:
            memberships = [dict(r) for r in db.execute('SELECT tenant,role FROM memberships WHERE user_id=? ORDER BY tenant', (user,))]
            if tenant:
                self.authorize(db, user, tenant)
            if (customer and not tenant) or (case_id and not customer):
                raise Problem(400, 'Selecionar SaaS e cliente para consultar um caso.')
            registry = []
            rows = db.execute("""SELECT e.tenant,e.customer,e.name,c.id,c.stage,c.verification FROM environments e
                JOIN memberships m ON m.tenant=e.tenant AND m.user_id=?
                LEFT JOIN cases c ON c.id=(SELECT latest.id FROM cases latest
                    WHERE latest.tenant=e.tenant AND latest.customer=e.customer
                    ORDER BY latest.created_at DESC,latest.id DESC LIMIT 1)
                WHERE (? IS NULL OR e.tenant=?) ORDER BY e.tenant,e.name,e.customer""", (user,tenant,tenant)).fetchall()
            counts = dict.fromkeys(('observation','deterioration','investigation','intervention','recovery','exceptions','stable'),0)
            for row in rows:
                case = {'stage':row['stage'], 'verification':json.loads(row['verification']) if row['verification'] else None} if row['id'] else None
                bucket = self.bucket(case)
                counts[bucket] += 1
                registry.append({'tenant':row['tenant'], 'customer':row['customer'], 'name':row['name'],
                                 'case_id':row['id'], 'stage':row['stage'], 'bucket':bucket})
            result = {'user':user, 'memberships':memberships, 'decision_mode':c04.MODE,
                      'environment_type':'sandbox', 'registry':registry, 'counts':counts}
            if customer is not None:
                role = self.authorize(db,user,tenant)
                env = self.environment(db,tenant,customer)
                cases = db.execute('SELECT * FROM cases WHERE tenant=? AND customer=? ORDER BY created_at DESC,id DESC', (tenant,customer)).fetchall()
                case = self.case(db,tenant,customer,case_id) if case_id else self.decode_case(cases[0]) if cases else None
                history = db.execute("""SELECT h.* FROM history h LEFT JOIN cases c ON c.id=h.case_id AND c.tenant=h.tenant
                    WHERE h.tenant=? AND (c.customer=? OR (h.case_id IS NULL AND json_extract(h.detail,'$.customer')=?)) ORDER BY h.id""", (tenant,customer,customer)).fetchall()
                result.update({'role':role, 'environment':env, 'case':case,
                    'cases':[{'id':r['id'],'stage':r['stage'],'created_at':r['created_at']} for r in cases],
                    'latest_case_id':cases[0]['id'] if cases else None,
                    'catalogue':{k:v for k,v in c04.CATALOGUE.items() if v['tenant']==tenant},
                    'history':[{**dict(r),'detail':json.loads(r['detail'])} for r in history]})
            return result

    def create_customer(self, user, tenant, customer, name, scenario='blocked'):
        with self.store.transaction() as db:
            self.authorize(db,user,tenant,write=True)
            if not isinstance(customer,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',customer):
                raise Problem(400,'ID: 1–64 letras minúsculas, números, hífen ou underscore.')
            if not isinstance(name,str) or not 1 <= len(name.strip()) <= 120:
                raise Problem(400,'Nome deve conter 1–120 caracteres.')
            if scenario not in ('blocked','operational') or tenant not in ('atlas','nimbus'):
                raise Problem(400,'Cenário de sandbox não autorizado.')
            if db.execute('SELECT 1 FROM environments WHERE tenant=? AND customer=?',(tenant,customer)).fetchone():
                raise Problem(409,'Já existe um cliente com este ID nesta SaaS.')
            state = ({'connector':'paused' if scenario=='blocked' else 'active',
                      'backlog':[{'id':f'job-{i}','status':'pending'} for i in range(12)] if scenario=='blocked' else [],
                      'completed_outcomes':0} if tenant=='atlas' else
                     {'workflow_enabled':scenario=='operational','completed_outcomes':0})
            db.execute('INSERT INTO environments VALUES (?,?,?,?,0)',(tenant,customer,name.strip(),encode(state)))
            self.audit(db,tenant,None,user,'CUSTOMER',{'customer':customer,'name':name.strip(),'scenario':scenario,'scope':'sandbox'})
            return {'customer':customer}

    def ingest(self, user, tenant, customer, observations):
        with self.store.transaction() as db:
            self.authorize(db,user,tenant,write=True)
            self.environment(db,tenant,customer)
            if not isinstance(observations,list) or not 1 <= len(observations) <= 366:
                raise Problem(400,'Enviar entre 1 e 366 observações por lote.')
            normalized, days = [], set()
            for line,row in enumerate(observations,1):
                if not isinstance(row,dict) or set(row) != {'day','value','source'}:
                    raise Problem(400,f'Linha {line}: campos obrigatórios day, value, source; sem campos extra.')
                try:
                    day = date.fromisoformat(row['day'])
                except (TypeError,ValueError):
                    raise Problem(400,f'Linha {line}: data inválida.')
                if row['day'] != day.isoformat() or not date.today()-timedelta(days=365) <= day <= date.today():
                    raise Problem(400,f'Linha {line}: data canónica, até hoje e no máximo 365 dias atrás.')
                if type(row['value']) is not int or not 0 <= row['value'] <= 1000000:
                    raise Problem(400,f'Linha {line}: value deve ser inteiro entre 0 e 1000000.')
                if not isinstance(row['source'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',row['source']):
                    raise Problem(400,f'Linha {line}: source deve ter 1–64 caracteres simples.')
                if row['day'] in days:
                    raise Problem(400,f'Linha {line}: dia repetido no lote.')
                days.add(row['day'])
                normalized.append(dict(row))
            normalized.sort(key=lambda row:row['day'])
            digest = hashlib.sha256(encode(normalized).encode()).hexdigest()
            prior = db.execute('SELECT id,inserted FROM ingestion_batches WHERE tenant=? AND customer=? AND payload_hash=?',(tenant,customer,digest)).fetchone()
            if prior:
                return {'batch_id':prior['id'],'inserted':0,'reused':True}
            inserted = 0
            for row in normalized:
                prior = db.execute('SELECT value,source FROM observations WHERE tenant=? AND customer=? AND day=?',(tenant,customer,row['day'])).fetchone()
                if prior:
                    if prior['value'] != row['value'] or prior['source'] != row['source']:
                        raise Problem(409,f"Já existe outra observação para {row['day']}; dados append-only não são sobrescritos. Lote revertido.")
                    continue
                db.execute('INSERT INTO observations(tenant,customer,day,value,source,created_at) VALUES (?,?,?,?,?,?)',(tenant,customer,row['day'],row['value'],row['source'],now()))
                inserted += 1
            batch_id = uuid.uuid4().hex
            db.execute('INSERT INTO ingestion_batches VALUES (?,?,?,?,?,?,?)',(batch_id,tenant,customer,user,digest,inserted,now()))
            self.audit(db,tenant,None,user,'INGEST',{'customer':customer,'batch_id':batch_id,'inserted':inserted,'source':'manual-sandbox'})
            if inserted:
                active = db.execute("SELECT id FROM cases WHERE tenant=? AND customer=? AND stage IN ('observed','detected','investigated','decided')",(tenant,customer)).fetchall()
                for case in active:
                    db.execute("UPDATE cases SET stage='stale_evidence' WHERE id=? AND tenant=? AND customer=?",(case['id'],tenant,customer))
                    self.audit(db,tenant,case['id'],user,'CORE',{'reason':'Novas observações; iniciar novo ciclo para reconstruir evidências.'})
            return {'batch_id':batch_id,'inserted':inserted,'reused':False}

    def assert_latest(self, db, tenant, customer, case_id):
        latest = db.execute('SELECT id FROM cases WHERE tenant=? AND customer=? ORDER BY created_at DESC,id DESC LIMIT 1',(tenant,customer)).fetchone()
        if not latest or latest['id'] != case_id:
            raise Problem(409,'Caso histórico: consultar os registos existentes; novas operações exigem o ciclo mais recente.')

    def advance(self, user, tenant, customer, case_id=None):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            env = self.environment(db, tenant, customer)
            if not case_id:
                existing = db.execute("SELECT id FROM cases WHERE tenant=? AND customer=? AND stage IN ('observed','detected','investigated','decided','executed')", (tenant, env['customer'])).fetchone()
                if existing:
                    return {'case_id': existing['id'], 'reused': True}
                case_id = uuid.uuid4().hex
                obs = c01.observe(db, tenant, env['customer'])
                db.execute('INSERT INTO cases(id,tenant,customer,stage,observation,created_at) VALUES (?,?,?,?,?,?)', (case_id, tenant, env['customer'], 'observed', encode(obs), now()))
                self.audit(db, tenant, case_id, user, 'C01', obs)
                return {'case_id': case_id}
            case = self.case(db, tenant, customer, case_id)
            stage = case['stage']
            if stage == 'observed':
                result = c02.detect(case['observation'])
                next_stage = 'detected' if result['status'] == 'deteriorating' else result['status']
                db.execute('UPDATE cases SET stage=?, detection=? WHERE id=? AND tenant=?', (next_stage, encode(result), case_id, tenant))
                self.audit(db, tenant, case_id, user, 'C02', result)
            elif stage == 'detected':
                result = c03.investigate(env, case['observation'], case['detection'])
                db.execute('UPDATE cases SET stage=?, investigation=? WHERE id=? AND tenant=?', ('investigated', encode(result), case_id, tenant))
                self.audit(db, tenant, case_id, user, 'C03', result)
            elif stage == 'investigated':
                result = c04.decide(tenant, case['investigation'])
                next_stage = 'decided' if result['action'] else 'needs_review'
                db.execute('UPDATE cases SET stage=?, decision=? WHERE id=? AND tenant=?', (next_stage, encode(result), case_id, tenant))
                self.audit(db, tenant, case_id, user, 'C04', result)
            else:
                raise Problem(409, 'Transição inválida. Use executar ou verificar, conforme o estado do caso.')
            return {'case_id': case_id}

    def execute(self, user, tenant, customer, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, customer, case_id)
            if db.execute('SELECT 1 FROM executions WHERE case_id=? AND tenant=?', (case_id, tenant)).fetchone():
                return {'case_id': case_id, 'reused': True}
            if case['stage'] != 'decided':
                raise Problem(409, 'A execução exige uma decisão autorizada.')
            env = self.environment(db, tenant, customer)
            action_id = case['decision']['action']
            action = c04.CATALOGUE.get(action_id)
            if not action or action['tenant'] != tenant or action['cause'] != case['investigation']['cause']:
                raise Problem(403, 'Ação fora do catálogo autorizado para esta SaaS e evidência.')
            if env['revision'] != case['investigation']['revision'] or env['state'] != case['investigation']['state']:
                raise Problem(409, 'Evidência desatualizada: ambiente alterado desde a investigação.')
            after = c05.intervene(action_id, env['state'])
            db.execute('UPDATE environments SET state=?, revision=revision+1 WHERE tenant=? AND customer=?', (encode(after), tenant, env['customer']))
            db.execute('INSERT INTO executions VALUES (?,?,?,?,?,?)', (case_id, tenant, action_id, encode(env['state']), encode(after), now()))
            db.execute('UPDATE cases SET stage=? WHERE id=? AND tenant=?', ('executed', case_id, tenant))
            self.audit(db, tenant, case_id, user, 'C05', {'action': action_id, 'before': env['state'], 'after': after, 'execution_key': case_id})
            return {'case_id': case_id, 'reused': False}

    def verify(self, user, tenant, customer, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, customer, case_id)
            if case['stage'] not in ('executed', 'verified'):
                raise Problem(409, 'Verificação exige uma intervenção executada.')
            self.assert_latest(db,tenant,customer,case_id)
            execution = db.execute('SELECT before_state FROM executions WHERE case_id=? AND tenant=?', (case_id, tenant)).fetchone()
            env = self.environment(db, tenant, customer)
            result = c06.verify(env['state'], json.loads(execution['before_state']))
            db.execute('UPDATE cases SET stage=?, verification=? WHERE id=? AND tenant=?', ('verified', encode(result), case_id, tenant))
            self.audit(db, tenant, case_id, user, 'C06', {**result, 'revision': env['revision']})
            return result

    def simulate_usage(self, user, tenant, customer, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, customer, case_id)
            env = self.environment(db, tenant, customer)
            self.assert_latest(db,tenant,customer,case_id)
            if tenant != 'nimbus' or case['stage'] not in ('executed', 'verified') or not env['state'].get('workflow_enabled'):
                raise Problem(409, 'Simulação de uso exige o percurso Nimbus ativado por uma intervenção.')
            state = env['state']
            if state.get('usage_batch'):
                return {'reused': True}
            state['usage_batch'] = [{'report': i, 'status': 'completed', 'source': 'simulated-customer-usage'} for i in range(4)]
            state['completed_outcomes'] += len(state['usage_batch'])
            db.execute('UPDATE environments SET state=?,revision=revision+1 WHERE tenant=? AND customer=?', (encode(state), tenant, env['customer']))
            self.audit(db, tenant, case_id, user, 'SANDBOX', {'event': 'simulated-customer-usage', 'reports_completed': 4})
            return {'reused': False}
