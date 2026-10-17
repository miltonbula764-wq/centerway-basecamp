import { defineConfig, mergeConfig } from 'vite';
import base from '../vite.config';

// Test-only read observer: no auth changes, no replacement components or request behavior.
// Production vite.config.ts never imports this plugin.
export default defineConfig(async (env) => {
  const config = typeof base === 'function' ? await base(env) : await base;
  return mergeConfig(config, {
    plugins: [{
      name: 'cw-e2e-read-query-state',
      enforce: 'pre',
      transform(code, id) {
        if (!id.split('?')[0]?.endsWith('/src/router.tsx')) return;
        const anchor = 'const queryClient = new QueryClient();';
        if (!code.includes(anchor)) throw new Error('E2E QueryClient observer anchor changed');
        return code.replace(anchor, `${anchor}
          if (typeof window !== 'undefined') {
            const events = [];
            queryClient.getMutationCache().subscribe((event) => {
              if (!event.mutation) return;
              const m = event.mutation;
              const v = m.state.variables;
              events.push({ id: m.mutationId, status: m.state.status,
                tenant: v?.tenantId, subject: v?.subjectId, run: v?.runId });
            });
            Object.defineProperty(window, '__CW_E2E_STATE__', { configurable: true, value: () => ({
              keys: queryClient.getQueryCache().getAll().map(q => q.queryKey),
              events: events.map(e => ({...e}))
            }) });
          }
        `);
      },
    }],
  });
});
