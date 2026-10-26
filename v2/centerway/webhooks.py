"""HMAC-authenticated intake only. No human impersonation or operational authority."""
import argparse
from contextlib import closing
import hashlib
import hmac
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from .core import Problem
from .evidence import EvidenceRepository, customer_id
from .http_contract import strict_json
from .integration_contract import identifier, shape, text, fields
from .integrations import canonical, digest
from .store import Store

PATH='/api/webhooks/ingest'
WINDOW=300
MAX_PER_MINUTE=120
MAX_RECEIPTS=100000
TABLES={
    'webhook_metadata': "CREATE TABLE webhook_metadata(marker TEXT PRIMARY KEY CHECK(marker='webhook-intake-v1'), mode TEXT NOT NULL)",
    'webhook_mappings': "CREATE TABLE webhook_mappings(source TEXT NOT NULL, version INTEGER NOT NULL, tenant TEXT NOT NULL, mapping_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source,version))",
    'webhook_keys': "CREATE TABLE webhook_keys(source TEXT NOT NULL, key_id TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE, PRIMARY KEY(source,key_id))",
    'webhook_receipts': "CREATE TABLE webhook_receipts(id INTEGER PRIMARY KEY, source TEXT NOT NULL, nonce TEXT NOT NULL, request_hash TEXT NOT NULL, received_at INTEGER NOT NULL, mapping_version INTEGER NOT NULL, mapping_hash TEXT NOT NULL, config_hash TEXT NOT NULL, key_id TEXT NOT NULL, body_hash TEXT NOT NULL, status INTEGER NOT NULL, result TEXT NOT NULL, evidence_ids TEXT NOT NULL, record_hash TEXT NOT NULL, UNIQUE(source,nonce), FOREIGN KEY(source,mapping_version) REFERENCES webhook_mappings(source,version), FOREIGN KEY(source,key_id) REFERENCES webhook_keys(source,key_id))",
}
GUARDS={f'webhook_immutable_{table}_{op}':f"CREATE TRIGGER webhook_immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END" for table in TABLES for op in ('UPDATE','DELETE')}
INDEXES={'webhook_rate':'CREATE INDEX webhook_rate ON webhook_receipts(source,received_at)'}


