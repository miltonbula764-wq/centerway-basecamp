-- Disposable database only. All public roles must lack the private capability.
DO $$ DECLARE r text;t text;BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role','authenticator'] LOOP
  IF has_schema_privilege(r,'connected_private','USAGE') OR pg_has_role(r,'centerway_connector_backend','MEMBER') THEN RAISE EXCEPTION 'private_capability_leak %',r;END IF;
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='connected_private' LOOP
   IF has_table_privilege(r,'connected_private.'||t,'SELECT') OR has_table_privilege(r,'connected_private.'||t,'INSERT') OR has_table_privilege(r,'connected_private.'||t,'UPDATE') OR has_table_privilege(r,'connected_private.'||t,'DELETE') THEN RAISE EXCEPTION 'table_privilege_leak % %',r,t;END IF;
  END LOOP;
 END LOOP;
 IF EXISTS(SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='connected_private' AND c.relkind='r' AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)) THEN RAISE EXCEPTION 'RLS missing';END IF;
END $$;
BEGIN;
SET LOCAL ROLE centerway_connector_backend;
SELECT set_config('request.jwt.claims','{}',true);
DO $$ BEGIN
 IF EXISTS(SELECT FROM connected_private.connections) OR EXISTS(SELECT FROM connected_private.oauth_states) OR EXISTS(SELECT FROM connected_private.batches) OR EXISTS(SELECT FROM connected_private.measurements) OR EXISTS(SELECT FROM connected_private.attempts) THEN RAISE EXCEPTION 'unclaimed_runtime_read';END IF;
END $$;
ROLLBACK;
