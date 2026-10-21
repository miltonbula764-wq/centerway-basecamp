"""Offline preparation/analysis only: no networking, SQL client, env or secrets.

The manifest describes source bytes, not proof of applied hosted migrations.
Exit 2 means snapshot has blocking findings; 0 never certifies hosted readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TABLES = {
    'memberships', 'tenant_value_profiles', 'profile_indicators', 'subjects',
    'observations', 'c02_runs', 'c02_results', 'c03_bundles', 'c03_attempts',
    'c04_configurations', 'c04_evaluations', 'cw_cases', 'cw_operational_cases', 'cw_operational_events',
    'ingestion_credentials', 'ingestion_api_requests', 'cw_review_scans',
    'cw_review_entries', 'cw_review_events', 'cw_review_attempts',
    'cw_notifications', 'cw_notification_jobs', 'cw_notification_attempts',
}
REQUIRED_FUNCTIONS = {
    'create_tenant', 'import_observations', 'ingest_external_observations',
    'run_deterioration_analysis', 'build_evidence_bundle', 'evaluate_c04_configuration',
    'core_followup_queue', 'prepare_scheduled_reviews', 'scheduled_reviews',
    'process_review_schedule', 'assign_operational_case', 'notification_inbox',
}
APPEND_ONLY = {'observations', 'c02_runs', 'c02_results', 'c03_bundles',
               'c04_evaluations', 'cw_review_events', 'cw_operational_events'}


def manifest(root=ROOT):
    directory = root / 'drizzle/migrations'
    journal = json.loads((directory / 'meta/_journal.json').read_text())['entries']
    assert [e['idx'] for e in journal] == list(range(len(journal))), 'Non-contiguous journal'
    assert len({e['tag'] for e in journal}) == len(journal), 'Duplicate migration tag'
    listed = {e['tag'] + '.sql' for e in journal}
    assert listed == {p.name for p in directory.glob('*.sql')}, 'Unjournaled/missing SQL'
    return {'format': 1, 'scope': 'source-only; hosted status unknown', 'migrations': [
        {'index': e['idx'], 'tag': e['tag'], 'when': e['when'],
         'sha256': hashlib.sha256((directory / (e['tag']+'.sql')).read_bytes()).hexdigest()}
        for e in journal]}


def catalog_findings(data):
    issues = []
    if data.get('format') != 1 or data.get('read_only') != 'on':
        issues.append('invalid_or_non_read_only_snapshot')
    tables = {t['name']: t for t in data.get('tables', [])}
    funcs = {f['name'] for f in data.get('functions', [])}
    issues += ['missing_table:'+n for n in sorted(REQUIRED_TABLES-tables.keys())]
    issues += ['missing_function:'+n for n in sorted(REQUIRED_FUNCTIONS-funcs)]
    for name, t in tables.items():
        if (t.get('tenant_column') or name in REQUIRED_TABLES) and not t.get('rls'):
            issues.append('rls_disabled:'+name)
        if name in APPEND_ONLY and any(t.get('authenticated_'+op) for op in ('insert','update','delete')):
            issues.append('direct_history_write:'+name)
    roles = data.get('scheduler_roles', [])
    if len(roles) != 1 or any(roles[0].get(k) for k in ('login','superuser','bypass_rls','inherit')):
        issues.append('unsafe_or_missing_scheduler_role')
    if set(data.get('scheduler_members', [])) & {'anon','authenticated','service_role','authenticator'}:
        issues.append('public_scheduler_membership')
    workers = [f for f in data.get('functions',[]) if f['name']=='process_review_schedule']
    if len(workers) != 1 or not workers[0].get('definer') or not workers[0].get('scheduler_execute') or any(
        workers[0].get(k) for k in ('anon_execute','authenticated_execute','service_execute')):
        issues.append('unsafe_or_missing_worker_acl')
    return issues


def cron_findings(data):
    if data.get('format') != 1 or not data.get('available'):
        return ['cron_unavailable_or_not_inspected']
    jobs = data.get('jobs', [])
    if len(jobs) != 1:
        return ['cron_job_missing_or_duplicated']
    j = jobs[0]
    issues = []
    if not j.get('command_matches') or j.get('legacy_transaction_wrapper'):
        issues.append('cron_command_drift')
    if j.get('schedule') != '* * * * *':
        issues.append('cron_schedule_drift')
    if not j.get('active'):
        issues.append('cron_inactive')
    # Owner, target database and memberships must also be reviewed against the
    # selected project's private inventory; do not guess them from local fixtures.
    if not data.get('runs'):
        issues.append('cron_no_observed_runs')
    elif any(r.get('status') != 'succeeded' or not r.get('end_time') for r in data['runs']):
        issues.append('cron_failed_or_unfinished_runs')
    return issues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path)
    p.add_argument('--cron', type=Path)
    args = p.parse_args()
    result = {'manifest': manifest(), 'hosted_approval': 'PENDING: no hosted verification performed',
              'blocking_findings': []}
    if args.catalog:
        result['blocking_findings'] += catalog_findings(json.loads(args.catalog.read_text()))
    if args.cron:
        result['blocking_findings'] += cron_findings(json.loads(args.cron.read_text()))
    print(json.dumps(result, indent=2))
    return 2 if result['blocking_findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
