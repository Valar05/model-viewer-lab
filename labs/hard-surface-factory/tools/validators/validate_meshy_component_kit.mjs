#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const sourceRel = 'labs/hard-surface-factory/source-assets/meshy-component-kit-071716';
const outRel = 'labs/hard-surface-factory/generated/meshy-component-kit-positioning-study';
const reviewRel = 'labs/hard-surface-factory/review-states';
const sourceDir = path.join(root, sourceRel);
const outDir = path.join(root, outRel);
const expectedComponents = ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac', 'canteen_lid'];
const expectedFiles = ['tank_hull.glb', 'tank_turret_housing.glb', 'tank_gun_barrel.glb', 'perforated_barrel_mac.glb', 'canteen_lid.glb'];

function fail(message) { console.error('[meshy-component-kit] ' + message); process.exitCode = 1; }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function readGlbHeader(file) {
  const data = fs.readFileSync(file);
  if (data.length < 20) return { ok: false, reason: 'too small' };
  return { ok: data.readUInt32LE(0) === 0x46546c67 && data.readUInt32LE(4) === 2, bytes: data.length };
}
for (const file of expectedFiles) {
  const full = path.join(sourceDir, file);
  if (!fs.existsSync(full)) fail('missing source GLB: ' + file);
  else if (!readGlbHeader(full).ok) fail('invalid source GLB: ' + file);
}
for (const file of ['kit_manifest.json', 'PROVENANCE.md']) if (!fs.existsSync(path.join(sourceDir, file))) fail('missing source metadata: ' + file);
for (const file of ['meshy_component_kit_positioning_study.glb', 'model_manifest.json', 'review-state.json']) if (!fs.existsSync(path.join(outDir, file))) fail('missing positioning-study artifact: ' + file);
if (fs.existsSync(path.join(outDir, 'meshy_component_kit_positioning_study.glb')) && !readGlbHeader(path.join(outDir, 'meshy_component_kit_positioning_study.glb')).ok) fail('invalid positioning-study GLB');
if (!process.exitCode) {
  const manifest = readJson(path.join(sourceDir, 'kit_manifest.json'));
  if (manifest.type !== 'meshy-reference-component-kit') fail('kit manifest type mismatch');
  if (manifest.sourcePolicy?.productionTopology !== false) fail('kit must not claim production topology');
  if (manifest.sourcePolicy?.finalAuthoredGeometry !== false) fail('kit must not claim final authored geometry');
  if (manifest.components?.length !== expectedComponents.length) fail('unexpected component count');
  for (const id of expectedComponents) {
    const component = manifest.components?.find((entry) => entry.id === id);
    if (!component) fail('missing manifest component: ' + id);
    if (!component.bounds?.dimensions || component.bounds.dimensions.some((value) => !(value > 0))) fail('invalid bounds for ' + id);
    if (!(component.embeddedImageCount >= 1)) fail('expected embedded textures for ' + id);
    if (id === 'canteen_lid' && component.category !== 'quarantined_hatch_candidate') fail('canteen_lid must stay quarantined');
  }
  const modelManifest = readJson(path.join(outDir, 'model_manifest.json'));
  if (modelManifest.claim?.includes('not authored topology') !== true) fail('positioning study must avoid authored-topology claim');
  const assemblyState = readJson(path.join(outDir, 'review-state.json'));
  if (assemblyState.version !== 2) fail('assembly review state must be version 2');
  if (assemblyState.parts?.length !== expectedComponents.length) fail('assembly review state must list all components');
  const canteen = assemblyState.parts.find((part) => part.id === 'canteen_lid');
  if (!canteen || canteen.visible !== false) fail('canteen_lid must be hidden by default');
  for (const id of expectedComponents) {
    const reviewPath = path.join(root, reviewRel, 'meshy-component-kit-' + id + '.json');
    if (!fs.existsSync(reviewPath)) fail('missing component review state: ' + id);
    else {
      const state = readJson(reviewPath);
      if (state.version !== 2) fail('component review state must be version 2: ' + id);
      if (!state.src?.startsWith('https://raw.githubusercontent.com/Valar05/model-viewer-lab/')) fail('component review state must use raw GitHub URL: ' + id);
    }
  }
}
if (!process.exitCode) console.log('[meshy-component-kit] ok: 5 source GLBs, manifest, review states, and positioning study valid');

