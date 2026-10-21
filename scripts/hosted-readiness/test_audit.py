"""Offline, deterministic regressions. No database, network or hosted credentials."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('readiness_audit', HERE/'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def healthy():
    return {'format':1,'read_only':'on',
            'tables':[{'name':n,'rls':True,'tenant_column':True} for n in audit.REQUIRED_TABLES],
            'functions':[{'name':n,'definer':True,'scheduler_execute':True}
                         for n in audit.REQUIRED_FUNCTIONS],
            'scheduler_roles':[{'name':'centerway_review_scheduler'}],
            'scheduler_members':['postgres']}


def cron():
    return {'format':1,'available':True,'jobs':[{'jobid':7,'command_matches':True,
            'legacy_transaction_wrapper':False,'schedule':'* * * * *','active':True}],
            'runs':[{'status':'succeeded','end_time':'2026-10-21T00:00:01Z'}]}


class ReadinessTests(unittest.TestCase):
    def test_source_manifest(self):
        self.assertEqual(audit.manifest(),json.loads((HERE/'migration-manifest.json').read_text()))

    def test_missing_migration_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); d=root/'drizzle/migrations/meta'; d.mkdir(parents=True)
            (d/'_journal.json').write_text('{"entries":[{"idx":0,"tag":"missing","when":1}]}')
            with self.assertRaises(AssertionError): audit.manifest(root)

    def test_unjournaled_sql_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); d=root/'drizzle/migrations/meta'; d.mkdir(parents=True)
            (d/'_journal.json').write_text('{"entries":[]}')
            (d.parent/'unexpected.sql').write_text('SELECT 1;')
            with self.assertRaises(AssertionError): audit.manifest(root)

    def test_local_metadata_does_not_certify_hosted(self):
        self.assertEqual([],audit.catalog_findings(healthy()))
        self.assertIn('hosted status unknown',audit.manifest()['scope'])

    def test_missing_contract(self):
        d=healthy(); d['functions']=[]
        self.assertIn('missing_function:ingest_external_observations',audit.catalog_findings(d))

    def test_rls_disabled(self):
        d=healthy(); d['tables'][0]['rls']=False
        self.assertTrue(any(x.startswith('rls_disabled:') for x in audit.catalog_findings(d)))

    def test_history_write_grant(self):
        d=healthy(); next(t for t in d['tables'] if t['name']=='observations')['authenticated_update']=True
        self.assertIn('direct_history_write:observations',audit.catalog_findings(d))

    def test_privileged_scheduler(self):
        for flag in ('login','superuser','bypass_rls','inherit'):
            d=healthy();d['scheduler_roles'][0][flag]=True
            self.assertIn('unsafe_or_missing_scheduler_role',audit.catalog_findings(d))

    def test_public_membership(self):
        for role in ('anon','authenticated','service_role','authenticator'):
            d=healthy();d['scheduler_members'].append(role)
            self.assertIn('public_scheduler_membership',audit.catalog_findings(d))

    def test_public_worker(self):
        for flag in ('anon_execute','authenticated_execute','service_execute'):
            d=healthy(); next(f for f in d['functions'] if f['name']=='process_review_schedule')[flag]=True
            self.assertIn('unsafe_or_missing_worker_acl',audit.catalog_findings(d))

    def test_cron_missing_duplicate(self):
        self.assertTrue(audit.cron_findings({'format':1,'available':False}))
        for jobs in ([],cron()['jobs']*2):
            d=cron();d['jobs']=jobs
            self.assertEqual(['cron_job_missing_or_duplicated'],audit.cron_findings(d))

    def test_cron_command_schedule_active(self):
        for key,value,expected in [('command_matches',False,'cron_command_drift'),
                                   ('legacy_transaction_wrapper',True,'cron_command_drift'),
                                   ('schedule','5 seconds','cron_schedule_drift'),
                                   ('active',False,'cron_inactive')]:
            d=cron();d['jobs'][0][key]=value
            self.assertIn(expected,audit.cron_findings(d))

    def test_cron_runs_are_not_manual_proof(self):
        self.assertEqual([],audit.cron_findings(cron()))
        for status in ('failed','running','starting'):
            d=cron();d['runs'][0]['status']=status
            self.assertIn('cron_failed_or_unfinished_runs',audit.cron_findings(d))
        d=cron();d['runs']=[]
        self.assertIn('cron_no_observed_runs',audit.cron_findings(d))

    def test_shipped_command_matches_inspection_and_update_template(self):
        source=(audit.ROOT/'scripts/monitoring/install-cron.sql').read_text()
        command=re.search(r'\$job\$(.*?)\$job\$',source,re.S).group(1)
        self.assertNotRegex(command,r'(?i)\b(BEGIN|COMMIT)\b')
        self.assertIn(command,(HERE/'update-cron.sql.example').read_text())
        self.assertIn(command.replace("'","''"),(HERE/'cron.sql').read_text())
        self.assertIn("statement_timeout='45s'",command)
        self.assertIn('SET LOCAL ROLE centerway_review_scheduler;',command)
        self.assertIn("to_jsonb(j)-'command'",(HERE/'update-cron.sql.example').read_text())


if __name__=='__main__': unittest.main()
