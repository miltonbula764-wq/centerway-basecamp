"""Local operational checks and consistent snapshots. No hosting or migrations."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .preview import PreviewPolicy, REPOSITORY, canonical_origin
from .store import Store


def readonly(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Ficheiro necessário.')
    return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)


def integrity(db):
    if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
        raise ValueError('Integridade SQLite não confirmada.')
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Referências SQLite inválidas.')


def check(path, origin):
    origin=canonical_origin(origin)
    path=Path(path).resolve(strict=True)
    if path.stat().st_mode & 0o077:
        raise ValueError('A base exige permissões 0600.')
    if not os.access(path,os.R_OK|os.W_OK) or not os.access(path.parent,os.W_OK):
        raise ValueError('Base e diretório de journal têm de ser graváveis pelo serviço.')
    store=Store.open_existing(path)
    with closing(readonly(path)) as db:
        integrity(db)
    policy=PreviewPolicy(store)
    if policy.origin!=origin:
        raise ValueError('Origem pública diferente da guardada na base privada.')
    return {'status':'ready','schema_version':2,'scope':'synthetic-sandbox',
            'expires':policy.expires.isoformat(),'database_bytes':path.stat().st_size}


def backup(path, destination):
    # A raw cp of an active SQLite database is not a consistent backup.
    Store.open_existing(path)
    source=Path(path).resolve(strict=True)
    destination=Path(destination).resolve()
    if destination==source or REPOSITORY in destination.parents:
        raise ValueError('Snapshot exige outro caminho, fora do checkout.')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if destination.parent.stat().st_mode & 0o077:
        raise ValueError('Diretório de snapshots deve ser privado (0700).')
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    os.close(fd)
    try:
        with closing(readonly(source)) as src,closing(sqlite3.connect(destination)) as dst:
            integrity(src)
            src.backup(dst)
            integrity(dst)
        return verify_backup(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def verify_backup(path):
    if Path(path).stat().st_mode & 0o077:
        raise ValueError('Snapshot exige permissões privadas.')
    Store.open_existing(path,read_only=True)
    with closing(readonly(path)) as db:
        integrity(db)
        if db.execute('PRAGMA user_version').fetchone()[0]!=2:
            raise ValueError('Snapshot não é schema V2.')
    digest=hashlib.sha256()
    with open(path,'rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return {'status':'verified','schema_version':2,'sha256':digest.hexdigest()}


def main():
    parser=argparse.ArgumentParser(description='Operações locais V2: não publica, não cria base, não migra, não restaura.')
    sub=parser.add_subparsers(dest='command',required=True)
    ready=sub.add_parser('check');ready.add_argument('--db',required=True);ready.add_argument('--origin',required=True)
    snapshot=sub.add_parser('backup');snapshot.add_argument('--db',required=True);snapshot.add_argument('--out',required=True)
    verify=sub.add_parser('verify-backup');verify.add_argument('--db',required=True)
    args=parser.parse_args()
    try:
        result=check(args.db,args.origin) if args.command=='check' else backup(args.db,args.out) if args.command=='backup' else verify_backup(args.db)
    except (ValueError,OSError,sqlite3.Error):
        # Paths and exception text may contain sensitive values; keep output bounded.
        parser.exit(1,'{"status":"error","code":"operation_refused"}\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
