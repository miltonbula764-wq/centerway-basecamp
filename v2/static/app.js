'use strict';
const $ = id => document.getElementById(id);
const names = {atlas: 'AtlasFlow', nimbus: 'NimbusDesk'};
const stages = ['observed', 'detected', 'investigated', 'decided', 'executed', 'verified'];
const stateLabels = {observed:'observado',detected:'deterioração detetada',investigated:'investigado',decided:'decisão disponível',executed:'intervenção executada',verified:'verificado',insufficient_data:'dados insuficientes',healthy:'sem deterioração',needs_review:'revisão humana necessária'};
const labels = ['Observação', 'Deteção', 'Investigação', 'Decisão', 'Execução', 'Verificação'];
let tenant = '', activeCase = null, requestGeneration = 0, busy = false;
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => escape(JSON.stringify(value, null, 2));
function error(message = '') { $('error').textContent = message; $('error').hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Erro ${response.status}`);
  return data;
}
async function load() {
  const generation = ++requestGeneration, selected = tenant;
  const data = await api('/api/view' + (selected ? '?tenant=' + encodeURIComponent(selected) : ''));
  if (generation !== requestGeneration || selected !== tenant) return;
  $('login').hidden = true; $('workspace').hidden = false;
  if (!selected) {
    $('tenant').innerHTML = data.memberships.map(m => `<option value="${escape(m.tenant)}">${escape(names[m.tenant])} · ${m.role === 'operator' ? 'operador' : 'leitor'}</option>`).join('');
    tenant = data.memberships[0]?.tenant || '';
    if (tenant) return load();
  }
  render(data);
}
function render(data) {
  const c = data.case, env = data.environment, readonly = data.role !== 'operator';
  activeCase = c?.id || null;
  const index = stages.indexOf(c?.stage);
  const signal = c?.detection;
  let html = `<div class="steps">${labels.map((label,i) => `<div class="step ${i <= index ? 'done' : ''}"><strong>C0${i+1}</strong>${label}</div>`).join('')}</div>`;
  html += `<section><span class="badge">${readonly ? 'APENAS LEITURA' : 'OPERADOR'} · SANDBOX</span><h2>${escape(env.name)}</h2><p>Estado do caso: <strong data-stage="${escape(c?.stage || '')}">${escape(stateLabels[c?.stage] || 'por iniciar')}</strong></p>`;
  if (signal?.baseline) html += `<div class="metrics"><div class="metric"><strong>${signal.baseline}</strong><span>Resultados · 7 dias anteriores</span></div><div class="metric"><strong>${signal.recent}</strong><span>Resultados · 7 dias recentes</span></div><div class="metric"><strong>−${Math.round(signal.drop*100)}%</strong><span>Variação</span></div></div>`;
  if (c?.stage === 'insufficient_data') html += `<p role="status">Dados insuficientes. ${escape(signal.reason)} Nenhuma intervenção autorizada.</p>`;
  if (c?.stage === 'healthy') html += '<p>Sem deterioração suficiente para autorizar uma intervenção.</p>';
  if (c?.stage === 'needs_review') html += '<p>Causa sem ação autorizada. Necessária investigação humana.</p>';
  if (c?.decision) html += `<p><strong>Simulador · sem IA real</strong><br>${escape(c.decision.reason)}</p><p>Ação escolhida: <strong>${escape(data.catalogue[c.decision.action]?.label || 'nenhuma')}</strong></p>`;
  if (!readonly) {
    html += '<div class="actions">';
    if (!c) html += '<button data-op="advance">Iniciar C01 · observar</button>';
    else if (index >= 0 && index < 3) html += `<button data-op="advance">Continuar C0${index+2} · ${labels[index+1].toLowerCase()}</button>`;
    else if (c.stage === 'decided') html += '<button data-op="execute">Executar C05 · alterar sandbox</button>';
    if (['executed','verified'].includes(c?.stage)) {
      html += '<button data-op="verify">Verificar C06 · medir resultado</button>';
      if (tenant === 'nimbus' && !env.state.usage_batch) html += '<button class="secondary" data-op="simulate-usage">Simular uso posterior · concluir 4 relatórios</button>';
    }
    html += '</div>';
  }
  html += '</section>';
  if (c?.verification) {
    const v = c.verification;
    html += `<div class="row"><section><h3>Recuperação operacional</h3><strong>${v.operational_recovered ? 'Confirmada no sandbox' : 'Não confirmada'}</strong><p>${escape(v.probe)}</p></section><section><h3>Recuperação de valor</h3><strong>${v.value_recovered ? 'Confirmada no sandbox' : 'Ainda não confirmada'}</strong><p>${v.gained} novos resultados / mínimo ${v.value_target}.</p><p class="muted">${escape(v.reason)}</p></section></div>`;
  }
  html += `<section><h3>Ambiente persistido · revisão ${env.revision}</h3><p class="muted">Estes dados são lidos da SQLite após cada operação e sobrevivem ao reinício.</p><details><summary>Inspecionar estado atual</summary><pre>${pretty(env.state)}</pre></details></section>`;
  html += `<section><h3>Catálogo autorizado para ${escape(names[tenant])}</h3>${Object.values(data.catalogue).map(a=>`<p><strong>${escape(a.label)}</strong><br>${escape(a.effect)}<br><span class="muted">Permissão: operador · causa: ${escape(a.cause)}</span></p>`).join('')}</section>`;
  if (c) html += `<section><h3>Evidências e histórico</h3><details><summary>C01 · observações e regra de deteção</summary><pre>${pretty(c.observation)}</pre></details>${data.history.map(h=>`<div class="history"><strong>${escape(h.stage)}</strong> · ${escape(h.actor)}<time>${escape(h.created_at)}</time><details><summary>Ver registo</summary><pre>${pretty(h.detail)}</pre></details></div>`).join('')}</section>`;
  $('content').innerHTML = html;
  $('content').querySelectorAll('[data-op]').forEach(button => button.addEventListener('click', () => operate(button.dataset.op)));
}
async function operate(op) {
  if (busy) return;
  busy = true; error();
  const selectedTenant = tenant, selectedCase = activeCase;
  document.querySelectorAll('button,select').forEach(el => el.disabled = true);
  try {
    const result = await api('/api/' + op, {tenant:selectedTenant, ...(selectedCase ? {case_id:selectedCase} : {})});
    $('status').textContent = result.reused ? 'Operação já registada; efeitos não repetidos.' : 'Operação concluída e persistida.';
    if (tenant === selectedTenant) await load();
  } catch (e) { error(e.message); }
  finally { busy = false; document.querySelectorAll('button,select').forEach(el => el.disabled = false); }
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); error();
  try { await api('/api/login', {user:$('account').value,password:$('password').value}); tenant=''; await load(); }
  catch (e) { error(e.message); }
});
$('tenant').addEventListener('change', async event => {
  tenant = event.target.value; activeCase = null; $('content').replaceChildren(); $('status').textContent=''; error();
  try { await load(); } catch(e) { error(e.message); }
});
$('logout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); ++requestGeneration; tenant=''; activeCase=null; $('content').replaceChildren(); $('workspace').hidden=true; $('login').hidden=false; $('status').textContent=''; error(); }
  catch(e) { error(e.message); }
});
load().catch(e => { if (!e.message.includes('Inicie sessão')) error(e.message); });
