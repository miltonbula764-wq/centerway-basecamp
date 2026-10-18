// Isolated demo only. Production/Lovable configuration and client remain unchanged.
import { defineConfig, mergeConfig } from 'vite';
import base from '../../vite.config';

export default defineConfig(async env => {
  const origin = process.env['CW_DEMO_ORIGIN'];
  if (!origin) throw new Error('Demo origin must be supplied by scripts/demo/manage.py');
  const url = new URL(origin);
  return mergeConfig(typeof base === 'function' ? await base(env) : await base, {
    server: {
      host: '127.0.0.1', port: 8080, strictPort: true,
      allowedHosts: [url.hostname],
      fs: { strict: true, deny: ['.env', '.env.*', '*.{crt,pem,key}', '**/.git/**', '**/e2e/private/**', '**/e2e/*fixtures.json', '**/scripts/**', '**/drizzle/**'] },
      hmr: { host: url.hostname, protocol: url.protocol === 'https:' ? 'wss' : 'ws', clientPort: Number(url.port) || (url.protocol === 'https:' ? 443 : 80) },
      proxy: {
        '/auth/v1': { target: 'http://127.0.0.1:54321', changeOrigin: false },
        '/rest/v1': { target: 'http://127.0.0.1:54321', changeOrigin: false },
      },
    },
  });
});
