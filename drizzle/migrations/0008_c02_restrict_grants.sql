-- Default privileges had granted more than SELECT; C02 tables are read-only for clients and invisible to anon.
REVOKE ALL ON public.c02_runs, public.c02_results FROM anon, authenticated;
GRANT SELECT ON public.c02_runs, public.c02_results TO authenticated;