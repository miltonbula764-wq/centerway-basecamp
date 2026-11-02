"""Private SSH transport: decrypt on Android, restore in RAM on Linux. No keys sent."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
from handoff import bundle

LIMIT=64*1024*1024

def require(value):
    if not value: raise ValueError('private_stream_rejected')

def frame(manifest,dump,fingerprint):
    require(len(manifest)<=LIMIT and len(dump)<=LIMIT and dump.startswith(b'PGDMP'))
    header=json.dumps({'format':'cw-private-ssh-v1','cipher_bundle':fingerprint,
        'manifest_bytes':len(manifest),'dump_bytes':len(dump),
        'manifest_sha256':hashlib.sha256(manifest).hexdigest(),
        'dump_sha256':hashlib.sha256(dump).hexdigest()},sort_keys=True).encode()
    return struct.pack('!I',len(header))+header+manifest+dump

def read_frame(stream,expected):
    def read(n):
        data=bytearray()
        while len(data)<n:
            part=stream.read(n-len(data));require(part);data.extend(part)
        return bytes(data)
    length=struct.unpack('!I',read(4))[0];require(0<length<=4096)
    h=json.loads(read(length))
    require(h['format']=='cw-private-ssh-v1' and h['cipher_bundle']==expected)
    require(0<h['manifest_bytes']<=LIMIT and 0<h['dump_bytes']<=LIMIT)
    manifest=read(h['manifest_bytes']);dump=read(h['dump_bytes'])
    require(stream.read(1)==b'')
    require(hashlib.sha256(manifest).hexdigest()==h['manifest_sha256'])
    require(hashlib.sha256(dump).hexdigest()==h['dump_sha256'] and dump.startswith(b'PGDMP'))
    return json.loads(manifest),dump

def send(folder,key,out):
    require(not out.isatty())
    checks=bundle(folder)
    fingerprint=hashlib.sha256(json.dumps(checks,sort_keys=True).encode()).hexdigest()
    clear=[]
    for name in ('manifest.age','database.age'):
        # age does not compress; checked ciphertext <=64MiB bounds clear output.
        r=subprocess.run(['age','-d','-i',str(key),str(Path(folder)/name)],
             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
             timeout=180,check=False)
        require(r.returncode==0 and len(r.stdout)<=LIMIT);clear.append(r.stdout)
    # No bytes emitted until BOTH age authenticators have succeeded.
    require(bundle(folder)==checks)
    out.write(frame(*clear,fingerprint));out.flush()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['send','receive']);p.add_argument('--archive');p.add_argument('--identity');p.add_argument('--expected')
    a=p.parse_args()
    if a.mode=='send':send(a.archive,a.identity,sys.stdout.buffer)
    else:
        require(a.expected and len(a.expected)==64)
        signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError()))
        signal.alarm(180)
        manifest,dump=read_frame(sys.stdin.buffer,a.expected)
        signal.alarm(0)
        from recovery import restore_payload
        print(json.dumps(restore_payload(manifest,dump),sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception:
        print('private_stream_failed',file=sys.stderr);sys.exit(1)
