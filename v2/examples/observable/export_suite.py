"""Export actual engine outputs from an existing local synthetic suite. Never advances/approves."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from centerway.journey import Journey,SCENARIOS,markdown,private_json


def export(root,out):
    root=Path(root).resolve(strict=True);out=Path(out)
    if out.exists(): raise ValueError('New output directory required; prior exports are preserved.')
    out.mkdir(parents=True,mode=0o700);matrix={};files={}
    for name in SCENARIOS:
        lab=Journey(root/name);report=lab.report();directory=out/name;directory.mkdir(mode=0o700)
        private_json(directory/'engine-output.json',report)
        content=markdown(report);(directory/'chronology.md').write_text(content);(directory/'chronology.md').chmod(0o600)
        inputs=directory/'inputs';inputs.mkdir(mode=0o700)
        for source in sorted((lab.root/'inputs').glob('*.json')):
            # Only declared synthetic inputs, never workspace credentials/session/database files.
            target=inputs/source.name;target.write_bytes(source.read_bytes());target.chmod(0o600)
        matrix[name]=report['summary']
        for path in sorted(p for p in directory.rglob('*') if p.is_file()): files[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
    private_json(out/'summary.json',matrix)
    lines=['# Resultados efetivamente produzidos pelos motores','', '**Ensaio sintético; fixture C04 não é inferência real. Nenhuma recuperação real é demonstrada.**','',
           '| Cenário | Estado do caso | Efeitos persistidos | Execução C06 | Operação C06 | Valor C06 |','| --- | --- | ---: | --- | --- | --- |']
    for name,item in matrix.items():
        last=item['c06'][-1] if item['c06'] else None
        states=[last[k]['state'] if last else 'não avaliado' for k in ('execution','operational_recovery','value_recovery')]
        lines.append('| '+name+' | '+item['case_state']+' | '+str(item['effects'])+' | '+' | '.join(states)+' |')
    lines+=['','Cada pasta contém a cronologia completa e os outputs JSON, incluindo hashes, fontes, períodos, participações e bloqueios. Estado C06 demonstrado refere-se exclusivamente aos critérios do ensaio sintético. Fecho não é automático.','']
    (out/'RESULTS.md').write_text('\n'.join(lines));files['RESULTS.md']=hashlib.sha256((out/'RESULTS.md').read_bytes()).hexdigest();files['summary.json']=hashlib.sha256((out/'summary.json').read_bytes()).hexdigest()
    private_json(out/'manifest.json',{'classification':'synthetic_test_only','files':files,'credentials_included':False,'raw_session_tokens_included':False})
    return matrix


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',required=True);parser.add_argument('--out-dir',required=True);args=parser.parse_args()
    try: print(json.dumps(export(args.workspace,args.out_dir),ensure_ascii=False,indent=2))
    except (ValueError,OSError): parser.exit(1,'Export refused; verify explicit private synthetic scopes and a new output path.\n')
