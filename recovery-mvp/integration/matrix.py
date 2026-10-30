"""Derived case index; never author example responses here."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(document):
    lines=['# L03-PREP v1 — matriz dos casos capturados','',
      'Cada linha referencia um caso real sanitizado em capture.json. PASS significa que',
      'a suite passou validação OpenAPI/contrato, comparação com nova execução e os gates',
      'de permissões/semântica; HTTP de erro esperado também é um caso PASS. Esta tabela',
      'é derivada das fixtures e não substitui o resultado do CI no commit entregue.','',
      '| Caso | Método | HTTP | Recibo F06 | Resultado de negócio | Gate esperado |',
      '|---|---|---|---|---|---|']
    for c in document['cases']:
        response=c['response']; receipt=business='—'
        if response:
            body=response['json']
            if isinstance(body,dict) and isinstance(body.get('data'),dict) and 'operation' in body['data']:
                r=body['data']; receipt=r['status']
                result=r['result']
                if r['status']=='completed':
                    business=result.get('status') or result.get('result',{}).get('status') or result.get('result',{}).get('state') or '—'
            status=str(response['status'])
        else: status='sem HTTP ('+c['transport_error']+')'
        lines.append(f'| `{c["id"]}` | {c["request"]["method"]} | {status} | {receipt} | {business} | PASS |')
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    document=json.loads((HERE/'fixtures'/'v1'/'capture.json').read_text())
    (HERE/'fixtures'/'v1'/'CASE_MATRIX.md').write_text(render(document))
