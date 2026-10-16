-- Read-only snapshot, no application data; use before/after migration and on clean replay.
SELECT jsonb_build_object(
  'version', version(),
  'relations', (SELECT jsonb_agg(jsonb_build_object(
    'name', c.relname, 'kind', c.relkind, 'owner', pg_get_userbyid(c.relowner),
    'acl', c.relacl::text, 'rls', c.relrowsecurity) ORDER BY c.relname)
    FROM pg_class c WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','S')),
  'functions', (SELECT jsonb_agg(jsonb_build_object(
    'signature', p.oid::regprocedure::text, 'owner', pg_get_userbyid(p.proowner),
    'acl', p.proacl::text, 'definer', p.prosecdef, 'definition_hash', md5(pg_get_functiondef(p.oid))) ORDER BY p.oid::regprocedure::text)
    FROM pg_proc p WHERE p.pronamespace='public'::regnamespace AND p.prokind='f'),
  'defaults', (SELECT jsonb_agg(jsonb_build_object(
    'owner', pg_get_userbyid(d.defaclrole), 'schema', coalesce(n.nspname,'GLOBAL'),
    'kind', d.defaclobjtype, 'acl', d.defaclacl::text))
    FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
    WHERE d.defaclnamespace IN (0,'public'::regnamespace)),
  'role_memberships', (SELECT jsonb_agg(jsonb_build_object('member',m.member::regrole::text,'role',m.roleid::regrole::text))
    FROM pg_auth_members m WHERE m.member IN ('anon'::regrole,'authenticated'::regrole)),
  'column_acls', (SELECT jsonb_agg(jsonb_build_object('table',a.attrelid::regclass::text,'column',a.attname,'acl',a.attacl::text))
    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid WHERE c.relnamespace='public'::regnamespace
    AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NOT NULL),
  'policies', (SELECT jsonb_agg(to_jsonb(p)) FROM pg_policies p WHERE schemaname='public'),
  'triggers', (SELECT jsonb_agg(jsonb_build_object('table',t.tgrelid::regclass::text,'name',t.tgname,
    'enabled',t.tgenabled,'definition',pg_get_triggerdef(t.oid)))
    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE c.relnamespace='public'::regnamespace AND NOT t.tgisinternal)
) AS catalog;
