\set ON_ERROR_STOP on
-- Metadata only. No application RPC, business row, credential or migration is read/executed.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SELECT jsonb_build_object(
 'format', 1,
 'captured_at', CURRENT_TIMESTAMP,
 'database', current_database(),
 'server_version', current_setting('server_version'),
 'read_only', current_setting('transaction_read_only'),
 'tables', (SELECT coalesce(jsonb_agg(jsonb_build_object(
   'name', c.relname, 'rls', c.relrowsecurity, 'force_rls', c.relforcerowsecurity,
   'policies', (SELECT count(*) FROM pg_policy WHERE polrelid=c.oid),
   'tenant_column', EXISTS(SELECT FROM pg_attribute WHERE attrelid=c.oid AND attname='tenant_id' AND NOT attisdropped),
   'authenticated_insert', has_table_privilege('authenticated', c.oid, 'INSERT'),
   'authenticated_update', has_table_privilege('authenticated', c.oid, 'UPDATE'),
   'authenticated_delete', has_table_privilege('authenticated', c.oid, 'DELETE')
 ) ORDER BY c.relname),'[]'::jsonb) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p')),
 'functions', (SELECT coalesce(jsonb_agg(jsonb_build_object(
   'name', p.proname, 'identity', p.oid::regprocedure::text,
   'definer', p.prosecdef, 'owner', pg_get_userbyid(p.proowner), 'settings', p.proconfig,
   'definition_md5', md5(pg_get_functiondef(p.oid)),
   'anon_execute', has_function_privilege('anon',p.oid,'EXECUTE'),
   'authenticated_execute', has_function_privilege('authenticated',p.oid,'EXECUTE'),
   'service_execute', has_function_privilege('service_role',p.oid,'EXECUTE'),
   'scheduler_execute', CASE WHEN EXISTS(SELECT FROM pg_roles WHERE rolname='centerway_review_scheduler')
     THEN has_function_privilege('centerway_review_scheduler',p.oid,'EXECUTE') ELSE false END
 ) ORDER BY p.proname,p.oid::regprocedure::text),'[]'::jsonb) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.prokind='f'),
 'constraints', (SELECT coalesce(jsonb_agg(jsonb_build_object(
   'table',c.conrelid::regclass::text,'name',c.conname,'type',c.contype,
   'validated',c.convalidated,'definition',pg_get_constraintdef(c.oid))
   ORDER BY c.conrelid::regclass::text,c.conname),'[]'::jsonb)
   FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
   WHERE n.nspname='public' AND c.contype IN ('f','u','p','c')),
 'triggers', (SELECT coalesce(jsonb_agg(jsonb_build_object(
   'table',t.tgrelid::regclass::text,'name',t.tgname,'enabled',t.tgenabled,
   'definition_md5',md5(pg_get_triggerdef(t.oid))) ORDER BY t.tgrelid::regclass::text,t.tgname),'[]'::jsonb)
   FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND NOT t.tgisinternal),
 'scheduler_roles', (SELECT coalesce(jsonb_agg(jsonb_build_object('name',rolname,'login',rolcanlogin,
    'superuser',rolsuper,'bypass_rls',rolbypassrls,'inherit',rolinherit)),'[]'::jsonb)
    FROM pg_roles WHERE rolname='centerway_review_scheduler'),
 'scheduler_members', (SELECT coalesce(jsonb_agg(pg_get_userbyid(m.member) ORDER BY pg_get_userbyid(m.member)),'[]'::jsonb)
    FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid WHERE r.rolname='centerway_review_scheduler'),
 'extensions', (SELECT jsonb_agg(jsonb_build_object('name',extname,'version',extversion) ORDER BY extname) FROM pg_extension),
 'migration_ledgers', (SELECT coalesce(jsonb_agg(n.nspname||'.'||c.relname ORDER BY n.nspname,c.relname),'[]'::jsonb)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relname IN ('__drizzle_migrations','schema_migrations') AND c.relkind='r')
);
ROLLBACK;
