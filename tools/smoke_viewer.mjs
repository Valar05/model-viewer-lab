#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { pathToWorkspaceUrl, viewerPathForDist } from './path_utils.mjs';

const root = process.cwd();
const outlawModels = {
  'dist/models/outlaw/Outlaw_Complete_WideTires_CLEAN.glb': {
    bytes: 65832,
    sha256: '468d50db3157045fbfa016a71509ade836ec5833aa4abeb892864637546065e1'
  },
  'dist/models/outlaw/Outlaw_Complete_Clearance_CLEAN.glb': {
    bytes: 78692,
    sha256: '6fc17cd21524fef4d3756afc9e01a8a88b840c1ab9a54f2a6a44ef7f755786cb'
  }
};
const required = [
  'dist/model-viewer.html',
  'dist/assets/model-viewer.js',
  'dist/assets/model-viewer.css',
  ...Object.keys(outlawModels)
];
const missing = required.filter((rel) => !fs.existsSync(path.join(root, rel)));
const bundleSource = fs.existsSync(path.join(root, 'dist/assets/model-viewer.js')) ? fs.readFileSync(path.join(root, 'dist/assets/model-viewer.js'), 'utf8') : '';
for (const marker of ['animationNames','activeAnimation','AnimationMixer','hierarchy']) {
  if (!bundleSource.includes(marker)) {
    console.error('missing animation/hierarchy contract: ' + marker);
    process.exit(1);
  }
}
if (missing.length) {
  console.error('missing built files: ' + missing.join(', '));
  process.exit(1);
}
for (const [rel, expected] of Object.entries(outlawModels)) {
  const bytes = fs.readFileSync(path.join(root, rel));
  const actual = createHash('sha256').update(bytes).digest('hex');
  if (bytes.length !== expected.bytes || actual !== expected.sha256 || bytes.subarray(0, 4).toString('ascii') !== 'glTF') {
    console.error('invalid Outlaw review model: ' + rel);
    process.exit(1);
  }
}

const html = fs.readFileSync(path.join(root, 'dist/model-viewer.html'), 'utf8');
for (const marker of ['Outlaw Before Clearance', 'Outlaw After Clearance', 'preset']) {
  if (!html.includes(marker)) {
    console.error('missing Outlaw selector contract: ' + marker);
    process.exit(1);
  }
}

const portableState = 'docs/examples/review-state-v2.json';
if (process.env.MODEL_VIEWER_REQUIRE_LOCAL_ARTIFACTS !== '1') {
  if (!fs.existsSync(path.join(root, portableState))) {
    console.error('missing portable review-state fixture: ' + portableState);
    process.exit(1);
  }
  const stateUrl = new URL('http://127.0.0.1:8798' + viewerPathForDist());
  stateUrl.searchParams.set('state', '/model-viewer-lab/' + portableState);
  stateUrl.searchParams.set('title', 'portable-review-state');
  console.log(JSON.stringify({
    ok: true,
    mode: 'portable',
    url: stateUrl.toString(),
    outlawPresets: ['outlaw-before', 'outlaw-after']
  }, null, 2));
  process.exit(0);
}

const kitGlb = '/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories/archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_chassis_kit_scratch_v1/real_sherman_chassis_kit_scratch_v1.glb';
const kitManifest = '/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories/archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_chassis_kit_scratch_v1/model_manifest.json';
for (const file of [kitGlb, kitManifest]) {
  if (!fs.existsSync(file)) {
    console.error('missing current kit artifact: ' + file);
    process.exit(1);
  }
}
const url = new URL('http://127.0.0.1:8798' + viewerPathForDist());
url.searchParams.set('src', pathToWorkspaceUrl(kitGlb));
url.searchParams.set('manifest', pathToWorkspaceUrl(kitManifest));
url.searchParams.set('title', 'real_sherman_chassis_kit_scratch_v1');
console.log(JSON.stringify({ ok: true, url: url.toString() }, null, 2));