def private_bytes(path, limit):
    """Private owner-only regular files outside this checkout, no symlink leaf."""
    if not isinstance(path,(str,Path)): raise ValueError('Explicit private file path required.')
    path=Path(path)
    if not path.is_absolute() or Path(__file__).resolve().parents[2] in path.resolve().parents:
        raise ValueError('Private configuration must be outside the checkout.')
    fd=os.open(path,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode & 0o077 or info.st_size>limit:
            raise ValueError('Private owner-only regular file required.')
        with os.fdopen(fd,'rb',closefd=False) as stream: value=stream.read(limit+1)
        if len(value)>limit: raise ValueError('Private file too large.')
        return value
    finally: os.close(fd)


def token(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value): raise ValueError('Invalid identifier.')


def positive(value):
    if type(value) is not int or not 1<=value<=2**31-1: raise ValueError('Explicit positive version required.')


def load_config(path):
    config=strict_json(private_bytes(path,262144))
    shape(config,'schema_version mode sources','webhook configuration')
    if type(config['schema_version']) is not int or config['schema_version']!=1 or config['mode'] not in ('demo','production'):
        raise ValueError('Incompatible webhook configuration.')
    if not isinstance(config['sources'],list) or not 1<=len(config['sources'])<=100: raise ValueError('1–100 explicit sources required.')
    seen=set();owned=set();key_materials=set()
    for source in config['sources']:
        shape(source,'id tenant config_version config_hash mapping_version classification customers routes keys','source')
        token(source['id']);identifier(source['tenant'],'tenant')
        if source['id'] in seen: raise ValueError('Repeated source.')
        seen.add(source['id'])
        positive(source['config_version']);positive(source['mapping_version'])
        if not isinstance(source['config_hash'],str) or not re.fullmatch('[0-9a-f]{64}',source['config_hash']): raise ValueError('Pinned config hash required.')
        if source['classification'] not in ('test','declared') or source['classification']!=('test' if config['mode']=='demo' else 'declared'):
            raise ValueError('Source classification must match the isolated runtime.')
        if not isinstance(source['customers'],dict) or not 1<=len(source['customers'])<=10000: raise ValueError('Explicit customer allowlist required.')
        for external,internal in source['customers'].items():
            text(external,'external customer',128);customer_id(internal)
        if not isinstance(source['routes'],dict) or not 1<=len(source['routes'])<=100: raise ValueError('Explicit routes required.')
        for name,route in source['routes'].items():
            token(name);shape(route,'kind definition_id source_ref fields','route')
            if route['kind'] not in ('event','metric','evidence'): raise ValueError('Invalid record kind.')
            identifier(route['definition_id'],'definition_id');text(route['source_ref'],'source_ref')
            scope=(source['tenant'],route['source_ref'])
            if any(scope==other_scope and source['id']!=owner for other_scope,owner in owned):
                raise ValueError('Each contract source_ref must belong to one authenticated source.')
            owned.add((scope,source['id']))
            if not isinstance(route['fields'],dict) or not 1<=len(route['fields'])<=50: raise ValueError('Explicit fields required.')
            for target,selector in route['fields'].items():
                text(target,'target field',128)
                if not isinstance(selector,str) or not (selector in ('$customer','$occurred_at') or re.fullmatch(r'data\.[A-Za-z0-9_-]{1,64}',selector)):
                    raise ValueError('Only direct data fields and explicit envelope references are supported.')
        if not isinstance(source['keys'],list) or not 1<=len(source['keys'])<=2: raise ValueError('One or two keys required.')
        kids=set()
        for key in source['keys']:
            shape(key,'id secret_file not_before expires_at','key');token(key['id'])
            if key['id'] in kids: raise ValueError('Duplicate key id.')
            kids.add(key['id'])
            if any(type(key[k]) is not int or not 0<=key[k]<=2**53-1 for k in ('not_before','expires_at')) or key['not_before']>=key['expires_at']:
                raise ValueError('Explicit finite credential window required.')
            secret=private_bytes(key['secret_file'],128).strip()
            if not re.fullmatch(b'[0-9a-f]{64}',secret): raise ValueError('Secret must contain 32 random bytes as lowercase hex.')
            fingerprint=hashlib.sha256(secret).digest()
            if fingerprint in key_materials: raise ValueError('Every configured credential requires independent key material.')
            key_materials.add(fingerprint)
            key['_secret']=bytes.fromhex(secret.decode('ascii'))
    return config


def mapping(source):
    return {k:v for k,v in source.items() if k!='keys'}


def signed_bytes(source,key_id,timestamp,nonce,body):
    return f'v1\nPOST\n{PATH}\n{source}\n{key_id}\n{timestamp}\n{nonce}\n'.encode('ascii')+body


def install(store):
    repo=EvidenceRepository(store)
    if repo.integrations.mode=='sandbox': raise ValueError('Private HTTPS demo/production required.')
    with store.transaction() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'webhook_*'").fetchone(): raise ValueError('Already installed; no repair.')
        for sql in {**TABLES,**GUARDS,**INDEXES}.values(): db.execute(sql)
        db.execute('INSERT INTO webhook_metadata VALUES (?,?)',('webhook-intake-v1',repo.integrations.mode))
    return {'status':'initialized','operational_state':'inactive'}


class WebhookIntake:
    def __init__(self,store,config_file):
        self.store=store;self.config_file=str(config_file)
        self.repo=EvidenceRepository(store)
        config=load_config(config_file)
        if config['mode']!=self.repo.integrations.mode: raise ValueError('Webhook runtime mode mismatch.')
        with closing(store.connect()) as db:
            self._storage(db)
            for source in config['sources']: self._check_mapping(db,source,config['mode'])

    def _storage(self,db):
        schema={r['name']:r['sql'] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'webhook_*'")}
        if any(schema.get(k)!=v for k,v in {**TABLES,**GUARDS,**INDEXES}.items()): raise ValueError('Webhook storage unavailable; no repair.')
        rows=db.execute('SELECT * FROM webhook_metadata').fetchall()
        if len(rows)!=1 or rows[0]['mode']!=self.repo.integrations.mode or rows[0]['marker']!='webhook-intake-v1': raise ValueError('Webhook mode mismatch.')

    def _check_mapping(self,db,source,mode):
        chain=self.repo.integrations._chain(db,source['tenant'])
        if not chain or chain[-1]['version']!=source['config_version'] or chain[-1]['content_hash']!=source['config_hash']:
            raise ValueError('Mapping requires the current explicit M06 version/hash.')
        config=chain[-1]['config']
        if config['data_classification']!=('synthetic' if mode=='demo' else 'declared'):
            raise ValueError('Contract classification incompatible with isolated runtime.')
        for route in source['routes'].values():
            definition=next((d for d in config[{'event':'events','metric':'metrics','evidence':'evidence'}[route['kind']]] if d['id']==route['definition_id']),None)
            if not definition or definition['source_ref']!=route['source_ref'] or (route['kind']=='evidence' and definition['availability']!='declared'):
                raise ValueError('Mapping target/source is not declared.')
            expected={'value':{'required':True}} if route['kind']=='metric' else fields(definition['fields'],'fields')
            if set(route['fields'])-set(expected) or any(d['required'] and k not in route['fields'] for k,d in expected.items()):
                raise ValueError('Mapping fields do not match M06.')
        return chain[-1]

    def receive(self,headers,raw):
        """Only called by the verified private TLS route, with the original body bytes."""
        try:
            config=load_config(self.config_file)
            self.repo._runtime()
            if config['mode']!=self.repo.integrations.mode: raise ValueError('Mode changed.')
        except (OSError,ValueError,Problem,sqlite3.Error,RecursionError): raise Problem(503,'Entrada indisponível; configuração privada necessária.')
        values=[]
        for name in ('X-CW-Source','X-CW-Key-Id','X-CW-Timestamp','X-CW-Nonce','X-CW-Signature'):
            all_values=headers.get_all(name,[])
            if len(all_values)!=1: raise Problem(401,'Autenticação da origem inválida.')
            values.append(all_values[0])
        sid,kid,stamp,nonce,signature=values
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',sid) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',kid)
                or not re.fullmatch(r'[0-9]{1,12}',stamp) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',nonce)
                or not re.fullmatch(r'v1=[0-9a-f]{64}',signature)):
            raise Problem(401,'Autenticação da origem inválida.')
        current=int(time.time());timestamp=int(stamp)
        source=next((s for s in config['sources'] if s['id']==sid),None)
        key=next((k for k in source['keys'] if k['id']==kid),None) if source else None
        if (not key or abs(current-timestamp)>WINDOW or not key['not_before']<=current<key['expires_at']
                or not key['not_before']<=timestamp<key['expires_at']):
            raise Problem(401,'Autenticação da origem inválida.')
        signed=signed_bytes(sid,kid,stamp,nonce,raw)
        if not hmac.compare_digest(signature,'v1='+hmac.new(key['_secret'],signed,hashlib.sha256).hexdigest()):
            raise Problem(401,'Autenticação da origem inválida.')
        request_hash=hashlib.sha256(signed).hexdigest();decl=mapping(source);map_hash=digest(decl)
        with self.store.transaction() as db:
            try:
                self._storage(db);self.repo._storage(db);self.repo.integrations._storage(db)
            except (ValueError,sqlite3.Error): raise Problem(503,'Integridade da entrada indisponível.')
            fingerprint=hashlib.sha256(key['_secret']).hexdigest()
            oldkey=db.execute('SELECT fingerprint FROM webhook_keys WHERE source=? AND key_id=?',(sid,kid)).fetchone()
            if oldkey and oldkey[0]!=fingerprint: raise Problem(409,'Rotação exige novo identificador de chave.')
            previous=db.execute('SELECT * FROM webhook_receipts WHERE source=? AND nonce=?',(sid,nonce)).fetchone()
            if previous:
                row=dict(previous);claimed=row.pop('record_hash')
                if digest(row)!=claimed: raise Problem(503,'Integridade do recibo indisponível.')
                if row['request_hash']!=request_hash: raise Problem(409,'Identidade de entrega já utilizada.')
                return row['status'],strict_json(row['result'].encode())
            if db.execute('SELECT count(*) FROM webhook_receipts WHERE source=? AND received_at>?',(sid,current-60)).fetchone()[0]>=MAX_PER_MINUTE:
                raise Problem(429,'Limite de entrada atingido.')
            if db.execute('SELECT count(*) FROM webhook_receipts WHERE source=?',(sid,)).fetchone()[0]>=MAX_RECEIPTS:
                raise Problem(503,'Capacidade de entrada esgotada; revisão local necessária.')
            old=db.execute('SELECT * FROM webhook_mappings WHERE source=? ORDER BY version DESC LIMIT 1',(sid,)).fetchone()
            if old and (canonical(strict_json(old['payload'].encode()))!=old['payload'] or digest(strict_json(old['payload'].encode()))!=old['mapping_hash']):
                raise Problem(503,'Integridade do mapeamento indisponível.')
            if old and (old['tenant']!=source['tenant'] or old['version']>source['mapping_version'] or (old['version']==source['mapping_version'] and old['mapping_hash']!=map_hash)):
                raise Problem(409,'Versão de mapeamento incompatível; configuração local necessária.')
            for prior in db.execute('SELECT source,payload FROM webhook_mappings WHERE tenant=? AND source<>?',(source['tenant'],sid)):
                old_routes=strict_json(prior['payload'].encode())['routes']
                if {r['source_ref'] for r in old_routes.values()} & {r['source_ref'] for r in source['routes'].values()}:
                    raise Problem(409,'Origem contratual já vinculada a outra identidade de integração.')
            if not old or old['version']<source['mapping_version']:

                db.execute('INSERT INTO webhook_mappings VALUES (?,?,?,?,?)',(sid,source['mapping_version'],source['tenant'],map_hash,canonical(decl)))
            if not oldkey:
                if db.execute('SELECT 1 FROM webhook_keys WHERE fingerprint=?',(fingerprint,)).fetchone():
                    raise Problem(409,'Rotação exige material secreto novo e independente.')
                db.execute('INSERT INTO webhook_keys VALUES (?,?,?)',(sid,kid,fingerprint))
            db.execute('SAVEPOINT intake')
            ids=[]
            try:
                body=strict_json(raw)
                shape(body,'mapping_version config_version customer_id event_type event_id occurred_at period data','webhook')
                if type(body['mapping_version']) is not int or type(body['config_version']) is not int or body['mapping_version']!=source['mapping_version'] or body['config_version']!=source['config_version']:
                    raise Problem(409,'Versões incompatíveis.')
                customer=source['customers'].get(body['customer_id']) if isinstance(body['customer_id'],str) else None
                route=source['routes'].get(body['event_type']) if isinstance(body['event_type'],str) else None
                if not customer: raise Problem(403,'Cliente fora do âmbito autorizado.')
                if not route: raise Problem(400,'Evento não declarado.')
                data=body['data'];used={s[5:] for s in route['fields'].values() if s.startswith('data.')}
                if not isinstance(data,dict) or set(data)!=used: raise Problem(400,'Campos externos incompatíveis.')
                payload={target:customer if selector=='$customer' else body['occurred_at'] if selector=='$occurred_at' else data[selector[5:]] for target,selector in route['fields'].items()}
                try: chain=self.repo.integrations._chain(db,source['tenant'])
                except (ValueError,sqlite3.Error): raise Problem(503,'Integridade da configuração indisponível.')
                if not chain or chain[-1]['version']!=source['config_version'] or chain[-1]['content_hash']!=source['config_hash']:
                    raise Problem(409,'Configuração SaaS incompatível; revisão do mapeamento necessária.')
                snapshot=chain[-1]
                if source['classification']=='declared' and snapshot['config']['data_classification']!='declared': raise Problem(403,'Origem declarada exige contrato declarado.')
                if config['mode']=='demo' and snapshot['config']['data_classification']!='synthetic': raise Problem(403,'Demo aceita apenas dados de teste.')
                record={'external_id':body['event_id'],'kind':route['kind'],'definition_id':route['definition_id'],'source_ref':route['source_ref'],
                        'occurred_at':body['occurred_at'],'period':body['period'],'payload':payload}
                result=self.repo._ingest(db,'webhook:'+sid,{'tenant':source['tenant'],'customer':customer,'config_version':source['config_version'],'records':[record]},snapshot)
                ids=result['record_ids']
                response={'status':'accepted','receipt_id':None,'inserted':result['inserted'],'duplicates':result['duplicates'],
                          'claim_classification':'source_claim','source_classification':source['classification'],'operational_state':'inactive'}
                status=200
            except (Problem,ValueError,TypeError,KeyError,RecursionError) as error:
                db.execute('ROLLBACK TO intake')
                status=error.status if isinstance(error,Problem) else 400
                response={'error':'Entrega rejeitada; contrato ou âmbito incompatível.'}
            db.execute('RELEASE intake')
            row={'id':db.execute('SELECT coalesce(max(id),0)+1 FROM webhook_receipts').fetchone()[0],
                 'source':sid,'nonce':nonce,'request_hash':request_hash,'received_at':current,'mapping_version':source['mapping_version'],
                 'mapping_hash':map_hash,'config_hash':source['config_hash'],'key_id':kid,'body_hash':hashlib.sha256(raw).hexdigest(),
                 'status':status,'result':None,'evidence_ids':canonical(ids)}
            if status==200: response['receipt_id']=row['id']
            row['result']=canonical(response);row['record_hash']=digest(row)
            db.execute('INSERT INTO webhook_receipts ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
            return status,response


def main():
    parser=argparse.ArgumentParser(description='Optional private webhook intake; no publication or business activation.')
    parser.add_argument('command',choices=['init','check']);parser.add_argument('--db',required=True);parser.add_argument('--config')
    args=parser.parse_args()
    try:
        store=Store.open_existing(args.db)
        if args.command=='init': result=install(store)
        else:
            if not args.config: raise ValueError('Private configuration required.')
            WebhookIntake(store,args.config);result={'status':'ready','operational_state':'inactive'}
        print(canonical(result))
    except (ValueError,OSError,Problem,sqlite3.Error,RecursionError): parser.exit(1,'Webhook preparation refused; verify private files, mode and storage.\n')


if __name__=='__main__': main()
