"""Single Android entry point. Prepare/probe first; restore only with explicit mode."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess as sp
import sys
import tarfile
from android_stream import frame,read_frame,send
from handoff import bundle,recipient_fingerprint

ROOT=Path(__file__).resolve().parents[2]
REPO='miltonbula764-wq/centerway-basecamp'

class AccessError(Exception):
    """Fixed diagnostics only; never forward gh stderr, headers or connection data."""
    def __init__(self,code):
        super().__init__(code)
        self.code=code

def require(ok):
    if not ok: raise ValueError('operation_rejected')

def run(args,data=None,timeout=240):
    r=sp.run(args,input=data,stdout=sp.PIPE,stderr=sp.PIPE,timeout=timeout)
    if r.returncode:
        if args[:2]==['gh','api'] or args[:3]==['gh','codespace','list'] or args[:3]==['gh','codespace','ssh']:
            status=re.search(rb'\bHTTP\s+([45][0-9]{2})\b',r.stderr)
            suffix=status.group(1).decode() if status else 'failed'
            if not status and r.stderr.rstrip().endswith(b': Forbidden'):suffix='403'
            kind='ssh' if args[:3]==['gh','codespace','ssh'] else 'read'
            raise AccessError('codespace_'+kind+'_'+suffix)
        require(False)
    return r.stdout

def resolve_codespace(spaces,selector=None):
    require(isinstance(spaces,list))
    if selector:
        # Canonical name wins, even when another display label overlaps it.
        matches=[s for s in spaces if s.get('name')==selector]
        if not matches:
            label=selector.replace(' ','-')
            matches=[s for s in spaces if str(s.get('displayName','')).replace(' ','-')==label
                     or str(s.get('name','')).startswith(label+'-')]
    else:
        matches=[s for s in spaces if s.get('state')=='Available']
    if len(matches)!=1:raise AccessError('codespace_selection_ambiguous_or_missing')
    selected=matches[0]
    if not re.fullmatch(r'[a-z0-9-]+',selected.get('name','')):raise AccessError('codespace_name_invalid')
    if selected.get('state')!='Available':raise AccessError('codespace_not_available')
    return selected

def inspect_codespace(selector=None):
    if os.environ.get('GH_HOST','github.com')!='github.com':
        raise AccessError('codespace_host_override_conflict')
    try:
        spaces=json.loads(run(['gh','codespace','list','--repo',REPO,'--json','name,displayName,state','--limit','100']))
    except AccessError as error:
        error.phase='list';raise
    # Do not resolve a partial page as unique.
    if len(spaces)>=100:raise AccessError('codespace_listing_limit')
    selected=resolve_codespace(spaces,selector)
    canonical=selected['name']
    try:
        detail=json.loads(run(['gh','api','--hostname','github.com','--method','GET','user/codespaces/'+canonical]))
    except AccessError as error:
        error.phase='canonical_get';error.canonical=canonical;raise
    if detail.get('name')!=canonical or detail.get('repository',{}).get('full_name')!=REPO:
        raise AccessError('codespace_detail_identity_mismatch')
    if detail.get('state')!='Available':raise AccessError('codespace_not_available')
    return {'name':canonical,'state':'Available','canonical_get_verified':True,
            'selector_resolved':selector is not None and selector!=canonical}

def diagnose(selector=None):
    version=run(['gh','--version']).splitlines()[0]
    match=re.search(rb'gh version ([0-9]+\.[0-9]+\.[0-9]+)',version)
    result={'gh_version':match.group(1).decode() if match else 'unknown',
            'mode':'read_only','ssh_verified':False,'real_backup':False,
            'credential_override_present':bool(os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))}
    try:
        result.update(inspect_codespace(selector));result['status']='canonical_get_verified'
    except AccessError as error:
        result['status']=error.code
        result['phase']=getattr(error,'phase','selection')
        if hasattr(error,'canonical'):result['name']=error.canonical
    return result

def remote(codespace,command,data=None,timeout=240):
    require(re.fullmatch(r'[a-z0-9-]+',codespace) is not None)
    return run(['gh','codespace','ssh','-c',codespace,'--','-T',command],data,timeout)

def checked_package(sha):
    require(re.fullmatch(r'[a-f0-9]{40}',sha) is not None)
    require(run(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()==sha)
    run(['git','-C',str(ROOT),'diff','--exit-code',sha,'--','recovery-mvp/gate1','recovery-mvp/api/requirements.txt'])
    raw=run(['git','-C',str(ROOT),'archive',sha,'recovery-mvp/gate1','recovery-mvp/api/requirements.txt'])
    require(len(raw)<=4*1024*1024)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for m in tar.getmembers():
            p=Path(m.name)
            require(not p.is_absolute() and '..' not in p.parts and (m.isfile() or m.isdir()))
    return raw

def probe_receive(stream,expected):
    manifest,dump=read_frame(stream,expected)
    require(manifest=={'probe':'synthetic-only'} and dump==b'PGDMP'+bytes(range(256))*64)
    return {'status':'synthetic_ssh_verified','nonce':expected,'database_access':False}

def prepare(sha,codespace=None,identity=None):
    package=checked_package(sha)
    # Read-only canonical GET before any SSH/staging; never pass a short label to gh.
    codespace=inspect_codespace(codespace)['name']
    suffix=sha+'-'+secrets.token_hex(8)
    stage='.local/state/centerway-gate1/'+suffix
    # stage has only locally generated hex and fixed ASCII path components.
    prefix='"$HOME/'+stage+'"'
    script='umask 077; mkdir -p "$HOME/.local/state/centerway-gate1" && mkdir '+prefix+' && cd '+prefix+' && tar -xf -'
    staged=False
    try:
        remote(codespace,script,package)
        staged=True
        ready=json.loads(remote(codespace,'cd '+prefix+' && bash recovery-mvp/gate1/prepare_codespace.sh',timeout=600))
        require(ready['status']=='codespace_dependencies_ready')
        nonce=secrets.token_hex(32)
        packet=frame(b'{"probe":"synthetic-only"}',b'PGDMP'+bytes(range(256))*64,nonce)
        response=json.loads(remote(codespace,'cd '+prefix+' && venv/bin/python recovery-mvp/gate1/android_ops.py probe-receive --expected '+nonce,packet))
        require(response=={'status':'synthetic_ssh_verified','nonce':nonce,'database_access':False})
        # Fingerprint the actual remote sender/receiver bytes against reviewed archive.
        files=['android_ops.py','android_stream.py','handoff.py','recovery.py','prepare_codespace.sh']
        for name in files:
            path='recovery-mvp/gate1/'+name
            expected=hashlib.sha256(run(['git','-C',str(ROOT),'show',sha+':'+path])).hexdigest()
            got=remote(codespace,'cd '+prefix+' && sha256sum '+shlex.quote(path)).decode().split()[0]
            require(got==expected)
        public_fp=None
        if identity:
            # Private key is read only by age-keygen ON ANDROID; only public key sent.
            recipient=run(['age-keygen','-y',identity]).strip()
            require(re.fullmatch(b'age1[0-9a-z]{58}',recipient) is not None)
            public_fp=hashlib.sha256(recipient).hexdigest()
            remote(codespace,'umask 077; cat > '+prefix+'/recipient.txt',recipient+b'\n')
        receipt={'format':'cw-android-ops-v1','status':'preparation_verified','sha':sha,
                 'codespace':codespace,'stage':stage,'public_recipient_sha256':public_fp,
                 'ssh_synthetic_verified':True,'real_backup':False}
        directory=Path.home()/'.local/state/centerway-gate1';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        require(not directory.is_symlink() and not directory.stat().st_mode & 0o077)
        target=directory/('receipt-'+suffix+'.json')
        with open(target,'x') as f: os.chmod(target,0o600);json.dump(receipt,f,sort_keys=True)
        return {'status':'preparation_verified','receipt':str(target),'real_backup':False,'ssh_synthetic_verified':True,'public_recipient_sha256':public_fp}
    except Exception as error:
        # A 404 fetching connection details in the first tar command ran no remote
        # shell. Do not mask it as an unconfirmed cleanup (or retry on another host).
        if not staged and isinstance(error,AccessError) and error.code=='codespace_ssh_404':
            raise
        # No Neon resources exist in this entry point. Remove only this new package.
        try:remote(codespace,'rm -rf -- '+prefix+' && test ! -e '+prefix)
        except Exception:raise RuntimeError('remote_cleanup_unconfirmed') from None
        raise

def restore(receipt_path,archive,identity,expected):
    p=Path(receipt_path)
    require(not p.is_symlink() and p.is_file() and not p.stat().st_mode & 0o077)
    r=json.loads(p.read_text())
    require(r['format']=='cw-android-ops-v1' and r['status']=='preparation_verified' and r['ssh_synthetic_verified'])
    require(re.fullmatch(r'\.local/state/centerway-gate1/[0-9a-f]{40}-[0-9a-f]{16}',r['stage']) is not None)
    require(re.fullmatch(r'[0-9a-f]{64}',expected) is not None)
    # expected comes from the ORIGINAL export via trusted channel, not self-declared download.
    checked_package(r['sha'])
    for name in ['android_ops.py','android_stream.py','handoff.py','recovery.py']:
        path='recovery-mvp/gate1/'+name
        wanted=hashlib.sha256(run(['git','-C',str(ROOT),'show',r['sha']+':'+path])).hexdigest()
        got=remote(r['codespace'],'cd \"$HOME/'+r['stage']+'\" && sha256sum '+path).decode().split()[0]
        require(got==wanted)
    checks=bundle(archive)
    actual=hashlib.sha256(json.dumps(checks,sort_keys=True).encode()).hexdigest();require(actual==expected)
    require(hashlib.sha256(run(['age-keygen','-y',identity]).strip()).hexdigest()==r['public_recipient_sha256'])
    packet=io.BytesIO();send(archive,identity,packet)
    result=json.loads(remote(r['codespace'],'cd "$HOME/'+r['stage']+'" && ulimit -c 0 && venv/bin/python recovery-mvp/gate1/android_stream.py receive --expected '+expected,packet.getvalue(),timeout=900))
    require(result['status']=='isolated_restore_verified' and result['runtime_ready'] is False)
    remote(r['codespace'],'rm -rf -- \"$HOME/'+r['stage']+'\" && test ! -e \"$HOME/'+r['stage']+'\"')
    result['remote_package_removed']=True
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','restore','probe-receive','diagnose'])
    p.add_argument('--reviewed-sha');p.add_argument('--codespace');p.add_argument('--identity')
    p.add_argument('--receipt');p.add_argument('--archive');p.add_argument('--expected')
    a=p.parse_args()
    if a.mode=='diagnose':result=diagnose(a.codespace)
    elif a.mode=='prepare': result=prepare(a.reviewed_sha,a.codespace,a.identity)
    elif a.mode=='restore':result=restore(a.receipt,a.archive,a.identity,a.expected)
    else:
        import signal
        signal.alarm(180)
        result=probe_receive(sys.stdin.buffer,a.expected)
    print(json.dumps(result,sort_keys=True))
    if a.mode=='diagnose' and result['status']!='canonical_get_verified':sys.exit(1)

if __name__=='__main__':
    try:main()
    except Exception as error:
        code=error.code if isinstance(error,AccessError) else ('remote_cleanup_unconfirmed' if isinstance(error,RuntimeError) and error.args==('remote_cleanup_unconfirmed',) else 'operation_rejected')
        print('android_operation_failed; '+code+'; no real export was started by this tool',file=sys.stderr);sys.exit(1)
