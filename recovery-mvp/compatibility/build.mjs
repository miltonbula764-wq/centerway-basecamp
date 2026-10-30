// Test-only mirror of the actual Lovable transport. Never imported by the API.
import { stripTypeScriptTypes } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(readFileSync(path.join(root, 'frontend/manifest.json')));
const out = process.argv[2];
if (!out) throw new Error('Supply a temporary output directory');
mkdirSync(out, { recursive: true });
for (const [name, hash] of Object.entries(manifest.files)) {
  const source = readFileSync(path.join(root, 'frontend', name), 'utf8');
  if (createHash('sha256').update(source).digest('hex') !== hash)
    throw new Error(`Source mirror drift: ${name}`);
  const js = stripTypeScriptTypes(source, { mode: 'transform' })
    .replace(/(from\s+["']\.\/[^"']+)(["'])/g, '$1.js$2');
  writeFileSync(path.join(out, name.replace(/\.ts$/, '.js')), js);
}
