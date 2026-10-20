-- PROVISIONAL number: 0025 is still pending hosted installation. Reconcile numbering before merge.
-- At 100 SaaS / 1,000 clients / 100k observations, the shared Core's generic plan
-- took seconds while the same authenticated projection/custom plan took milliseconds.
-- Preserve classifier, signatures, RLS and permissions; scope planning to this one engine.
ALTER FUNCTION public._core_followup_engine(uuid,text,text,text,text,integer,uuid,uuid)
 SET plan_cache_mode = 'force_custom_plan';
NOTIFY pgrst,'reload schema';
