// Optional QA dependency: npm ci in v2. Runtime remains Python stdlib only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdtempSync, rmSync, mkdirSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async () => {
  const temp = mkdtempSync(path.join(os.tmpdir(), 'centerway-browser-'));
  const server = spawn(process.env.PYTHON || 'python3', ['-u','-m','centerway.server','--db',path.join(temp,'browser.sqlite3'),'--port','0'], {cwd:path.resolve(__dirname,'..')});
  let browser;
  const errors = [];
  try {
    const url = await new Promise((resolve,reject) => {
      const timeout = setTimeout(()=>reject(new Error('Server startup timeout')),10000);
      server.stdout.on('data', chunk => { const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/); if(match) {clearTimeout(timeout);resolve(match[0]);} });
      server.on('error',reject);
      server.on('exit',code=>{if(code) reject(new Error('Server exited '+code));});
    });
    browser = await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {}),args:['--no-sandbox']});
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    async function login(account) {
      await page.goto(url);
      await page.selectOption('#account',account);
      await page.getByRole('button',{name:'Abrir laboratório'}).click();
      await page.locator('#workspace').waitFor({state:'visible'});
      await page.locator('#content h2').waitFor();
    }
    async function step(op, expectedStage) {
      await page.locator(`[data-op="${op}"]`).click();
      await page.waitForFunction(stage=>document.querySelector('[data-stage]')?.dataset.stage === stage,expectedStage);
      await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
      assert.equal(await page.locator('#error').isVisible(),false);
    }
    async function prepare() {
      for (const stage of ['observed','detected','investigated','decided']) await step('advance',stage);
    }
    await login('demo');
    await prepare();
    assert.match(await page.locator('#content').innerText(),/Simulador · sem IA real/);
    await step('execute','executed');
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/12 novos resultados/);
    await page.reload();
    await page.locator('[data-op="verify"]').waitFor();
    assert.match(await page.locator('#content').innerText(),/12 novos resultados/);
    for (const width of [360,390,1280]) {
      await page.setViewportSize({width,height:844});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true,'horizontal overflow at '+width);
    }
    await page.setViewportSize({width:390,height:844});
    mkdirSync(path.resolve(__dirname,'../test-results'),{recursive:true});
    await page.screenshot({path:path.resolve(__dirname,'../test-results/atlas-mobile.png'),fullPage:true});
    await page.selectOption('#tenant','nimbus');
    await page.getByRole('heading',{name:'NimbusDesk · Estúdio Norte'}).waitFor();
    assert.equal(await page.locator('#content').innerText().then(t=>t.includes('job-0')),false);
    await prepare();
    await step('execute','executed');
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/Ainda não confirmada/);
    assert.match(await page.locator('#content').innerText(),/0 novos resultados/);
    await page.locator('[data-op="simulate-usage"]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-op="simulate-usage"]'));
    await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    await step('verify','verified');
    assert.match(await page.locator('#content').innerText(),/4 novos resultados/);
    // A delayed response from the previous tenant cannot overwrite the active tenant.
    await page.route('**/api/view?tenant=atlas',async route=>{await new Promise(r=>setTimeout(r,250));await route.continue();});
    await page.selectOption('#tenant','atlas');
    await page.selectOption('#tenant','nimbus');
    await page.getByRole('heading',{name:'NimbusDesk · Estúdio Norte'}).waitFor();
    await page.waitForTimeout(400);
    assert.match(await page.locator('#content h2').innerText(),/NimbusDesk/);
    await page.unroute('**/api/view?tenant=atlas');
    await page.getByRole('button',{name:'Sair',exact:true}).click();
    await page.locator('#login').waitFor({state:'visible'});
    await login('leitor');
    assert.equal(await page.locator('[data-op]').count(),0);
    assert.equal(await page.locator('#tenant option').count(),1);
    const forbidden = await page.evaluate(async()=>{const r=await fetch('/api/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tenant:'nimbus',case_id:'any'})});return r.status;});
    assert.equal(forbidden,403);
    await page.getByRole('button',{name:'Sair',exact:true}).click();
    await page.locator('#login').waitFor({state:'visible'});
    await login('atlas');
    assert.equal(await page.locator('#tenant option').count(),1);
    assert.equal(await page.evaluate(async()=> (await fetch('/api/view?tenant=nimbus')).status),403);
    assert.deepEqual(errors,[]);
    console.log('PASS browser: both C01–C06 flows; reload persistence; 360/390/1280px; delayed tenant response; viewer; isolated operator; no JS errors.');
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
    rmSync(temp,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
