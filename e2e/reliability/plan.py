"""Compare exact authenticated Core projections under generic/custom planning, before/after 0026."""
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
import sys,statistics
c=json.loads(Path('e2e/private/reliability.json').read_text())['companies'][0];results={}
for mode in ['force_generic_plan','force_custom_plan']:
 samples=[]
 for _ in range(3):
  query="BEGIN;SET LOCAL statement_timeout='60s';SET LOCAL plan_cache_mode="+mode+";DO $$BEGIN PERFORM set_config('request.jwt.claims',"+lit(json.dumps({'role':'authenticated','sub':users['admin']['id']}))+",true); END$$;SET LOCAL ROLE authenticated; WITH started AS MATERIALIZED(SELECT clock_timestamp()at),answer AS MATERIALIZED(SELECT public.core_followup_queue("+lit(c['tenant'])+")value FROM started) SELECT jsonb_build_object('ms',extract(epoch FROM(clock_timestamp()-started.at))*1000,'entries',jsonb_array_length(value->'items'),'digest',md5((value->'items')::text)) FROM started,answer;ROLLBACK;"
  samples.append(json.loads(sql(query)))
 results[mode]=samples
assert len({r['digest'] for samples in results.values() for r in samples})==1,'Planning changed projection data or permissions'
kind='baseline' if '--baseline' in sys.argv else 'fixed'
Path('e2e/logs/reliability-plan-'+kind+'.json').write_text(json.dumps(results,indent=2))
if kind=='fixed':
 assert 'plan_cache_mode=force_custom_plan' in sql("SELECT proconfig::text FROM pg_proc WHERE oid='public._core_followup_engine(uuid,text,text,text,text,integer,uuid,uuid)'::regprocedure")
 before=json.loads(Path('e2e/logs/reliability-plan-baseline.json').read_text());assert before['force_custom_plan'][0]['digest']==results['force_custom_plan'][0]['digest'],'Migration changed output'
 print('PASS Core planning: byte-equivalent entries/RLS; baseline generic median ms =',round(statistics.median(r['ms'] for r in before['force_generic_plan']),3),'fixed generic caller median ms =',round(statistics.median(r['ms'] for r in results['force_generic_plan']),3),flush=True)
else:print('PASS planning baseline: equal projections, generic/custom medians ms =', {m:round(statistics.median(r['ms'] for r in rows),3) for m,rows in results.items()},flush=True)
