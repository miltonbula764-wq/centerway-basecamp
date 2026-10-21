import base64
import hmac
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import connect, event, transaction


def report(path, after=0):
    db = connect(path)
    try:

        def rows(query, args=()):
            return [dict(r) for r in db.execute(query, args)]

        imported = rows("SELECT * FROM comparisons ORDER BY id DESC LIMIT 100")
        for item in imported:
            item["simulator_measurements"] = rows(
                "SELECT observed_at,value,provenance FROM measurements WHERE client=? AND indicator=? AND observed_at<=? ORDER BY observed_at DESC LIMIT 10",
                (item["client"], item["indicator"], item["observed_until"]),
            )
            item["private_events"] = rows(
                "SELECT * FROM events WHERE client=? AND kind='operation' AND json_extract(truth,'$.observed_at_epoch')<=? ORDER BY id DESC LIMIT 10",
                (item["client"], item["observed_until"]),
            )
        events = rows("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (after,))
        for e in events:
            e["truth"] = json.loads(e["truth"])
        for item in imported:
            for e in item["private_events"]:
                e["truth"] = json.loads(e["truth"])
        return {
            "paused": bool(
                db.execute("SELECT paused FROM controls WHERE id=1").fetchone()[0]
            ),
            "clients": rows("SELECT * FROM clients ORDER BY ref"),
            "counts": dict(
                db.execute(
                    "SELECT 'produced',count(*) FROM measurements UNION ALL SELECT 'sent_measurements',count(*) FROM measurements m JOIN outbox b ON b.id=m.batch_id WHERE b.state='sent' UNION ALL SELECT 'awaiting_receipts',count(*) FROM measurements m JOIN measurements p ON p.id=m.corrects WHERE m.batch_id IS NULL AND p.observation_id IS NULL UNION ALL SELECT 'history_ticks',count(*) FROM ticks WHERE provenance='synthetic_history'"
                )
            ),
            "outbox": rows("SELECT state,count(*) AS total FROM outbox GROUP BY state"),
            "attempts": rows("SELECT * FROM attempts ORDER BY id DESC LIMIT 50"),
            "events": events,
            "event_total": db.execute("SELECT count(*) FROM events").fetchone()[0],
            "comparisons": imported,
            "worker": dict(
                db.execute(
                    "SELECT key,value FROM meta WHERE key IN ('last_cycle','last_error')"
                )
            ),
            "technical_errors": rows(
                "SELECT * FROM technical_errors ORDER BY id DESC LIMIT 20"
            ),
            "ticks": rows("SELECT * FROM ticks ORDER BY slot DESC LIMIT 10"),
        }
    finally:
        db.close()


HTML = r"""<!doctype html><html lang="pt"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Laboratório Vivo · CENTERWAY</title>
<style>body{font:16px system-ui;margin:0;background:#10191c;color:#e2eee9}main{max-width:1200px;margin:auto;padding:24px}h1{font-size:2rem}small,.muted{color:#a3bbb1}section{background:#1b2c30;border:1px solid #34504d;border-radius:12px;padding:20px;margin:20px 0}button{padding:10px 18px;border:0;border-radius:7px;background:#b8efcb;color:#10271c;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;max-height:420px;overflow:auto}summary{cursor:pointer;padding:10px 0}nav{display:flex;gap:12px;align-items:center}.stats{display:flex;gap:22px;flex-wrap:wrap}.stat{font-size:1.5rem}.error{color:#ffb5a6}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;text-align:left;border-bottom:1px solid #34504d}#notice{min-height:24px}</style>
<main><small>LABORATÓRIO INDEPENDENTE · DUAS EMPRESAS SaaS</small><h1>Operações em movimento</h1><p>Verdade privada e medições autorizadas. Uma simulação não é uma avaliação CENTERWAY.</p><p id="notice" role="status"></p><div id="companies"></div><small>Atualização a cada 5 segundos · pause cada empresa separadamente · credenciais nunca são apresentadas</small></main>
<script>
const csrf='__CSRF__'; let states={}; let cursors={};
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
function detail(parent,title,value){let d=el('details'),s=el('summary',title);d.dataset.key=parent.dataset.company+':'+title.replace(/\d+/g,'#');d.open=window.labOpen?.has(d.dataset.key)||false;d.append(s,el('pre',JSON.stringify(value,null,2)));parent.append(d)}
async function toggle(id,paused){try{let r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-CSRF':csrf},body:JSON.stringify({company:id,paused})});if(!r.ok)throw Error('Controlo recusado');await refresh()}catch(e){document.querySelector('#notice').textContent=e.message}}
async function page(id){cursors[id]=(cursors[id]||0)+100;await refresh()}
async function refresh(){try{let r=await fetch('/api/state?'+new URLSearchParams(Object.fromEntries(Object.entries(cursors).map(([k,v])=>[k,String(v)]))));if(!r.ok)throw Error('Sessão do painel recusada');let data=await r.json();states=data;window.labOpen=new Set([...document.querySelectorAll('details[open]')].map(x=>x.dataset.key));const box=document.querySelector('#companies');box.replaceChildren();for(let c of data.companies){let s=el('section');s.dataset.company=c.id;s.append(el('h2',c.name),el('p',c.mode+' · '+(c.send_enabled?'emissor autorizado na configuração':'envio desligado')));if(c.error){let e=el('p',c.error);e.className='error';s.append(e)}if(c.data){let d=c.data;let nav=el('nav');nav.append(el('b',d.paused?'Pausada':'Em execução'));let b=el('button',d.paused?'Retomar':'Pausar');b.onclick=()=>toggle(c.id,!d.paused);nav.append(b);s.append(nav);let stats=el('p');stats.className='stats';for(let [k,v] of Object.entries(d.counts))stats.append(el('span',({'produced':'Medições produzidas','sent_measurements':'Aceites por HTTP','awaiting_receipts':'Correções à espera de IDs','history_ticks':'Ciclos históricos'}[k]||k)+': '+v));stats.append(el('span','Clientes ativos: '+d.clients.filter(x=>x.active).length+'/'+d.clients.length));s.append(stats);detail(s,'Clientes e cenários operacionais atuais',d.clients);detail(s,'Fila durável e respostas HTTP recentes', {outbox:d.outbox,attempts:d.attempts,technical_errors:d.technical_errors,worker:d.worker});detail(s,'Verdade operacional privada · acontecimentos '+(cursors[c.id]||0)+'–'+((cursors[c.id]||0)+d.events.length)+' / '+d.event_total,d.events);let next=el('button','Próxima página de acontecimentos');next.disabled=d.events.length<100;next.onclick=()=>page(c.id);s.append(next);let first=el('button','Início');first.onclick=()=>{cursors[c.id]=0;refresh()};s.append(first);detail(s,'Avaliações CENTERWAY importadas · comparar com factos privados e corte temporal',d.comparisons);detail(s,'Proveniência temporal dos últimos ciclos',d.ticks)}box.append(s)}document.querySelector('#notice').textContent='Última leitura: '+new Date().toLocaleTimeString()}catch(e){document.querySelector('#notice').textContent=e.message}}
refresh();setInterval(refresh,5000);
</script></html>"""


def make_server(cfg, paths, health, bind="127.0.0.1", port=8765):
    password = Path(cfg["admin_password_file"]).read_text().strip()
    if len(password) < 20:
        raise ValueError("dashboard_password_minimum_20_characters")
    expected = base64.b64encode((cfg["admin_user"] + ":" + password).encode()).decode()
    csrf = secrets.token_hex(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # No paths/headers/passwords in access logs.

        def reply(self, status, value, kind="application/json"):
            body = (
                value.encode() if isinstance(value, str) else json.dumps(value).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="Private living lab"')
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            actual = self.headers.get("Authorization", "")
            return hmac.compare_digest(actual.encode(), ("Basic " + expected).encode())

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/healthz":
                return self.reply(200, {"alive": True})
            if not self.authenticated():
                return self.reply(401, {"error": "authentication_required"})
            if parsed.path == "/":
                return self.reply(200, HTML.replace("__CSRF__", csrf), "text/html")
            if parsed.path != "/api/state":
                return self.reply(404, {"error": "not_found"})
            companies = []
            query = parse_qs(parsed.query)
            for c in cfg["companies"]:
                data = None
                error = health.get(c["id"])
                try:
                    after = int(query.get(c["id"], ["0"])[0])
                    if after < 0:
                        raise ValueError()
                    if c["id"] in paths:
                        data = report(paths[c["id"]], after)
                except (ValueError, OverflowError):
                    return self.reply(400, {"error": "invalid_cursor"})
                except Exception:
                    error = "state_read_failed"
                companies.append(
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "mode": cfg["mode"],
                        "send_enabled": c["send_enabled"],
                        "error": error,
                        "data": data,
                    }
                )
            return self.reply(200, {"companies": companies})

        def do_POST(self):
            if not self.authenticated():
                return self.reply(401, {"error": "authentication_required"})
            if self.path != "/api/control":
                return self.reply(404, {"error": "not_found"})
            if not hmac.compare_digest(self.headers.get("X-Lab-CSRF", ""), csrf):
                return self.reply(403, {"error": "csrf_required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError()
                value = json.loads(self.rfile.read(length))
                if (
                    set(value) != {"company", "paused"}
                    or type(value["paused"]) is not bool
                ):
                    raise ValueError()
                path = paths[value["company"]]
                db = connect(path)
                try:
                    with transaction(db):
                        db.execute(
                            "UPDATE controls SET paused=? WHERE id=1",
                            (int(value["paused"]),),
                        )
                        if not value["paused"]:
                            db.execute(
                                "INSERT OR REPLACE INTO meta VALUES('resume_slot',?)",
                                (str(int(time.time() // cfg["interval_seconds"])),),
                            )
                        event(
                            db,
                            None,
                            None,
                            "operator_pause" if value["paused"] else "operator_resume",
                            {
                                "at": time.time(),
                                "resume_skips_paused_gap": not value["paused"],
                            },
                        )
                finally:
                    db.close()
            except (ValueError, KeyError):
                return self.reply(400, {"error": "invalid_control"})
            except Exception:
                return self.reply(503, {"error": "state_unavailable"})
            return self.reply(200, {"paused": value["paused"]})

    return ThreadingHTTPServer((bind, port), Handler)
