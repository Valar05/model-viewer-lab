import assert from 'node:assert/strict';
import fs from 'node:fs';

const catalog = JSON.parse(fs.readFileSync(new URL('./free-stack.json', import.meta.url), 'utf8'));
assert.equal(catalog.schema, 'hard-surface-factory.free-blender-stack/1');
assert.equal(catalog.policy.cost, 'zero-license-fee');
assert.ok(Array.isArray(catalog.entries) && catalog.entries.length >= 9);

const ids = new Set();
for (const entry of catalog.entries) {
  assert.match(entry.id, /^[a-z0-9-]+$/);
  assert.ok(!ids.has(entry.id), `duplicate id: ${entry.id}`);
  ids.add(entry.id);
  assert.match(entry.source, /^https:\/\//);
  assert.ok(entry.license);
  assert.ok(['headless', 'interactive', 'interactive-adapter', 'adapter-with-native-fallback'].includes(entry.mode));
  assert.ok(Array.isArray(entry.verbs) && entry.verbs.length > 0);
  assert.ok(Array.isArray(entry.moduleProbes));
  assert.ok(Array.isArray(entry.operatorProbes));
  if (entry.headless === true) assert.equal(entry.mode, 'headless');
}

for (const required of ['retopoflow', 'polyquilt-fork', 'bsurfaces-gpl-edition', 'looptools', 'f2', 'auto-mirror', 'bool-tool', 'material-utilities', 'blender-native']) {
  assert.ok(ids.has(required), `missing governed entry: ${required}`);
}

process.stdout.write('free stack catalog: ok\n');
