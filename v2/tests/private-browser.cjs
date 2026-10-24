// HTTPS with an ephemeral local test certificate; never an external deployment.
const { chromium,devices }=require('playwright');
const assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const {mkdtempSync,rmSync,readFileSync,mkdirSync}=require('node:fs');
const {createServer}=require('node:net');
const path=require('node:path');
const os=require('node:os');

(async()=>{
  const temp=mkdtempSync(path.join(os.tmpdir(),'cw-private-browser-'));
  const cwd=path.resolve(__dirname,'..');
  const db=path.join(temp,'preview.sqlite3'),credentials=path.join(temp,'credentials.json');
  const cert=path.join(temp,'test-cert.pem'),key=path.join(temp,'test-key.pem');
  let browser,server;
  try {
    const port=await new Promise(resolve=>{const socket=createServer();socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;socket.close(()=>resolve(port));});});
    const origin=`https://127.0.0.1:${port}`;
    const tls=spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',key,'-out',cert,'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],{encoding:'utf8'});
    assert.equal(tls.status,0,'test TLS certificate creation');
    const setup=spawnSync(process.env.PYTHON || 'python3',['-m','centerway.preview','init','--db',db,'--credentials-file',credentials,'--origin',origin],{cwd,encoding:'utf8'});
    assert.equal(setup.status,0,setup.stderr);
    const passwords=JSON.parse(readFileSync(credentials,'utf8')).accounts;
    server=spawn(process.env.PYTHON || 'python3',['-u','-m','centerway.preview','serve','--db',db,'--certfile',cert,'--keyfile',key,'--port',String(port)],{cwd});
    await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('HTTPS startup timeout')),10000);
      server.stdout.on('data',chunk=>{if(chunk.toString().includes('Servidor HTTPS privado iniciado')){clearTimeout(timeout);resolve();}});
      server.on('error',reject);
      server.on('exit',code=>{if(code)reject(new Error('Private server exited '+code));});
    });
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
    // Only the disposable local certificate is untrusted. Python tests validate the
    // same TLS path using an explicit CA, with verification enabled.
    const context=await browser.newContext({...devices['Pixel 7'],ignoreHTTPSErrors:true});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(origin);
    assert.equal(await page.locator('#account').getAttribute('autocomplete'),'username');
    assert.equal(await page.inputValue('#password'),'');
    assert.equal(await page.content().then(html=>html.includes('centerway-local')),false);
    assert.equal(await page.evaluate(async()=>(await fetch('/api/view')).status),401);
    await page.fill('#account','demo');await page.fill('#password','centerway-local');
    await page.getByRole('button',{name:'Entrar',exact:false}).click();
    await page.locator('#error').waitFor({state:'visible'});
    await page.fill('#account','founder');await page.fill('#password',passwords.founder);
    await page.getByRole('button',{name:'Entrar',exact:false}).click();
    await page.locator('#registry-list [data-open-customer]').first().waitFor();
    assert.match(await page.locator('#registry-total').innerText(),/150 clientes/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.selectOption('#bucket','exceptions');
    assert.match(await page.locator('#registry-total').innerText(),/32 clientes/);
    await page.selectOption('#bucket','');await page.fill('#search','client-010');
    await page.locator('[data-open-tenant="atlas"][data-open-customer="client-010"]').click();
    await page.locator('#content h2').waitFor();
    for(const stage of ['observed','detected','investigated','decided','executed','verified']) {
      const op=stage==='executed'?'execute':stage==='verified'?'verify':'advance';
      await page.locator(`[data-op="${op}"]`).click();
      await page.waitForFunction(stage=>document.querySelector('[data-stage]')?.dataset.stage===stage,stage);
      await page.waitForFunction(()=>!document.querySelector('#tenant').disabled);
    }
    assert.match(await page.locator('#content').innerText(),/12 novos resultados/);
    const cookie=(await context.cookies()).find(cookie=>cookie.name==='__Host-cw_session');
    assert.ok(cookie && cookie.secure && cookie.httpOnly && cookie.sameSite==='Strict');
    mkdirSync(path.join(cwd,'test-results'),{recursive:true});
    await page.screenshot({path:path.join(cwd,'test-results/private-android-emulated.png'),fullPage:true});
    await page.getByRole('button',{name:'Sair',exact:true}).click();await page.locator('#login').waitFor({state:'visible'});
    assert.equal(await page.evaluate(async()=>(await fetch('/api/view')).status),401);
    await page.fill('#account','reader-private');await page.fill('#password',passwords['reader-private']);
    await page.getByRole('button',{name:'Entrar',exact:false}).click();
    await page.locator('#registry-list [data-open-customer]').first().waitFor();
    assert.match(await page.locator('#registry-total').innerText(),/75 clientes/);
    assert.equal(await page.locator('[data-open-tenant="atlas"]').count(),0);
    assert.equal(await page.evaluate(async()=>(await fetch('/api/view?tenant=atlas&customer=client-010')).status),403);
    assert.deepEqual(errors,[]);
    console.log('PASS private HTTPS browser: emulated Pixel 7, no public credential form, public login refused, private login, 150-client filters, C01–C06 sandbox flow, Secure cookie, logout and reader isolation. Local test certificate only; no public URL or physical Android validation.');
  } finally {
    if(browser)await browser.close();
    if(server){server.kill('SIGTERM');await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));}
    rmSync(temp,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
