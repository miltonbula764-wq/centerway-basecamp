import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';
if(process.env.CW_DEMO_BASE_URL !== 'https://demo.centerway.test:8443') throw Error('This configuration validates local test HTTPS only, never a remote Codespace.');
const spki=fs.readFileSync(new URL('./private/tls/spki.txt',import.meta.url),'utf8').trim();
export default defineConfig({
 testDir:'./tests', testMatch:['operational-journey.spec.mjs','demo-mobile.spec.mjs'],
 fullyParallel:false,workers:1,retries:0,timeout:60000,expect:{timeout:15000},
 reporter:[['list'],['html',{outputFolder:'report-demo',open:'never'}]], outputDir:'results-demo',
 use:{...devices['Pixel 7'],baseURL:process.env.CW_DEMO_BASE_URL,browserName:'chromium',
   trace:'off',video:'off',screenshot:'only-on-failure',
   launchOptions:{args:['--host-resolver-rules=MAP demo.centerway.test 127.0.0.1',`--ignore-certificate-errors-spki-list=${spki}`]},
 },
});
