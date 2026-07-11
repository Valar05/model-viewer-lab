#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const required = [
  'dist/mechanism-viewer.html',
  'dist/assets/mechanism-viewer.js',
  'dist/assets/mechanism-viewer.css',
  'dist/labs/hard-surface-factory/mechanisms/tread-system-v1/mechanism.json'
];
const missing = required.filter((rel) => !fs.existsSync(path.join(root, rel)));
if (missing.length) {
  console.error('missing built mechanism files: ' + missing.join(', '));
  process.exit(1);
}
const mechanism = JSON.parse(fs.readFileSync(path.join(root, 'dist/labs/hard-surface-factory/mechanisms/tread-system-v1/mechanism.json'), 'utf8'));
const js = fs.readFileSync(path.join(root, 'dist/assets/mechanism-viewer.js'), 'utf8');
if (mechanism.id !== 'tread-system-v1') {
  console.error('unexpected mechanism id: ' + mechanism.id);
  process.exit(1);
}
for (const token of ['leftSpeed', 'rightSpeed', 'joystick', 'sampleBelt']) {
  if (!js.includes(token)) {
    console.error('mechanism bundle missing expected token: ' + token);
    process.exit(1);
  }
}
const url = new URL('http://127.0.0.1:8798/model-viewer-lab/dist/mechanism-viewer.html');
url.searchParams.set('mechanism', '/model-viewer-lab/dist/labs/hard-surface-factory/mechanisms/tread-system-v1/mechanism.json');
url.searchParams.set('title', mechanism.id);
console.log(JSON.stringify({ ok: true, url: url.toString() }, null, 2));
