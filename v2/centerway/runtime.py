"""Explicit demo/production entrypoints. No hosting and no existing-data conversion."""
import argparse
from pathlib import Path
import sqlite3
import ssl
from . import preview, production
from .store import Store, encode


def policy_for(mode,store):
    if mode=='demo': return preview.PreviewPolicy(store)
    if mode=='production': return production.ProductionPolicy(store)
    raise ValueError('Modo explícito demo ou production necessário.')


def main():
    parser=argparse.ArgumentParser(description='Runtime privado com modos isolados; não publica nem migra.')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init')
    for name in ('db','credentials-file','origin'): init.add_argument('--'+name,required=True)
    init.add_argument('--mode',choices=('demo','production'),required=True)
    init.add_argument('--hours',type=int)
    init.add_argument('--accounts-file')
    serve=sub.add_parser('serve')
    serve.add_argument('--mode',choices=('demo','production'),required=True)
    for name in ('db','certfile','keyfile'): serve.add_argument('--'+name,required=True)
    serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--port',type=int,default=8443)
    serve.add_argument('--pilot-ai-config',help='Private configured AI; per-SaaS pilot consent also required. No fallback.')
    serve.add_argument('--webhook-config',help='Private owner-only webhook configuration outside the checkout; opt-in.')
    serve.add_argument('--frontend-origin',action='append',default=[])
    apply=sub.add_parser('apply-accounts')
    for name in ('db','accounts-file','credentials-file'): apply.add_argument('--'+name,required=True)
    rotate=sub.add_parser('rotate-password')
    for name in ('db','user','credentials-file'): rotate.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        if args.command=='init':
            if args.mode=='demo':
                if args.accounts_file: raise ValueError('Demo não aceita configuração de production.')
                result=preview.provision(args.db,args.credentials_file,args.origin,args.hours if args.hours is not None else 24)
            else:
                if args.hours is not None or not args.accounts_file: raise ValueError('Production exige contas e não aceita horas de demo.')
                result=production.provision(args.db,args.credentials_file,args.origin,args.accounts_file)
            print(encode(result));return
        if args.command=='apply-accounts':
            print(encode(production.apply_accounts(args.db,args.accounts_file,args.credentials_file)));return
        if args.command=='rotate-password':
            print(encode(production.rotate_password(args.db,args.user,args.credentials_file)));return
        if not Path(args.db).is_file(): raise ValueError('Base inexistente.')
        store=Store.open_existing(args.db);policy=policy_for(args.mode,store)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.certfile,args.keyfile)
        from .server import make_server
        server=make_server(store,args.host,args.port,preview=policy,tls_context=context,frontend_origins=args.frontend_origin,webhook_config=args.webhook_config,pilot_ai_config=args.pilot_ai_config)
    except (ValueError,OSError,sqlite3.Error):
        parser.exit(1,'{"status":"error","code":"configuration_refused"}\n')
    preview.run_private_server(server)


if __name__=='__main__':
    main()
