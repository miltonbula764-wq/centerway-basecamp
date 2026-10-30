"""Offline review only: never authorizes, edits config, resolves DNS or publishes."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


def validate_origins(origins, *, activation=True):
    if not isinstance(origins,list) or not origins or any(not isinstance(o,str) for o in origins) or len(origins)!=len(set(origins)):
        raise ValueError('Explicit nonempty unique origin list required')
    for origin in origins:
        u=urlsplit(origin)
        host=u.hostname or ''
        labels=host.split('.')
        port=u.port
        canonical='https://'+host+((':'+str(port)) if port and port!=443 else '')
        if u.scheme!='https' or u.username is not None or u.password is not None or origin!=canonical or len(labels)<2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in labels):
            raise ValueError('Exact canonical HTTPS origin required')
        if activation and (host.endswith(('.invalid','.test','.local','.example')) or host in {'example.com','example.org','example.net'} or host.endswith(('.example.com','.example.org','.example.net')) or all(x.isdigit() for x in labels)):
            raise ValueError('Real reviewed interface origins required')
    return origins


def check(config,review):
    if set(review)!={'version','origins'} or review['version']!='c04-origins-v1':
        raise ValueError('Unknown origin review contract')
    expected=validate_origins(review['origins'])
    if config.get('demo') is not False or set(validate_origins(config.get('origins')))!=set(expected):
        raise ValueError('Configuration differs from reviewed origins')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True); p.add_argument('--origins',default=str(Path(__file__).with_name('origins.json')))
    args=p.parse_args()
    try:
        config=Path(args.config)
        if config.is_symlink() or config.stat().st_mode&0o077: raise ValueError('Private config required')
        check(json.loads(config.read_text()),json.loads(Path(args.origins).read_text()))
    except Exception:
        print('NO-GO: missing or mismatched exact reviewed origins/private configuration.')
        raise SystemExit(1)
    print('Offline origin comparison passed; publication and live connectivity remain unverified.')
