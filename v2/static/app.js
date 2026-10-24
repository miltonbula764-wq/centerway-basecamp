'use strict';
const $ = id => document.getElementById(id);
const names = {atlas:'AtlasFlow', nimbus:'NimbusDesk'};
const stages = ['observed','detected','investigated','decided','executed','verified'];
const stateLabels = {observed:'observado',detected:'deterioração detetada',investigated:'investigado',decided:'decisão disponível',executed:'intervenção executada',verified:'verificado',insufficient_data:'dados insuficientes',healthy:'sem deterioração',needs_review:'revisão humana necessária',stale_evidence:'evidências desatualizadas'};
const labels = ['Observação','Deteção','Investigação','Decisão','Execução','Verificação'];
const buckets = {deterioration:'Deterioração',investigation:'Investigação',intervention:'Intervenção',recovery:'Recuperação no sandbox',exceptions:'Exceções',observation:'A observar',stable:'Estáveis'};
let tenant='', customer='', selectedCase='', activeCase=null, scopeTenant='', requestGeneration=0, busy=false;
let registry=[], memberships=[], currentPage=0;
const PAGE_SIZE=20;
const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => escape(JSON.stringify(value,null,2));
function error(message='') { $('error').textContent=message; $('error').hidden=!message; }
async function api(path,body) {
  const response=await fetch(path,body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || `Erro ${response.status}`);
  return data;
}
function params(values) { return new URLSearchParams(Object.entries(values).filter(([,v])=>v)).toString(); }
async function load() {
  const generation=++requestGeneration;
  const captured={tenant,customer,selectedCase,scopeTenant};
  const [data,detail]=await Promise.all([
    api('/api/view?'+params({tenant:scopeTenant})),
    customer ? api('/api/view?'+params({tenant,customer,case_id:selectedCase})) : Promise.resolve(null)
  ]);
  if(generation!==requestGeneration) return;
  $('login').hidden=true; $('workspace').hidden=false;
  memberships=data.memberships;
  $('tenant').innerHTML='<option value="">Todas as SaaS autorizadas</option>'+memberships.map(m=>`<option value="${escape(m.tenant)}">${escape(names[m.tenant])} · ${m.role==='operator'?'operador':'leitor'}</option>`).join('');
  $('tenant').value=captured.scopeTenant;
  const writable=memberships.filter(m=>m.role==='operator');
  $('new-customer').hidden=!writable.length;
  $('new-tenant').innerHTML=writable.map(m=>`<option value="${escape(m.tenant)}">${escape(names[m.tenant])}</option>`).join('');
  if(captured.scopeTenant && writable.some(m=>m.tenant===captured.scopeTenant)) $('new-tenant').value=captured.scopeTenant;
  registry=data.registry;
  $('counts').innerHTML=Object.entries(buckets).map(([key,label])=>`<span>${escape(label)} <strong>${data.counts[key] || 0}</strong></span>`).join('');
  renderRegistry();
  if(detail) renderDetail(detail); else {activeCase=null;$('content').replaceChildren();}
}
function renderRegistry() {
  const query=$('search').value.trim().toLocaleLowerCase(), bucket=$('bucket').value;
  const rows=registry.filter(r=>(!bucket || r.bucket===bucket) && `${r.name} ${r.customer} ${names[r.tenant]}`.toLocaleLowerCase().includes(query));
  currentPage=Math.min(currentPage,Math.max(0,Math.ceil(rows.length/PAGE_SIZE)-1));
  const page=rows.slice(currentPage*PAGE_SIZE,(currentPage+1)*PAGE_SIZE);
  $('registry-total').textContent=`${rows.length} clientes · página ${currentPage+1} de ${Math.max(1,Math.ceil(rows.length/PAGE_SIZE))}`;
  $('registry-list').innerHTML=Object.entries(buckets).map(([key,label])=>{
    const group=page.filter(r=>r.bucket===key);
    return group.length ? `<div class="registry-group"><h3>${escape(label)}</h3>${group.map(r=>`<button class="client-row secondary" data-open-tenant="${escape(r.tenant)}" data-open-customer="${escape(r.customer)}"><span><strong>${escape(r.name)}</strong><small>${escape(names[r.tenant])} · ${escape(r.customer)}</small></span><span>${escape(stateLabels[r.stage] || 'por iniciar')} →</span></button>`).join('')}</div>` : '';
  }).join('') || '<p>Nenhum cliente corresponde aos filtros.</p>';
  $('previous').disabled=currentPage===0;
  $('next').disabled=(currentPage+1)*PAGE_SIZE>=rows.length;
  $('registry-list').querySelectorAll('[data-open-customer]').forEach(button=>button.addEventListener('click',()=>openCustomer(button.dataset.openTenant,button.dataset.openCustomer)));
}
async function openCustomer(nextTenant,nextCustomer) {
  tenant=nextTenant; customer=nextCustomer; selectedCase=''; activeCase=null;
  $('content').replaceChildren(); error(); $('status').textContent='';
  try { await load(); $('content').scrollIntoView({behavior:'smooth',block:'start'}); } catch(e) {error(e.message);}
}
function renderDetail(data) {
  const c=data.case,env=data.environment,readonly=data.role!=='operator';
  activeCase=c?.id || null;
  const latest=!c || c.id===data.latest_case_id, index=stages.indexOf(c?.stage), signal=c?.detection;
  const terminal=c && ['verified','healthy','insufficient_data','needs_review','stale_evidence'].includes(c.stage);
  let html=`<section><span class="badge">${readonly?'APENAS LEITURA':'OPERADOR'} · SANDBOX</span><h2>${escape(env.name)}</h2><p>${escape(names[tenant])} · ${escape(customer)}</p>`;
  if(data.cases.length) html+=`<label>Ciclo consultado<select id="case-select">${data.cases.map((item,i)=>`<option value="${escape(item.id)}" ${c?.id===item.id?'selected':''}>${i===0?'Mais recente':'Histórico'} · ${escape(stateLabels[item.stage])} · ${escape(item.created_at)} · ${escape(item.id.slice(0,8))}</option>`).join('')}</select></label>`;
  if(!latest) html+='<p class="notice">Ciclo histórico: os registos estão preservados. Ações só no ciclo mais recente.</p>';
  html+=`<div class="steps">${labels.map((label,i)=>`<div class="step ${i<=index?'done':''}"><strong>C0${i+1}</strong>${label}</div>`).join('')}</div><p>Estado do caso: <strong data-stage="${escape(c?.stage || '')}">${escape(stateLabels[c?.stage] || 'por iniciar')}</strong></p>`;
  if(signal?.baseline) html+=`<div class="metrics"><div class="metric"><strong>${signal.baseline}</strong><span>Resultados · 7 dias anteriores</span></div><div class="metric"><strong>${signal.recent}</strong><span>Resultados · 7 dias recentes</span></div><div class="metric"><strong>−${Math.round(signal.drop*100)}%</strong><span>Variação</span></div></div>`;
  if(c?.stage==='insufficient_data') html+=`<p>Dados insuficientes. ${escape(signal.reason)} Introduza observações e inicie outro ciclo.</p>`;
  if(c?.stage==='healthy') html+='<p>Sem deterioração suficiente para autorizar uma intervenção.</p>';
  if(c?.stage==='needs_review') html+='<p>Causa sem ação autorizada. Necessária investigação humana.</p>';
  if(c?.stage==='stale_evidence') html+='<p>Entraram novas observações. Inicie outro ciclo para reconstruir a análise.</p>';
  if(c?.decision) html+=`<p><strong>Simulador · sem IA real</strong><br>${escape(c.decision.reason)}</p><p>Ação escolhida: <strong>${escape(data.catalogue[c.decision.action]?.label || 'nenhuma')}</strong></p>`;
  if(!readonly && latest) {
    html+='<div class="actions">';
    if(!c) html+='<button data-op="advance">Iniciar C01 · observar</button>';
    else if(index>=0 && index<3) html+=`<button data-op="advance">Continuar C0${index+2} · ${labels[index+1].toLowerCase()}</button>`;
    else if(c.stage==='decided') html+='<button data-op="execute">Executar C05 · alterar sandbox</button>';
    if(['executed','verified'].includes(c?.stage)) {
      html+='<button data-op="verify">Verificar C06 · medir resultado</button>';
      if(tenant==='nimbus' && !env.state.usage_batch) html+='<button class="secondary" data-op="simulate-usage">Simular uso posterior · concluir 4 relatórios</button>';
    }
    if(terminal) html+='<button class="secondary" data-op="advance" data-new="true">Iniciar novo ciclo C01</button>';
    html+='</div>';
  }
  html+='</section>';
  if(c?.verification) {
    const v=c.verification;
    html+=`<div class="row"><section><h3>Recuperação operacional</h3><strong>${v.operational_recovered?'Confirmada no sandbox':'Não confirmada'}</strong><p>${escape(v.probe)}</p></section><section><h3>Recuperação de valor</h3><strong>${v.value_recovered?'Confirmada no sandbox':'Ainda não confirmada'}</strong><p>${v.gained} novos resultados / mínimo ${v.value_target}.</p><p class="muted">${escape(v.reason)} Medição: ${escape(v.measured_at)}</p></section></div>`;
  }
  if(!readonly) html+=`<section><h3>Introduzir observações deste cliente</h3><p>Uma linha por dia: <code>AAAA-MM-DD,valor,fonte</code>. Resultados concluídos, inteiros ≥ 0; até 366 linhas. Para C02: 14 dias completos, mesma fonte. Datas futuras e conflitos são recusados, sem sobrescrever dados.</p><form id="observation-form"><label>Observações de ${escape(customer)}<textarea id="observations" rows="7" placeholder="2026-10-01,12,manual-sandbox" required></textarea></label><div class="actions"><button type="submit">Validar e gravar lote</button><button id="sample" type="button" class="secondary">Preencher exemplo simulado de 14 dias</button></div></form><p class="muted">O exemplo só preenche o formulário. A gravação é explícita. Novos dados invalidam análises ainda não executadas.</p></section>`;
  html+=`<section><h3>Ambiente persistido · revisão ${env.revision}</h3><details><summary>Inspecionar estado atual deste cliente</summary><pre>${pretty(env.state)}</pre></details><details><summary>Catálogo autorizado para ${escape(names[tenant])}</summary>${Object.values(data.catalogue).map(a=>`<p><strong>${escape(a.label)}</strong><br>${escape(a.effect)}<br><span class="muted">Permissão: operador · causa: ${escape(a.cause)}</span></p>`).join('')}</details></section>`;
  html+=`<section><h3>Histórico deste cliente · todos os ciclos</h3>${c?`<details><summary>C01 · observações do ciclo consultado</summary><pre>${pretty(c.observation)}</pre></details>`:''}${data.history.map(h=>`<div class="history"><strong>${escape(h.stage)}</strong> · ${escape(h.actor)} · ${h.case_id ? 'ciclo '+escape(h.case_id.slice(0,8)):'registo do cliente'}<time>${escape(h.created_at)}</time><details><summary>Ver registo</summary><pre>${pretty(h.detail)}</pre></details></div>`).join('')}</section>`;
  $('content').innerHTML=html;
  $('content').querySelectorAll('[data-op]').forEach(button=>button.addEventListener('click',()=>operate(button.dataset.op,button.dataset.new==='true')));
  $('case-select')?.addEventListener('change',async event=>{selectedCase=event.target.value;activeCase=null;$('content').replaceChildren();try{await load();}catch(e){error(e.message);}});
  $('observation-form')?.addEventListener('submit',submitObservations);
  $('sample')?.addEventListener('click',()=>{
    $('observations').value=Array.from({length:14},(_,i)=>{const day=new Date();day.setUTCDate(day.getUTCDate()-13+i);return `${day.toISOString().slice(0,10)},${i<7?10:2},manual-sandbox-v2`;}).join('\n');
  });
}
async function mutate(task) {
  if(busy) return;
  busy=true; error();
  document.querySelectorAll('button,select,input,textarea').forEach(el=>el.disabled=true);
  try {await task();await load();}
  catch(e) {error(e.message);}
  finally {busy=false;document.querySelectorAll('button,select,input,textarea').forEach(el=>el.disabled=false);renderRegistry();}
}
async function operate(op,newCycle=false) {
  const captured={tenant,customer,...(activeCase && !newCycle ? {case_id:activeCase}:{})};
  await mutate(async()=>{
    const result=await api('/api/'+op,captured);
    selectedCase='';
    $('status').textContent=result.reused?'Operação já registada; efeitos não repetidos.':'Operação concluída e persistida no sandbox.';
  });
}
async function submitObservations(event) {
  event.preventDefault();
  try {
    const observations=$('observations').value.trim().split('\n').map((line,i)=>{
      const parts=line.split(',').map(v=>v.trim());
      if(parts.length!==3 || !/^\d+$/.test(parts[1])) throw new Error(`Linha ${i+1}: use data,inteiro,fonte.`);
      return {day:parts[0],value:Number(parts[1]),source:parts[2]};
    });
    const captured={tenant,customer,observations};
    await mutate(async()=>{const result=await api('/api/observations',captured);selectedCase='';$('status').textContent=`${result.inserted} observações inseridas. ${result.reused?'Lote já registado.':''}`;});
  } catch(e) {error(e.message);}
}
$('login-form').addEventListener('submit',async event=>{
  event.preventDefault();error();
  try{await api('/api/login',{user:$('account').value,password:$('password').value});tenant=customer=selectedCase=scopeTenant='';currentPage=0;$('search').value='';$('bucket').value='';await load();}catch(e){error(e.message);}
});
$('customer-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const body={tenant:$('new-tenant').value,customer:$('new-id').value,name:$('new-name').value,scenario:$('new-scenario').value};
  await mutate(async()=>{await api('/api/customers',body);tenant=body.tenant;customer=body.customer;selectedCase='';scopeTenant='';currentPage=0;$('search').value='';$('bucket').value='';$('customer-form').reset();$('status').textContent='Cliente criado no sandbox, sem observações inventadas.';});
});
$('tenant').addEventListener('change',async event=>{scopeTenant=event.target.value;tenant=customer=selectedCase='';activeCase=null;currentPage=0;registry=[];$('content').replaceChildren();$('counts').replaceChildren();renderRegistry();error();try{await load();}catch(e){error(e.message);}});
for(const id of ['search','bucket']) $(id).addEventListener(id==='search'?'input':'change',()=>{currentPage=0;renderRegistry();});
$('previous').addEventListener('click',()=>{currentPage--;renderRegistry();});
$('next').addEventListener('click',()=>{currentPage++;renderRegistry();});
$('logout').addEventListener('click',async()=>{
  try{await api('/api/logout',{});++requestGeneration;tenant=customer=selectedCase=scopeTenant='';activeCase=null;registry=[];memberships=[];$('search').value='';$('bucket').value='';$('customer-form').reset();$('content').replaceChildren();$('registry-list').replaceChildren();$('workspace').hidden=true;$('login').hidden=false;$('status').textContent='';error();}catch(e){error(e.message);}
});
load().catch(e=>{if(!e.message.includes('Inicie sessão')) error(e.message);});
