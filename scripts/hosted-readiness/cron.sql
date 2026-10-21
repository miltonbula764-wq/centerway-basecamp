\set ON_ERROR_STOP on
-- Run separately: cron.job can contain sensitive commands. Only command conformity
-- and the known CENTERWAY job are exported; never export other jobs/raw commands.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SELECT to_regclass('cron.job') IS NOT NULL AS cron_available \gset
\if :cron_available
SELECT jsonb_build_object('format',1,'available',true,
 'background_workers',current_setting('cron.use_background_workers',true),
 'timezone',current_setting('cron.timezone',true),
 'jobs',(SELECT coalesce(jsonb_agg(jsonb_build_object(
   'jobid',jobid,'jobname',jobname,'schedule',schedule,'active',active,
   'database',database,'username',username,
   'command_matches',regexp_replace(btrim(command),'\s+',' ','g') =
     'SET LOCAL statement_timeout=''45s''; SET LOCAL ROLE centerway_review_scheduler; SELECT public.process_review_schedule(10);',
   'legacy_transaction_wrapper',command ~* '(^|;)\s*(BEGIN|START\s+TRANSACTION|COMMIT)\y'
 ) ORDER BY jobid),'[]'::jsonb) FROM cron.job WHERE jobname='centerway-prepare-reviews-v1'),
 'runs',(SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.start_time),'[]'::jsonb) FROM (
   SELECT d.jobid,d.runid,d.status,d.start_time,d.end_time
   FROM cron.job_run_details d JOIN cron.job j ON j.jobid=d.jobid
   WHERE j.jobname='centerway-prepare-reviews-v1' ORDER BY d.start_time DESC LIMIT 20
 ) r));
\else
SELECT jsonb_build_object('format',1,'available',false,'jobs','[]'::jsonb,'runs','[]'::jsonb);
\endif
ROLLBACK;
