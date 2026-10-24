"""Core — server-side identity, tenancy, transitions and atomic execution."""
import json
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

    def environment(self, db, tenant):
        row = db.execute('SELECT * FROM environments WHERE tenant=? AND customer=?', (tenant, 'customer-01')).fetchone()
        if not row:
            raise Problem(404, 'Ambiente não encontrado.')
        return {**dict(row), 'state': json.loads(row['state'])}

    def case(self, db, tenant, case_id):
        row = db.execute('SELECT * FROM cases WHERE id=? AND tenant=?', (case_id, tenant)).fetchone()
        if not row:
            raise Problem(404, 'Caso não encontrado nesta SaaS.')
        return self.decode_case(row)

    @staticmethod
    def decode_case(row):
        result = dict(row)
        for key in ('observation', 'detection', 'investigation', 'decision', 'verification'):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def view(self, user, tenant=None):
        with self.store.transaction() as db:
            memberships = [dict(r) for r in db.execute('SELECT tenant,role FROM memberships WHERE user_id=? ORDER BY tenant', (user,))]
            result = {'user': user, 'memberships': memberships, 'decision_mode': c04.MODE, 'environment_type': 'sandbox'}
            if tenant:
                role = self.authorize(db, user, tenant)
                result.update({'role': role, 'environment': self.environment(db, tenant), 'catalogue': {k: v for k, v in c04.CATALOGUE.items() if v['tenant'] == tenant}})
                row = db.execute('SELECT * FROM cases WHERE tenant=?', (tenant,)).fetchone()
                result['case'] = self.decode_case(row) if row else None
                result['history'] = [{**dict(r), 'detail': json.loads(r['detail'])} for r in db.execute('SELECT * FROM history WHERE tenant=? ORDER BY id', (tenant,))]
            return result

    def advance(self, user, tenant, case_id=None):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            env = self.environment(db, tenant)
            if not case_id:
                existing = db.execute('SELECT id FROM cases WHERE tenant=? AND customer=?', (tenant, env['customer'])).fetchone()
                if existing:
                    return {'case_id': existing['id'], 'reused': True}
                case_id = uuid.uuid4().hex
                obs = c01.observe(db, tenant, env['customer'])
                db.execute('INSERT INTO cases(id,tenant,customer,stage,observation,created_at) VALUES (?,?,?,?,?,?)', (case_id, tenant, env['customer'], 'observed', encode(obs), now()))
                self.audit(db, tenant, case_id, user, 'C01', obs)
                return {'case_id': case_id}
            case = self.case(db, tenant, case_id)
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

    def execute(self, user, tenant, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, case_id)
            if db.execute('SELECT 1 FROM executions WHERE case_id=? AND tenant=?', (case_id, tenant)).fetchone():
                return {'case_id': case_id, 'reused': True}
            if case['stage'] != 'decided':
                raise Problem(409, 'A execução exige uma decisão autorizada.')
            env = self.environment(db, tenant)
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

    def verify(self, user, tenant, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, case_id)
            if case['stage'] not in ('executed', 'verified'):
                raise Problem(409, 'Verificação exige uma intervenção executada.')
            execution = db.execute('SELECT before_state FROM executions WHERE case_id=? AND tenant=?', (case_id, tenant)).fetchone()
            env = self.environment(db, tenant)
            result = c06.verify(env['state'], json.loads(execution['before_state']))
            db.execute('UPDATE cases SET stage=?, verification=? WHERE id=? AND tenant=?', ('verified', encode(result), case_id, tenant))
            self.audit(db, tenant, case_id, user, 'C06', {**result, 'revision': env['revision']})
            return result

    def simulate_usage(self, user, tenant, case_id):
        with self.store.transaction() as db:
            self.authorize(db, user, tenant, write=True)
            case = self.case(db, tenant, case_id)
            env = self.environment(db, tenant)
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
