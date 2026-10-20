-- Read-only effective ACL assertions after 0018. No service_role impersonation.
DO $$ DECLARE t text; who text; priv text; f text; BEGIN
 FOREACH t IN ARRAY ARRAY['ingestion_credentials','ingestion_api_requests','ingestion_api_events'] LOOP
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||t)::regclass) THEN RAISE EXCEPTION 'RLS disabled: %',t; END IF;
  FOREACH who IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
   FOREACH priv IN ARRAY ARRAY['INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] LOOP
    IF has_table_privilege(who,'public.'||t,priv) THEN RAISE EXCEPTION 'Unexpected %.% %',who,t,priv; END IF;
   END LOOP;
   FOREACH priv IN ARRAY ARRAY['INSERT','UPDATE','REFERENCES'] LOOP
    IF has_any_column_privilege(who,'public.'||t,priv) THEN RAISE EXCEPTION 'Unexpected column %.% %',who,t,priv; END IF;
   END LOOP;
   IF who<>'authenticated' AND has_any_column_privilege(who,'public.'||t,'SELECT') THEN RAISE EXCEPTION 'Unexpected private read %.%',who,t; END IF;
  END LOOP;
 END LOOP;
 FOREACH who IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
  IF has_column_privilege(who,'public.ingestion_credentials','secret_hash','SELECT') OR has_column_privilege(who,'public.ingestion_credentials','request_hash','SELECT') THEN RAISE EXCEPTION 'Private credential hash exposed to %',who; END IF;
  FOREACH f IN ARRAY ARRAY['public._c01_import(uuid,uuid,text,timestamptz,timestamptz,boolean,text,jsonb,uuid)','public._ingestion_credential_guard()','public._ingestion_credential_audit()'] LOOP
   IF has_function_privilege(who,f,'EXECUTE') THEN RAISE EXCEPTION 'Private function exposed %.%',who,f; END IF;
  END LOOP;
  FOREACH f IN ARRAY ARRAY['public.create_ingestion_credential(uuid,text,text,timestamptz,uuid,uuid)','public.revoke_ingestion_credential(uuid,uuid)'] LOOP
   IF has_function_privilege(who,f,'EXECUTE') IS DISTINCT FROM (who='authenticated') THEN RAISE EXCEPTION 'Administrative ACL %.%',who,f; END IF;
  END LOOP;
  IF has_function_privilege(who,'public.ingest_external_observations(text,uuid,jsonb)','EXECUTE') IS DISTINCT FROM (who IN ('anon','authenticated')) THEN RAISE EXCEPTION 'Narrow API ACL %',who; END IF;
 END LOOP;
 RAISE NOTICE 'Ingestion ACL passed: RLS, private hashes/engine, no direct writes or administrative anon grants.';
END $$;
