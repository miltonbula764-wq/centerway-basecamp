/** Opt-in remote acceptance; never runs with fixtures or committed credentials. */
import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { HttpTransport } from '@/data/http-transport';
import { API_ORIGIN, LiveRuntime } from '@/data/live-runtime';
const credentialsPath=process.env['CW_SYNTHETIC_CREDENTIALS_FILE'];
it.skipIf(!credentialsPath)('actual UI transport/controller maps public F01–F06, enforces permissions and logs out',async()=>{
 const credentials:Record<string,string>={}; let user='';
 for(const line of readFileSync(credentialsPath!,'utf8').split(/\r?\n/)) {
  if(line.startsWith('Utilizador:'))user=line.split(':').slice(1).join(':').trim();
  if(line.startsWith('Palavra-passe:'))credentials[user]=line.split(':').slice(1).join(':').trim();
 }
 const evidence:{method:string;path:string;status:number}[]=[];
 let offline=false,clock=Date.now();
 const transport=new HttpTransport({baseUrl:API_ORIGIN,now:()=>clock,fetch:async(url,init)=>{
  if(offline)throw new TypeError('synthetic client offline test');
  const response=await fetch(url,{...init,headers:{...init.headers,Origin:'https://value-recovery-radar.lovable.app'},signal:AbortSignal.timeout(90000)});
  evidence.push({method:init.method??'GET',path:new URL(url).pathname,status:response.status});
  expect(response.headers.get('access-control-allow-origin')).toBe('https://value-recovery-radar.lovable.app');
  return response;
 }});
 const runtime=new LiveRuntime(transport,()=>clock);
 try {
  await runtime.login('alice',credentials['alice']!);
  const views=await runtime.customers();expect(views.length).toBeGreaterThan(0);
  const view=views[0]!;
  expect(view.demo).toBeNull();expect(view.displayName).toMatch(/synthetic/i);
  expect(view.contracts.length).toBeGreaterThan(0);
  expect(view.contracts.flatMap(c=>c.detections).length).toBeGreaterThan(0);
  expect(view.investigations.length).toBeGreaterThan(0);
  expect(view.decisions.length).toBeGreaterThan(0);
  expect(view.recoveries.length).toBeGreaterThan(0);
  expect(view.receipts.length).toBeGreaterThan(0);
  expect(view.causalAttribution).toBe('not_established');
  const denied=transport.getJourney('b1000000-0000-0000-0000-000000000001','b2000000-0000-0000-0000-000000000001');
  await expect(denied).rejects.toMatchObject({status:403});
  offline=true;
  await expect(runtime.refresh()).rejects.toMatchObject({kind:'network'});
  expect(runtime.getSnapshot().customers).toEqual([]);
  offline=false;await runtime.refresh();expect((await runtime.customers())[0]!.id).toBe(view.id);
  await runtime.logout();expect(runtime.getSnapshot().auth.session).toBeNull();expect(runtime.getSnapshot().customers).toEqual([]);
  await expect(transport.getSession()).rejects.toMatchObject({status:401});
  await runtime.login('reader',credentials['reader']!);
  expect(runtime.controller.canAttempt('intervene')).toBe(false);
  const readerView=(await runtime.customers())[0]!;
  await expect(runtime.prepare(readerView.id,{request_id:crypto.randomUUID(),operation:'intervene',arguments:{investigation_id:'00000000-0000-4000-8000-000000000001',report_id:'00000000-0000-4000-8000-000000000002'}})).rejects.toMatchObject({status:403});
  expect(evidence.filter(e=>e.path.endsWith('/operations'))).toEqual([]);
  clock+=901000;runtime.checkExpiry();expect(runtime.getSnapshot().auth.status).toBe('expired');expect(runtime.getSnapshot().customers).toEqual([]);
  // Explicitly revoke the server token even after the controller clock has expired.
  // Transport.deleteSession clears memory before attempting revocation; no retries.
  clock-=901000;await transport.deleteSession();
  console.info('PUBLIC_ACCEPTANCE_SANITIZED',JSON.stringify({checks:['login','directory','F01','F02','F03','F04','F05','F06','tenant_denial','offline_error','recovery_after_network','logout','reader_permissions','no_automatic_writes','local_expiration'],requests:evidence}));
 } finally {offline=false;clock=Date.now();await runtime.logout();await transport.deleteSession();}
},240000);
