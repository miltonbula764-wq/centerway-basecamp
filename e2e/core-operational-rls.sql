-- Uses real Auth user IDs and persisted HTTP-created records; runner rolls back everything.
DO $test$
DECLARE f jsonb:=current_setting('cw.core_fixture')::jsonb;
  tenant uuid:=(f->>'tenant')::uuid; actor uuid:=(f->>'admin')::uuid;
  op uuid:=(f->>'operator')::uuid; viewer uuid:=(f->>'viewer')::uuid;
  outsider uuid:=(f->>'outsider')::uuid; t text; u uuid; n int:=0;
  save_sql text; evaluate_sql text;
BEGIN
  CREATE FUNCTION pg_temp.integrated_as(_uid uuid,_sql text) RETURNS text LANGUAGE plpgsql AS $fn$
  DECLARE answer text;
  BEGIN
    PERFORM set_config('request.jwt.claims',CASE WHEN _uid IS NULL THEN '{"role":"anon"}' ELSE jsonb_build_object('role','authenticated','sub',_uid)::text END,true);
    PERFORM set_config('role',CASE WHEN _uid IS NULL THEN 'anon' ELSE 'authenticated' END,true);
    EXECUTE _sql INTO answer; RESET ROLE; RETURN answer;
  EXCEPTION WHEN OTHERS THEN RESET ROLE; RAISE;
  END $fn$;
  CREATE FUNCTION pg_temp.integrated_error(_uid uuid,_sql text,_state text) RETURNS int LANGUAGE plpgsql AS $fn$
  BEGIN
    BEGIN PERFORM pg_temp.integrated_as(_uid,_sql);
    EXCEPTION WHEN OTHERS THEN
      IF SQLSTATE=_state THEN RETURN 1; END IF;
      RAISE EXCEPTION 'Expected %, got %: %',_state,SQLSTATE,SQLERRM;
    END;
    RAISE EXCEPTION 'Unauthorized operation unexpectedly succeeded: %',_sql;
  END $fn$;
  FOREACH t IN ARRAY ARRAY['cw_operational_cases','cw_operational_events','cw_operational_cycles'] LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||t)::regclass) THEN RAISE EXCEPTION 'RLS disabled: %',t; END IF;
    n:=n+1;
    FOREACH u IN ARRAY ARRAY[actor,op,viewer] LOOP
      IF pg_temp.integrated_as(u,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int<1 THEN RAISE EXCEPTION 'Member read blocked'; END IF;
      n:=n+1;
      n:=n+pg_temp.integrated_error(u,format('INSERT INTO public.%I DEFAULT VALUES',t),'42501');
      n:=n+pg_temp.integrated_error(u,format('UPDATE public.%I SET tenant_id=tenant_id',t),'42501');
      n:=n+pg_temp.integrated_error(u,format('DELETE FROM public.%I',t),'42501');
    END LOOP;
    IF pg_temp.integrated_as(outsider,format('SELECT count(*) FROM public.%I WHERE tenant_id=%L',t,tenant))::int<>0 THEN RAISE EXCEPTION 'Cross-company read'; END IF;
    n:=n+1;
    n:=n+pg_temp.integrated_error(NULL,format('SELECT count(*) FROM public.%I',t),'42501');
    BEGIN
      EXECUTE format('UPDATE public.%I SET tenant_id=gen_random_uuid()',t);
      RAISE EXCEPTION 'Owner bypassed immutable history';
    EXCEPTION WHEN SQLSTATE '42501' THEN n:=n+1;
    END;
  END LOOP;
  n:=n+pg_temp.integrated_error(viewer,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',tenant,f->>'case',gen_random_uuid()),'42501');
  n:=n+pg_temp.integrated_error(NULL,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',tenant,f->>'case',gen_random_uuid()),'42501');
  n:=n+pg_temp.integrated_error(outsider,format('SELECT public.command_operational_case(%L,%L,0,%L,''plan'',''{}'')',f->>'foreign',f->>'case',gen_random_uuid()),'22023');
  n:=n+pg_temp.integrated_error(actor,$$SELECT public._cwop_text('{}','x')$$,'42501');
  n:=n+pg_temp.integrated_error(actor,format('SELECT public.command_operational_case(%L,%L,0,%L,''investigate'',''{}'')',tenant,f->>'case',gen_random_uuid()),'PT409');
  RAISE NOTICE 'CW_CORE_OPERATIONAL_RESULTS pass=% fail=0',n;
END $test$;
