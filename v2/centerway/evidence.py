"""Inactive, tenant/customer/configuration-scoped evidence. No C01–C06 execution."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import math
import sqlite3

from .core import Core, Problem
from .http_contract import strict_json
from .integration_contract import fields, identifier, shape, text, timestamp
from .integrations import IntegrationRepository, canonical, digest
from .store import Store, now

MAX_RECORDS = 100
MAX_CUSTOMER_RECORDS = 1000
MAX_CUSTOMER_BATCHES = 5000
MAX_RECORD_BYTES = 8192
TABLES = {
    'evidence_metadata': "CREATE TABLE evidence_metadata(marker TEXT PRIMARY KEY CHECK(marker='inactive-evidence-v1'), mode TEXT NOT NULL CHECK(mode IN ('sandbox','demo','production')))",
    'evidence_items': "CREATE TABLE evidence_items(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, config_version INTEGER NOT NULL, config_hash TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('event','metric','evidence')), definition_id TEXT NOT NULL, source_ref TEXT NOT NULL, external_id TEXT NOT NULL, occurred_at TEXT NOT NULL, period_start TEXT, period_end TEXT, payload TEXT NOT NULL, content_hash TEXT NOT NULL, fact_hash TEXT NOT NULL, actor TEXT NOT NULL, received_at TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer,kind,definition_id,source_ref,external_id), FOREIGN KEY(tenant,config_version) REFERENCES integration_versions(tenant,version))",
    'evidence_batches': "CREATE TABLE evidence_batches(id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL, config_version INTEGER NOT NULL, request_hash TEXT NOT NULL, actor TEXT NOT NULL, received_at TEXT NOT NULL, result TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(tenant,customer,config_version,request_hash), FOREIGN KEY(tenant,config_version) REFERENCES integration_versions(tenant,version))",
}
GUARDS = {
    f'evidence_immutable_{table}_{operation}':
        f"CREATE TRIGGER evidence_immutable_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    for table in TABLES for operation in ('UPDATE','DELETE')
}
INDEXES = {
    'evidence_customer_version': 'CREATE INDEX evidence_customer_version ON evidence_items(tenant,customer,config_version,id)',
    'evidence_customer_fact': 'CREATE INDEX evidence_customer_fact ON evidence_items(tenant,customer,config_version,fact_hash)',
}


def invalid(reason):
    raise Problem(400,'Evidência incompatível: '+reason)


def customer_id(value):
    text(value,'customer',128)
    if value!=value.strip(): invalid('identificador de cliente não canónico.')


def utc(value):
    timestamp(value,'timestamp')
    return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat(timespec='microseconds').replace('+00:00','Z')


def scalar(value, kind):
    if kind=='boolean': valid=type(value) is bool
    elif kind=='integer': valid=type(value) is int and abs(value)<=2**53-1
    elif kind=='number': valid=type(value) in (int,float) and abs(value)<=2**53-1 and math.isfinite(value)
    else:
        text(value,'payload.value')
        return utc(value) if kind=='timestamp' else value
    if not valid: invalid('tipo ou limite de valor inválido.')
    return int(value) if kind=='number' and type(value) is float and value.is_integer() else value


def normalize(record, config, customer, received_at):
    shape(record,'external_id kind definition_id source_ref occurred_at period payload','record')
    text(record['external_id'],'external_id',128)
    if record['external_id']!=record['external_id'].strip(): invalid('external_id não canónico.')
    kind=record['kind']
    if kind not in ('event','metric','evidence'): invalid('tipo de registo desconhecido.')
    identifier(record['definition_id'],'definition_id')
    definition=next((d for d in config[{'event':'events','metric':'metrics','evidence':'evidence'}[kind]] if d['id']==record['definition_id']),None)
    if not definition: invalid('definição inexistente nesta versão.')
    if record['source_ref']!=definition['source_ref']: invalid('origem diferente da configuração.')
    if kind=='evidence' and definition['availability']!='declared': invalid('evidência declarada indisponível.')
    occurred=utc(record['occurred_at'])
    if occurred>received_at: invalid('momento futuro não autorizado.')
    period=record['period']
    needs_period=kind=='metric' or (kind=='evidence' and definition['kind']=='metric')
    if needs_period:
        shape(period,'start end','period')
        period={'start':utc(period['start']),'end':utc(period['end'])}
        if not period['start']<period['end'] or period['end']>occurred:
            invalid('período vazio/invertido ou posterior ao acontecimento.')
    elif period is not None: invalid('período apenas para métricas ou evidência do tipo metric.')
    expected={'value':{'type':definition['value_type'],'required':True}} if kind=='metric' else fields(definition['fields'],'fields')
    payload=record['payload']
    if not isinstance(payload,dict) or not payload or set(payload)-set(expected) or any(f['required'] and key not in payload for key,f in expected.items()):
        invalid('campos ausentes ou não declarados no payload.')
    payload={key:scalar(value,expected[key]['type']) for key,value in payload.items()}
    identity_field=definition['customer_id_field'] if kind=='event' else config['customers']['id_field']
    if identity_field in payload and payload[identity_field]!=customer: invalid('identidade do cliente divergente.')
    if 'occurred_at' in payload:
        payload['occurred_at']=utc(payload['occurred_at'])
        if payload['occurred_at']!=occurred: invalid('momentos divergentes no envelope e payload.')
    normalized={**record,'occurred_at':occurred,'period':period,'payload':payload}
    if len(canonical(normalized).encode('utf-8'))>MAX_RECORD_BYTES: raise Problem(413,'Registo excede 8192 bytes.')
    return normalized


def install(store):
    integration=IntegrationRepository(store)
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'evidence_*'").fetchone():
            raise ValueError('Evidence storage already exists; no repair.')
        for sql in {**TABLES,**GUARDS,**INDEXES}.values(): db.execute(sql)
        db.execute('INSERT INTO evidence_metadata VALUES (?,?)',('inactive-evidence-v1',integration.mode))
    return {'status':'initialized','mode':integration.mode,'operational_state':'inactive'}


class EvidenceRepository:
    """Only authenticated server principals; no browser role claims or Core side effects."""
    def __init__(self, store):
        self.store=store
        try:
            self.integrations=IntegrationRepository(store)
            with closing(store.connect()) as db: self._storage(db)
        except (ValueError,sqlite3.Error):
            raise Problem(503,'Armazenamento de evidências indisponível; preparação/integridade necessária.')

    def _storage(self, db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'evidence_*'")}
        if any(schema.get(name)!=sql for name,sql in {**TABLES,**GUARDS,**INDEXES}.items()):
            raise ValueError('Evidence schema/protections unavailable.')
        row=db.execute('SELECT marker,mode FROM evidence_metadata').fetchall()
        if len(row)!=1 or row[0]['marker']!='inactive-evidence-v1' or row[0]['mode']!=self.integrations.mode:
            raise ValueError('Evidence mode mismatch.')

    def _runtime(self):
        try: self.integrations._runtime()
        except (ValueError,sqlite3.Error): raise Problem(503,'Modo ou integridade da configuração indisponível.')

    def _snapshot(self, db, user, tenant, customer, version, write=False):
        identifier(tenant,'tenant');customer_id(customer)
        # Authorization precedes configuration/evidence lookup, including missing scopes.
        Core(self.store).authorize(db,user,tenant,write=write)
        if type(version) is not int or version<1 or version>2**31-1: invalid('config_version explícita e positiva necessária.')
        try:
            self.integrations._storage(db);self._storage(db)
            chain=self.integrations._chain(db,tenant)
        except (ValueError,sqlite3.Error,TypeError,KeyError):
            raise Problem(503,'Integridade de configuração/evidências não confirmada.')
        if version>len(chain): raise Problem(404,'Versão de configuração inexistente nesta SaaS.')
        return chain[version-1]

    def _records(self, db, tenant, customer, configs):
        try: return self._read_records(db,tenant,customer,configs)
        except (ValueError,TypeError,KeyError,AttributeError,sqlite3.Error):
            raise Problem(503,'Integridade de evidências não confirmada.')

    def _read_records(self, db, tenant, customer, configs):
        result=[]
        for row in db.execute('SELECT * FROM evidence_items WHERE tenant=? AND customer=? ORDER BY id',(tenant,customer)):
            record=dict(row);claimed=record.pop('record_hash')
            if claimed!=digest(record): raise Problem(503,'Integridade de evidências não confirmada.')
            version=record['config_version']
            if not 1<=version<=len(configs) or configs[version-1]['content_hash']!=record['config_hash']:
                raise Problem(503,'Proveniência da configuração não confirmada.')
            payload=strict_json(record['payload'].encode('utf-8'))
            if canonical(payload)!=record['payload']: raise Problem(503,'Payload de evidências não canónico.')
            result.append({**record,'record_hash':claimed,'payload':payload})
        return result

    def ingest(self, user, body):
        self._runtime()
        shape(body,'tenant customer config_version records','request')
        tenant,customer,version=body['tenant'],body['customer'],body['config_version']
        if not isinstance(body['records'],list) or not 1<=len(body['records'])<=MAX_RECORDS:
            invalid('lote exige entre 1 e 100 registos.')
        if len(canonical(body).encode('utf-8'))>65536: raise Problem(413,'Lote excede 65536 bytes.')
        with self.store.transaction() as db:
            snapshot=self._snapshot(db,user,tenant,customer,version,write=True)
            return self._ingest(db,user,body,snapshot)

    def _ingest(self, db, user, body, snapshot):
        """Shared M07 persistence; caller supplies a transaction and authorized snapshot.

        Human ingest authorizes through Core; private webhook intake authenticates
        its own strictly scoped service grant before calling this internal method.
        """
        tenant,customer,version=body['tenant'],body['customer'],body['config_version']
        received=utc(now())
        records=[normalize(r,snapshot['config'],customer,received) for r in body['records']]
        request_hash=digest(records)
        existing_batch=db.execute('SELECT * FROM evidence_batches WHERE tenant=? AND customer=? AND config_version=? AND request_hash=?',(tenant,customer,version,request_hash)).fetchone()
        configs=self.integrations._chain(db,tenant)
        stored=self._records(db,tenant,customer,configs)
        if existing_batch:
            batch=dict(existing_batch);claimed=batch.pop('record_hash')
            if claimed!=digest(batch): raise Problem(503,'Integridade do lote não confirmada.')
            result=strict_json(batch['result'].encode('utf-8'))
            indexed={r['id']:r for r in stored}
            if len(result['record_ids'])!=len(records) or any(
                    item not in indexed or indexed[item]['config_version']!=version or indexed[item]['content_hash']!=digest(record)
                    for item,record in zip(result['record_ids'],records)):
                raise Problem(503,'Proveniência do lote não confirmada.')
            return {**result,'inserted':0,'duplicates':len(records),'batch_id':batch['id'],'reused':True}
        ids=[];inserted=0;reused=0
        for record in records:
            identity={key:record[key] for key in ('kind','definition_id','source_ref','external_id')}
            content_hash=digest(record)
            previous=next((r for r in stored if all(r[k]==v for k,v in identity.items())),None)
            if previous:
                if previous['config_version']!=version or previous['content_hash']!=content_hash:
                    raise Problem(409,'Identidade de origem já utilizada com conteúdo/versão diferente; histórico preservado.')
                ids.append(previous['id']);reused+=1;continue
            fact={key:record[key] for key in ('kind','definition_id','source_ref','occurred_at','period')}
            fact_hash=digest(fact)
            if record['kind']!='event' and any(r['config_version']==version and r['fact_hash']==fact_hash and r['payload']==record['payload'] for r in stored):
                raise Problem(409,'Snapshot duplicado com outro external_id; reutilize a identidade original.')
            if len(stored)>=MAX_CUSTOMER_RECORDS: raise Problem(413,'Limite de 1000 evidências por cliente atingido.')
            row={'tenant':tenant,'customer':customer,'config_version':version,'config_hash':snapshot['content_hash'],
                 **{k:record[k] for k in ('kind','definition_id','source_ref','external_id','occurred_at')},
                 'period_start':record['period']['start'] if record['period'] else None,
                 'period_end':record['period']['end'] if record['period'] else None,
                 'payload':canonical(record['payload']),'content_hash':content_hash,'fact_hash':fact_hash,'actor':user,'received_at':received}
            # Include the generated id in the integrity hash without ever updating a row.
            row['id']=db.execute('SELECT coalesce(max(id),0)+1 FROM evidence_items').fetchone()[0]
            row['record_hash']=digest(row)
            db.execute('INSERT INTO evidence_items ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
            stored.append({**row,'payload':record['payload']});ids.append(row['id']);inserted+=1
        if db.execute('SELECT count(*) FROM evidence_batches WHERE tenant=? AND customer=?',(tenant,customer)).fetchone()[0]>=MAX_CUSTOMER_BATCHES:
            raise Problem(413,'Limite de 5000 lotes por cliente atingido.')
        result={'tenant':tenant,'customer':customer,'config_version':version,'config_hash':snapshot['content_hash'],
                'operational_state':'inactive','classification':snapshot['config']['data_classification'],
                'inserted':inserted,'duplicates':reused,'record_ids':ids}
        batch={'tenant':tenant,'customer':customer,'config_version':version,'request_hash':request_hash,'actor':user,
               'received_at':received,'result':canonical(result)}
        batch['id']=db.execute('SELECT coalesce(max(id),0)+1 FROM evidence_batches').fetchone()[0]
        batch['record_hash']=digest(batch)
        db.execute('INSERT INTO evidence_batches ('+','.join(batch)+') VALUES ('+','.join('?' for _ in batch)+')',tuple(batch.values()))
        return {**result,'batch_id':batch['id'],'reused':False}

    def query(self, user, tenant, customer, config_version, after=0, through=None, limit=100):
        self._runtime()
        if any(type(v) is not int or v<0 or v>2**53-1 for v in (after,limit)) or not 1<=limit<=100:
            invalid('paginação inválida.')
        if through is not None and (type(through) is not int or not 0<=through<=2**53-1): invalid('through inválido.')
        with self.store.transaction() as db:
            snapshot=self._snapshot(db,user,tenant,customer,config_version)
            rows=self._records(db,tenant,customer,self.integrations._chain(db,tenant))
            latest=max((r['id'] for r in rows),default=0)
            through=latest if through is None else through
            if through>latest: invalid('through posterior às evidências recebidas.')
            if after>through: invalid('after posterior ao snapshot through.')
            visible=[r for r in rows if r['id']<=through]
            selected=[r for r in visible if r['config_version']==config_version]
            page=[r for r in selected if r['id']>after]
            config=snapshot['config'];expected=[{'kind':kind,'definition_id':d['id']} for kind,key in (('event','events'),('metric','metrics'),('evidence','evidence')) for d in config[key]]
            missing=[d for d in expected if not any(all(r[k]==v for k,v in d.items()) for r in selected)]
            conflicts=[];groups={}
            for row in selected:
                if row['kind']!='event': groups.setdefault(row['fact_hash'],[]).append(row)
            for group in groups.values():
                values={}
                for row in group:
                    for field,value in row['payload'].items(): values.setdefault(field,set()).add(canonical(value))
                if any(len(v)>1 for v in values.values()):
                    conflicts.append({'kind':group[0]['kind'],'definition_id':group[0]['definition_id'],'record_ids':[r['id'] for r in group]})
            quality={'status':'contradictory' if conflicts else 'incompatible' if visible and not selected else 'insufficient' if missing or not expected else 'compatible',
                     'missing':missing,'conflicts':conflicts,'excluded_other_versions':len(visible)-len(selected),'conclusion':'not_evaluated'}
            return {'tenant':tenant,'customer':customer,'config_version':config_version,'config_hash':snapshot['content_hash'],
                    'operational_state':'inactive','classification':config['data_classification'],'quality':quality,
                    'through':through,'next_after':page[limit-1]['id'] if len(page)>limit else None,'records':page[:limit]}


def main():
    parser=argparse.ArgumentParser(description='Prepare inactive evidence storage locally; ingestion is authenticated HTTP.')
    parser.add_argument('command',choices=['init']);parser.add_argument('--db',required=True)
    args=parser.parse_args()
    try: result=install(Store.open_existing(args.db))
    except (ValueError,OSError,sqlite3.Error,Problem): parser.exit(1,'{"status":"error","code":"evidence_refused"}\n')
    print(canonical(result))


if __name__=='__main__': main()
