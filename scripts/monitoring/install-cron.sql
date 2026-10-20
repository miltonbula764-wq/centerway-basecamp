-- Manual infrastructure integration step ONLY, after 0020, with Supabase Cron enabled.
-- Run as postgres in the chosen environment; never from the browser or a service key.
-- This script does not enable extensions, install migrations, or change application state.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_extension WHERE extname='pg_cron') THEN
  RAISE EXCEPTION 'Enable Supabase Cron separately before installing this job';
 END IF;
 IF NOT pg_has_role(current_user,'centerway_review_scheduler','MEMBER') THEN
  RAISE EXCEPTION 'Scheduler capability membership required';
 END IF;
END $$;
-- Same name updates the existing job, preventing duplicate schedules.
SELECT cron.schedule('centerway-prepare-reviews-v1','* * * * *',
 $job$BEGIN; SET LOCAL statement_timeout='45s'; SET LOCAL ROLE centerway_review_scheduler; SELECT public.process_review_schedule(10); COMMIT;$job$);
COMMIT;
-- Disable later with: SELECT cron.unschedule('centerway-prepare-reviews-v1');
-- Inspect infrastructure attempts: SELECT * FROM cron.job_run_details ORDER BY start_time DESC LIMIT 20;
-- Inspect tenant failures through scheduled_reviews; business failures are caught per tenant.
