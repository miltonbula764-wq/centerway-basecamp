"""Explicit local synthetic SQLite service. No network, shell or production connector."""
import sqlite3
from contextlib import closing
from pathlib import Path

from .core import Problem
from .execution_adapter import ExecutionAdapter,ExecutionReceipt
from .integrations import canonical,digest
from .http_contract import strict_json
from .store import now

SCHEMA={
 'synthetic_metadata':"CREATE TABLE synthetic_metadata(marker TEXT PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, capability TEXT NOT NULL, usage_step INTEGER NOT NULL, fault TEXT NOT NULL)",
 'synthetic_state':"CREATE TABLE synthetic_state(tenant TEXT NOT NULL, customer TEXT NOT NULL, revision INTEGER NOT NULL, paused INTEGER NOT NULL, outcome_count INTEGER NOT NULL, PRIMARY KEY(tenant,customer))",
 'synthetic_effects':"CREATE TABLE synthetic_effects(key TEXT PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, before_revision TEXT NOT NULL, after_revision TEXT NOT NULL, created_at TEXT NOT NULL, record_hash TEXT NOT NULL)",
 'synthetic_samples':"CREATE TABLE synthetic_samples(key TEXT PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, scheduled_at TEXT NOT NULL, observed_at TEXT NOT NULL, paused INTEGER NOT NULL, outcome_count INTEGER NOT NULL, record_hash TEXT NOT NULL)",
}
GUARDS={f'synthetic_immutable_{table}_{op}':f"CREATE TRIGGER synthetic_immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append_only'); END" for table in ('synthetic_metadata','synthetic_effects','synthetic_samples') for op in ('UPDATE','DELETE')}


def install(path,tenant,customer,capability,usage_step=2,fault='none'):
    if Path(path).exists() or usage_step not in (0,2) or fault not in ('none','uncertain_after_effect'): raise ValueError('New explicit synthetic service required.')
    with sqlite3.connect(path) as db:
        for sql in {**SCHEMA,**GUARDS}.values(): db.execute(sql)
        db.execute('INSERT INTO synthetic_metadata VALUES (?,?,?,?,?,?)',('synthetic-local-v1',tenant,customer,capability,usage_step,fault))
        db.execute('INSERT INTO synthetic_state VALUES (?,?,1,1,1)',(tenant,customer))
    Path(path).chmod(0o600)


