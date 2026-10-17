import fs from 'node:fs';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
const config = JSON.parse(fs.readFileSync('e2e/private/public.json', 'utf8'));
assert.equal(config.url, 'http://127.0.0.1:54321');
const password = randomBytes(24).toString('base64url') + '-Aa1!';
async function request(path, token, body, method = 'POST') {
  const response = await fetch(config.url + path, {
    method, headers: { apikey: config.anon, Authorization: `Bearer ${token || config.anon}`,
      'Content-Type': 'application/json', Prefer: 'return=representation' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${path}: HTTP ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}
const rpc = (token, name, body) => request('/rest/v1/rpc/' + name, token, body);
const users = {};
for (const role of ['admin', 'operator', 'viewer', 'ownerB']) {
  const email = `cw-${role.toLowerCase()}@example.invalid`;
  await request('/auth/v1/signup', null, { email, password });
  const session = await request('/auth/v1/token?grant_type=password', null, { email, password });
  assert.ok(session.access_token && session.user.id, 'Real password grant must issue a session');
  const verified = await request('/auth/v1/user', session.access_token, undefined, 'GET');
  assert.equal(verified.id, session.user.id);
  users[role] = { email, password, id: verified.id, token: session.access_token };
}
const tenantA = await rpc(users.admin.token, 'create_tenant', { _name: 'E2E Tenant A', _subject_unit_type: 'organization' });
const tenantB = await rpc(users.ownerB.token, 'create_tenant', { _name: 'E2E Tenant B', _subject_unit_type: 'organization' });
for (const role of ['operator', 'viewer']) await rpc(users.admin.token, 'add_tenant_member', {
  _tenant_id: tenantA, _user_id: users[role].id, _role: role,
});
await rpc(users.ownerB.token, 'add_tenant_member', { _tenant_id: tenantB, _user_id: users.admin.id, _role: 'viewer' });
const now = new Date();
const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
const date = (days) => new Date(midnight + days * 86400000).toISOString();
const indicator = {
  name: 'Resultado sintético', classification: 'outcome', unit: 'count', direction: 'higher_is_better',
  baseline_method: 'fixed_value', baseline_value: 80, baseline_min_period_days: 7,
  observation_window_days: 7, comparison_window_days: 7, min_coverage_pct: 100, min_denominator: 1,
  deterioration_kind: 'absolute', deterioration_operator: 'lt', deterioration_value: 56,
  deterioration_consecutive_windows: 2, recovery_kind: 'absolute', recovery_operator: 'gte',
  recovery_value: 72, recovery_consecutive_windows: 2, aggregation: 'mean', expected_cadence_days: 7,
  denominator_mode: 'observation_count',
};
async function profile(token, tenant) {
  const id = await rpc(token, 'create_value_profile_draft', { _tenant_id: tenant, _promise: 'Promessa histórica v1' });
  for (const row of [
    { ...indicator, tenant_id: tenant, profile_id: id, key: 'outcome' },
    { ...indicator, name: 'Sem medições', tenant_id: tenant, profile_id: id, key: 'empty' },
    { name: 'Contexto sintético', classification: 'context', value_type: 'text', unit: 'texto', direction: 'higher_is_better',
      tenant_id: tenant, profile_id: id, key: 'notes' },
  ]) await request('/rest/v1/profile_indicators', token, row);
  await rpc(token, 'approve_value_profile', { _profile_id: id });
  return id;
}
const profileA = await profile(users.admin.token, tenantA);
const profileB = await profile(users.ownerB.token, tenantB);
async function subject(token, tenant, profileId, key, name) {
  const [row] = await request('/rest/v1/subjects?select=id', token, { tenant_id: tenant, external_ref: key, display_name: name });
  const imported = await rpc(token, 'import_observations', {
    _tenant_id: tenant, _expected_profile_id: profileId, _source: 'synthetic-ci',
    _coverage_start: date(-60), _coverage_end: date(0), _coverage_declared: true, _file_name: 'synthetic.csv',
    _rows: [80, 52, 48].map((value, i) => ({
      line: i + 1, subject_external_ref: key, indicator_key: 'outcome', unit: 'count',
      value_numeric: String(value), observed_at: date(-21 + i * 7), idempotency_key: `${key}-${i}`,
    })),
  });
  assert.equal(imported.status, 'completed');
  const readable = await rpc(token, 'run_deterioration_analysis', {
    _tenant_id: tenant, _subject_id: row.id, _expected_profile_id: profileId, _as_of: date(-1),
  });
  const historicalBundle = await rpc(token, 'build_evidence_bundle', { _tenant_id: tenant, _run_id: readable.run_id });
  assert.equal(historicalBundle.status, 'built');
  const older = await rpc(token, 'run_deterioration_analysis', {
    _tenant_id: tenant, _subject_id: row.id, _expected_profile_id: profileId, _as_of: date(-7),
  });
  const primary = await rpc(token, 'run_deterioration_analysis', {
    _tenant_id: tenant, _subject_id: row.id, _expected_profile_id: profileId, _as_of: date(0),
  });
  return { id: row.id, name, primary: primary.run_id, older: older.run_id, readable: readable.run_id, historicalBundle: historicalBundle.bundle_id };
}
const customerA = await subject(users.admin.token, tenantA, profileA, 'synthetic-a', 'Cliente Sintético A');
const customerA2 = await subject(users.admin.token, tenantA, profileA, 'synthetic-a2', 'Outro Cliente A');
const customerB = await subject(users.ownerB.token, tenantB, profileB, 'synthetic-b', 'Cliente Exclusivo B');
// The current profile differs from the historical run: C03 must still display baseline 80 / v1.
const profileV2 = await rpc(users.admin.token, 'create_value_profile_version', { _from_profile_id: profileA });
await request(`/rest/v1/tenant_value_profiles?id=eq.${profileV2}`, users.admin.token, { promise: 'Promessa atual v2' }, 'PATCH');
await request(`/rest/v1/profile_indicators?profile_id=eq.${profileV2}&key=eq.outcome`, users.admin.token, { baseline_value: 100 }, 'PATCH');
await rpc(users.admin.token, 'approve_value_profile', { _profile_id: profileV2 });
// Effective RLS and function authorization over REAL HTTP/JWT, not the owner connection.
const invisible = await request(`/rest/v1/subjects?tenant_id=eq.${tenantB}&select=id`, users.viewer.token, undefined, 'GET');
assert.deepEqual(invisible, []);
for (const [label, token, body] of [
  ['viewer', users.viewer.token, { _tenant_id: tenantA, _run_id: customerA.primary }],
  ['cross-tenant operator', users.operator.token, { _tenant_id: tenantB, _run_id: customerB.primary }],
]) {
  const response = await fetch(config.url + '/rest/v1/rpc/build_evidence_bundle', {
    method: 'POST', headers: { apikey: config.anon, Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const error = await response.json();
  assert.equal(response.status, 403, label);
  assert.equal(error.code, '42501', label);
}
const tampered = users.viewer.token.slice(0, -5) + 'aaaaa';
for (const [path, status, field, code] of [
  ['/rest/v1/subjects?select=id', 401, 'code', 'PGRST301'],
  ['/auth/v1/user', 403, 'error_code', 'bad_jwt'],
]) {
  const invalid = await fetch(config.url + path, { headers: { apikey: config.anon, Authorization: `Bearer ${tampered}` } });
  assert.equal(invalid.status, status, 'Invalid JWT signature must be rejected by ' + path);
  const rejected = await invalid.json();
  assert.equal(rejected[field], code, 'JWT rejection code for ' + path);
}
const fixture = { tenantA, tenantB, customerA, customerA2, customerB, profileA, profileV2 };
fs.writeFileSync('e2e/fixtures.json', JSON.stringify(fixture, null, 2));
fs.writeFileSync('e2e/private/users.json', JSON.stringify(Object.fromEntries(Object.entries(users).map(([role, u]) => [role, { email: u.email, password: u.password, id: u.id }]))));
fs.writeFileSync('e2e/logs/auth-rls.json', JSON.stringify({
  real_password_grants: 4, get_user_verified: 4, invalid_jwt_rejected_by_auth_and_rest: true, cross_tenant_read_hidden: true,
  viewer_build_sqlstate: '42501', cross_tenant_operator_sqlstate: '42501',
  synthetic: true, production_contacted: false,
}, null, 2));
console.log('Synthetic fixtures created via real Auth/REST/RPC. Password auth, JWT and targeted RLS checks passed.');
