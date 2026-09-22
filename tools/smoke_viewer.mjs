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
  },
  'dist/models/outlaw/Outlaw_Factory_Base_WideTires_CLEAN.glb': {
    bytes: 59076,
    sha256: 'ae1c1f3aabfc1ad261aa5a0853b85bc1505969f83ef929eb1a654714bbc044f1'
  },
  'dist/models/outlaw/Outlaw_Complete_WideTires_TEXTURED.glb': {
    bytes: 71924,
    sha256: 'ed49c6b37ddbb99b9a2fc64afb6deca8ea923e09a377617c02eccba90316ac80'
  },
  'dist/models/outlaw/Outlaw_Complete_Clearance_TEXTURED.glb': {
    bytes: 88588,
    sha256: 'bb0a48eb60e0a8b1db9a0dc42be4e9d7cef0173ca54fb9bcdd1c46326f6cf7ef'
  },
  'dist/models/outlaw/Outlaw_Factory_Base_WideTires_TEXTURED.glb': {
    bytes: 65612,
    sha256: 'c1ce0e45da7b9dbbeb772c2fbe5b54feb50d3dc9ba71c1981b06e7e87b35cdcc'
  }
};
const texturedOutlawModels = [
  'dist/models/outlaw/Outlaw_Complete_WideTires_TEXTURED.glb',
  'dist/models/outlaw/Outlaw_Complete_Clearance_TEXTURED.glb',
  'dist/models/outlaw/Outlaw_Factory_Base_WideTires_TEXTURED.glb'
];
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

function readGlbJson(bytes) {
  const jsonLength = bytes.readUInt32LE(12);
  const jsonType = bytes.readUInt32LE(16);
  if (jsonType !== 0x4e4f534a) throw new Error('GLB JSON chunk missing');
  return JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').replace(/[\u0000 ]+$/g, ''));
}
const requiredSemanticMaterials = [
  'TT_Main_Ivory',
  'TT_Industrial_Yellow',
  'TT_Graphite',
  'TT_Rubber',
  'TT_Pressure_Glass',
  'TT_Cool_Metal',
  'TT_Service_Orange',
  'TT_Headlamp',
  'TT_TailLamp',
  'TT_Indicator_Amber'
];
for (const rel of texturedOutlawModels) {
  const gltf = readGlbJson(fs.readFileSync(path.join(root, rel)));
  const names = new Set((gltf.materials || []).map((material) => material.name));
  for (const requiredName of requiredSemanticMaterials) {
    if (!names.has(requiredName)) {
      console.error('missing semantic Outlaw material ' + requiredName + ' in ' + rel);
      process.exit(1);
    }
  }
  const body = (gltf.meshes || []).find((mesh) => mesh.name === 'body_shell');
  if (!body || body.primitives.length < 6 || gltf.asset?.extras?.outlawSemanticAlbedo !== 'v1') {
    console.error('semantic Outlaw body split missing in ' + rel);
    process.exit(1);
  }
}

const html = fs.readFileSync(path.join(root, 'dist/model-viewer.html'), 'utf8');
for (const marker of ['Outlaw Before Clearance — Textured', 'Outlaw After Clearance — Textured', 'outlaw-before-textured', 'outlaw-after-textured', 'viewAxes']) {
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
    outlawPresets: ['outlaw-before-textured', 'outlaw-after-textured', 'outlaw-before', 'outlaw-after']
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
