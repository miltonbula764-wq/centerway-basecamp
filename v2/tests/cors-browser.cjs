// Browser transport test only: two HTTPS origins, no frontend product/UI.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const {mkdtempSync,rmSync,readFileSync}=require('node:fs');
const https=require('node:https'),net=require('node:net');
const path=require('node:path'),os=require('node:os');

(async()=>{
  const temp=mkdtempSync(path.join(os.tmpdir(),'cw-cors-')),cwd=path.resolve(__dirname,'..');
  const db=path.join(temp,'db.sqlite3'),credentials=path.join(temp,'credentials.json');
  const cert=path.join(temp,'cert.pem'),key=path.join(temp,'key.pem');
  let browser,backend,allowedFrontend,deniedFrontend;
  try {
    assert.equal(spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',key,'-out',cert,'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],{encoding:'utf8'}).status,0);
    async function emptyOrigin() {
      const server=https.createServer({key:readFileSync(key),cert:readFileSync(cert)},(_,res)=>{res.writeHead(200,{'Content-Type':'text/plain'});res.end('Local API transport test. No product frontend.');});
      await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
      return server;
    }
    allowedFrontend=await emptyOrigin();deniedFrontend=await emptyOrigin();
    const frontend=`https://127.0.0.1:${allowedFrontend.address().port}`;
    const forbidden=`https://127.0.0.1:${deniedFrontend.address().port}`;
    const port=await new Promise(resolve=>{const sock=net.createServer();sock.listen(0,'127.0.0.1',()=>{const port=sock.address().port;sock.close(()=>resolve(port));});});
    const api=`https://127.0.0.1:${port}`;
    const setup=spawnSync(process.env.PYTHON || 'python3',['-m','centerway.preview','init','--db',db,'--credentials-file',credentials,'--origin',api],{cwd,encoding:'utf8'});
    assert.equal(setup.status,0,setup.stderr);
    const passwords=JSON.parse(readFileSync(credentials,'utf8')).accounts;
    backend=spawn(process.env.PYTHON || 'python3',['-u','-m','centerway.preview','serve','--db',db,'--certfile',cert,'--keyfile',key,'--port',String(port),'--frontend-origin',frontend],{cwd});
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Private API startup timeout')),10000);
      backend.stdout.on('data',chunk=>{if(chunk.toString().includes('Servidor HTTPS privado iniciado')){clearTimeout(timer);resolve();}});
      backend.on('error',reject);backend.on('exit',code=>{if(code)reject(new Error('API exited '+code));});
    });
    browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
    // Disposable local certificate exception only; Python HTTPS tests validate TLS.
    const context=await browser.newContext({ignoreHTTPSErrors:true});
    const page=await context.newPage();await page.goto(frontend);
    assert.notEqual(new URL(api).origin,new URL(frontend).origin);
    async function call(route,body) {
      return page.evaluate(async({api,route,body})=>{
        const response=await fetch(api+route,{credentials:'include',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
        return {status:response.status,data:await response.json(),retry:response.headers.get('Retry-After'),version:response.headers.get('X-Centerway-API-Version')};
      },{api,route,body});
    }
    const anonymous=await call('/api/view');
    assert.equal(anonymous.status,401);assert.equal(anonymous.data.code,'unauthenticated');
    assert.equal(anonymous.version,'1.0.0');
    assert.equal((await call('/api/login',{user:'founder',password:passwords.founder})).status,200);
    assert.equal((await call('/api/view')).data.registry.length,150);
    // A second, non-allowlisted origin cannot read or log out this authenticated user.
    await page.goto(forbidden);
    const denied=await page.evaluate(async api=>{try{await fetch(api+'/api/logout',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:'{}'});return false;}catch{return true;}},api);
    assert.equal(denied,true);
    await page.goto(frontend);assert.equal((await call('/api/view')).status,200);
    assert.equal((await call('/api/logout',{})).status,200);
    assert.equal((await call('/api/view')).status,401);
    assert.equal((await call('/api/login',{user:'reader-private',password:passwords['reader-private']})).status,200);
    assert.equal((await call('/api/view')).data.registry.length,75);
    const other=await call('/api/view?tenant=atlas&customer=client-007');
    assert.equal(other.status,403);assert.equal(other.data.code,'forbidden');
    assert.equal((await call('/api/logout',{})).status,200);
    assert.equal((await call('/api/view')).status,401);
    console.log('PASS browser CORS: distinct local same-site HTTPS origins, native preflight, Strict cookie login/read/logout, readable JSON errors, denied origin cannot mutate session, tenant isolation. No Lovable, external hosting or real integration.');
  } finally {
    if(browser)await browser.close();
    if(backend){backend.kill('SIGTERM');await new Promise(resolve=>backend.exitCode!==null?resolve():backend.once('exit',resolve));}
    for(const server of [allowedFrontend,deniedFrontend])if(server)await new Promise(resolve=>server.close(resolve));
    rmSync(temp,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
