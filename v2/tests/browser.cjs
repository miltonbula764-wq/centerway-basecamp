// Browser QA uses a disposable 150-client sandbox; no external SaaS or AI.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn,spawnSync } = require('node:child_process');
const { mkdtempSync,rmSync,mkdirSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async()=>{
  const temp=mkdtempSync(path.join(os.tmpdir(),'centerway-browser-'));
  const cwd=path.resolve(__dirname,'..'),db=path.join(temp,'browser.sqlite3');
  const fixture=spawnSync(process.env.PYTHON || 'python3',['-m','centerway.synthetic','--db',db],{cwd,encoding:'utf8'});
  assert.equal(fixture.status,0,fixture.stderr);
  const server=spawn(process.env.PYTHON || 'python3',['-u','-m','centerway.server','--db',db,'--port','0'],{cwd});
  let browser;
  const errors=[];
  try {
    const url=await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('Server startup timeout')),10000);
      server.stdout.on('data',chunk=>{const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});
      server.on('error',reject);
      server.on('exit',code=>{if(code) reject(new Error('Server exited '+code));});
    });
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
    const page=await browser.newPage({viewport:{width:390,height:844}});
    page.on('pageerror',e=>errors.push(e.message));
    async function login(account) {
      await page.goto(url);
      await page.selectOption('#account',account);
      await page.getByRole('button',{name:'Abrir laboratório'}).click();
      await page.locator('#registry-list [data-open-customer]').first().waitFor();
    }
    async function open(tenant,customer) {
      await page.selectOption('#bucket','');
      await page.fill('#search',customer);
      await page.locator(`[data-open-tenant="${tenant}"][data-open-customer="${customer}"]`).click();
      await page.waitForFunction(({tenant,customer})=>document.querySelector('#content')?.textContent.includes(tenant+' · '+customer),{tenant:tenant==='atlas'?'AtlasFlow':'NimbusDesk',customer});
    }
    async function step(op,stage,extra='') {
      await page.locator(`[data-op="${op}"]${extra}`).click();
      await page.waitForFunction(stage=>document.querySelector('[data-stage]')?.dataset.stage===stage,stage);
      await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
      assert.equal(await page.locator('#error').isVisible(),false);
    }
    await login('demo');
    assert.match(await page.locator('#registry-total').innerText(),/150 clientes/);
    for(const [bucket,count] of [['deterioration',16],['investigation',14],['intervention',35],['recovery',23],['exceptions',32]]) {
      await page.selectOption('#bucket',bucket);
      assert.match(await page.locator('#registry-total').innerText(),new RegExp(`${count} clientes`));
    }
    await page.selectOption('#bucket','');
    await page.getByRole('button',{name:'Seguinte',exact:true}).click();
    assert.match(await page.locator('#registry-total').innerText(),/página 2/);
    for(const width of [360,390,1280]) {
      await page.setViewportSize({width,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'registry overflow at '+width);
    }
    await page.setViewportSize({width:390,height:844});
    await page.fill('#search','');
    await page.getByRole('button',{name:'Anterior',exact:true}).click();
    mkdirSync(path.join(cwd,'test-results'),{recursive:true});
    await page.screenshot({path:path.join(cwd,'test-results/registry-mobile.png'),fullPage:true});
    // Independent clients, same ID in two different SaaS, actual persisted sandbox effects.
    await open('atlas','client-007');
    await step('execute','executed');
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/12 novos resultados/);
    await page.reload();
    await page.locator('#registry-list [data-open-customer]').first().waitFor();
    await open('atlas','client-007');
    assert.match(await page.locator('#content').innerText(),/12 novos resultados/);
    await open('nimbus','client-007');
    await step('execute','executed');
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/Ainda não confirmada/);
    await page.locator('[data-op="simulate-usage"]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-op="simulate-usage"]'));
    await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/4 novos resultados/);
    // New registration and valid observation entry through the real UI, not fixtures.
    await page.getByText('Registar cliente no sandbox',{exact:true}).click();
    await page.selectOption('#new-tenant','atlas');
    await page.fill('#new-id','browser-new');
    await page.fill('#new-name','Novo cliente navegador');
    await page.getByRole('button',{name:'Registar cliente',exact:true}).click();
    await page.getByRole('heading',{name:'Novo cliente navegador'}).waitFor();
    await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    await step('advance','observed');
    await step('advance','insufficient_data');
    await page.fill('#observations','2026-01-01,-1,manual-sandbox');
    await page.getByRole('button',{name:'Validar e gravar lote'}).click();
    await page.locator('#error').waitFor({state:'visible'});
    await page.getByRole('button',{name:'Preencher exemplo simulado'}).click();
    await page.getByRole('button',{name:'Validar e gravar lote'}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('14 observações inseridas'));
    await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    for(const stage of ['observed','detected','investigated','decided']) await step('advance',stage);
    await step('execute','executed');
    await step('verify','verified');
    const latest=await page.inputValue('#case-select');
    const old=await page.locator('#case-select option').last().getAttribute('value');
    assert.notEqual(latest,old);
    await page.selectOption('#case-select',old);
    await page.waitForFunction(()=>document.querySelector('[data-stage]')?.dataset.stage==='insufficient_data');
    assert.equal(await page.locator('[data-op]').count(),0);
    await page.selectOption('#case-select',latest);
    await page.locator('[data-op="verify"]').waitFor();
    // Replayed batch must not create a new cycle or duplicate observations.
    await page.getByRole('button',{name:'Preencher exemplo simulado'}).click();
    await page.getByRole('button',{name:'Validar e gravar lote'}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Lote já registado'));
    await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    assert.equal(await page.locator('#case-select option').count(),2);
    // A late response cannot overwrite another selected customer.
    await page.route('**/api/view?tenant=atlas&customer=client-006',async route=>{await new Promise(r=>setTimeout(r,250));await route.continue();});
    await page.fill('#search','client-0');
    await page.locator('[data-open-tenant="atlas"][data-open-customer="client-006"]').click();
    await page.locator('[data-open-tenant="atlas"][data-open-customer="client-016"]').click();
    await page.waitForFunction(()=>document.querySelector('#content')?.textContent.includes('AtlasFlow · client-016'));
    await page.waitForTimeout(400);
    assert.match(await page.locator('#content').innerText(),/AtlasFlow · client-016/);
    await page.unroute('**/api/view?tenant=atlas&customer=client-006');
    await page.getByRole('button',{name:'Sair',exact:true}).click();
    await page.locator('#login').waitFor({state:'visible'});
    await login('leitor');
    assert.match(await page.locator('#registry-total').innerText(),/75 clientes/);
    assert.equal(await page.locator('[data-open-tenant="atlas"]').count(),0);
    assert.equal(await page.locator('#new-customer').isVisible(),false);
    await open('nimbus','client-007');
    assert.equal(await page.locator('[data-op]').count(),0);
    assert.equal(await page.locator('#observation-form').count(),0);
    assert.equal(await page.evaluate(async()=> (await fetch('/api/view?tenant=atlas&customer=client-007')).status),403);
    await page.getByRole('button',{name:'Sair',exact:true}).click();
    await page.locator('#login').waitFor({state:'visible'});
    await login('atlas');
    assert.match(await page.locator('#registry-total').innerText(),/76 clientes/);
    assert.equal(await page.locator('[data-open-tenant="nimbus"]').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS browser: 150-client registry, filters, pagination, 360/390/1280px, two independent SaaS cycles, registration, invalid/valid/replayed ingestion, historical cycle, reload persistence, delayed customer response, reader/operator isolation, no JS errors.');
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
    rmSync(temp,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