class SyntheticService(ExecutionAdapter):
    def __init__(self,path):
        self.path=Path(path).resolve(strict=True)
        if self.path.stat().st_mode & 0o077: raise ValueError('Private synthetic service required.')
        with closing(self.connect()) as db:
            schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'synthetic_*'")}
            if any(schema.get(k)!=v for k,v in {**SCHEMA,**GUARDS}.items()): raise ValueError('Synthetic service integrity unavailable.')
            rows=db.execute('SELECT * FROM synthetic_metadata').fetchall()
            if len(rows)!=1 or rows[0]['marker']!='synthetic-local-v1': raise ValueError('Not an explicit synthetic service.')
            self.metadata=dict(rows[0])
    def connect(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=10);db.row_factory=sqlite3.Row;return db
    def descriptor(self):
        return {'kind':'test_adapter','adapter_id':'observable-synthetic-sqlite','version':'v1','tenant':self.metadata['tenant'],
                'capability_id':self.metadata['capability'],'idempotent':True,'atomic_conditions':True}
    def _scope(self,binding):
        if (binding['tenant']!=self.metadata['tenant'] or binding['customer']!=self.metadata['customer']
            or binding.get('classification')!='synthetic' or binding['capability']['id']!=self.metadata['capability']):
            raise Problem(403,'Adaptador exclusivamente sintético; escopo recusado.')
    def observe(self,binding):
        self._scope(binding)
        with closing(self.connect()) as db: row=db.execute('SELECT * FROM synthetic_state WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer'])).fetchone()
        if not row: raise Problem(404,'Estado sintético inexistente.')
        return {'tenant':binding['tenant'],'customer':binding['customer'],'capability_id':self.metadata['capability'],
                'revision':str(row['revision']),'observed_at':now(),
                'facts':[{'evidence_ref':'operation-state','field':'paused','value':bool(row['paused'])}]}
    def apply(self,key,binding,snapshot):
        self._scope(binding)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM synthetic_effects WHERE key=?',(key,)).fetchone()
            if old:
                self._check(old)
                if old['tenant']!=binding['tenant'] or old['customer']!=binding['customer']: raise Problem(403,'Chave de outro escopo.')
                return ExecutionReceipt('test_applied','synthetic-'+key[:24],old['before_revision'],old['after_revision'])
            row=db.execute('SELECT * FROM synthetic_state WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer'])).fetchone()
            if not row or str(row['revision'])!=snapshot['revision'] or not row['paused']:
                return ExecutionReceipt('failed_no_effect','synthetic-fenced',snapshot['revision'],None)
            db.execute('UPDATE synthetic_state SET paused=0,revision=revision+1 WHERE tenant=? AND customer=?',(binding['tenant'],binding['customer']))
            effect={'key':key,'tenant':binding['tenant'],'customer':binding['customer'],'before_revision':str(row['revision']),
                    'after_revision':str(row['revision']+1),'created_at':now()};effect['record_hash']=digest(effect)
            db.execute('INSERT INTO synthetic_effects VALUES (?,?,?,?,?,?,?)',tuple(effect.values()))
        if self.metadata['fault']=='uncertain_after_effect': raise TimeoutError('Explicit synthetic fault after committed effect.')
        return ExecutionReceipt('test_applied','synthetic-'+key[:24],effect['before_revision'],effect['after_revision'])
    def sample(self,key,scheduled_at):
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM synthetic_samples WHERE key=?',(key,)).fetchone()
            if old:
                if old['tenant']!=self.metadata['tenant'] or old['customer']!=self.metadata['customer']: raise Problem(403,'Amostra de outro escopo.')
                return self._check(old)
            row=db.execute('SELECT * FROM synthetic_state WHERE tenant=? AND customer=?',(self.metadata['tenant'],self.metadata['customer'])).fetchone()
            # Explicit synthetic workload, independent of receipt/verification outcome.
            count=row['outcome_count']+(self.metadata['usage_step'] if not row['paused'] else 0)
            db.execute('UPDATE synthetic_state SET outcome_count=? WHERE tenant=? AND customer=?',(count,row['tenant'],row['customer']))
            sample={'key':key,'tenant':row['tenant'],'customer':row['customer'],'scheduled_at':scheduled_at,'observed_at':now(),
                    'paused':row['paused'],'outcome_count':count};sample['record_hash']=digest(sample)
            db.execute('INSERT INTO synthetic_samples VALUES (?,?,?,?,?,?,?,?)',tuple(sample.values()))
            return sample
    def _check(self,row):
        row=dict(row);claimed=row.pop('record_hash')
        if digest(row)!=claimed: raise ValueError('Synthetic audit integrity failed.')
        return {**row,'record_hash':claimed}
    def inspect(self):
        with closing(self.connect()) as db:
            return {'classification':'synthetic_test_only','profile':self.metadata,'state':[dict(r) for r in db.execute('SELECT * FROM synthetic_state WHERE tenant=? AND customer=?',(self.metadata['tenant'],self.metadata['customer']))],
                    'effects':[self._check(r) for r in db.execute('SELECT * FROM synthetic_effects WHERE tenant=? AND customer=? ORDER BY created_at,key',(self.metadata['tenant'],self.metadata['customer']))],
                    'samples':[self._check(r) for r in db.execute('SELECT * FROM synthetic_samples WHERE tenant=? AND customer=? ORDER BY scheduled_at,key',(self.metadata['tenant'],self.metadata['customer']))]}
