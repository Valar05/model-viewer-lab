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
function readGlbJson(file) {
  const data = fs.readFileSync(file);
  let offset = 12;
  while (offset < data.length) {
    const length = data.readUInt32LE(offset);
    const type = data.readUInt32LE(offset + 4);
    offset += 8;
    const chunk = data.subarray(offset, offset + length);
    offset += length;
    if (type === 0x4e4f534a) return JSON.parse(chunk.toString('utf8').trim());
  }
  throw new Error('missing GLB JSON: ' + file);
}

function nodeMeshBounds(glbJson) {
  const bounds = {};
  function meshBounds(meshIndex) {
    const mesh = glbJson.meshes?.[meshIndex];
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const primitive of mesh?.primitives || []) {
      const accessorIndex = primitive.attributes?.POSITION;
      const accessor = glbJson.accessors?.[accessorIndex];
      if (!accessor?.min || !accessor?.max) continue;
      for (let axis = 0; axis < 3; axis++) {
        min[axis] = Math.min(min[axis], accessor.min[axis]);
        max[axis] = Math.max(max[axis], accessor.max[axis]);
      }
    }
    if (min[0] === Infinity) return null;
    return { min, max, dim: max.map((value, axis) => value - min[axis]), center: max.map((value, axis) => (value + min[axis]) / 2) };
  }
  for (const node of glbJson.nodes || []) {
    if (node.mesh !== undefined && node.name) bounds[node.name] = meshBounds(node.mesh);
  }
  return bounds;
}
function closeEnough(actual, expected, tolerance = 0.0001) { return Math.abs(actual - expected) <= tolerance; }
function vectorClose(actual, expected, tolerance = 0.0001) {
  return Array.isArray(actual) && actual.length === expected.length && actual.every((value, index) => closeEnough(value, expected[index], tolerance));
}
function transformFor(modelManifest, id) { return modelManifest.parts?.find((part) => part.id === id)?.originalTransform; }
for (const file of expectedFiles) {
  const full = path.join(sourceDir, file);
  if (!fs.existsSync(full)) fail('missing source GLB: ' + file);
  else if (!readGlbHeader(full).ok) fail('invalid source GLB: ' + file);
}
for (const file of ['kit_manifest.json', 'PROVENANCE.md']) if (!fs.existsSync(path.join(sourceDir, file))) fail('missing source metadata: ' + file);
for (const file of ['meshy_component_kit_positioning_study.glb', 'model_manifest.json', 'review-state.json', 'red-build-evidence.json']) if (!fs.existsSync(path.join(outDir, file))) fail('missing positioning-study artifact: ' + file);
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
  if (modelManifest.type !== 'visible-tank-positioning-study') fail('positioning study must be the visible tank assembly variant');
  for (const id of ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac']) {
    if (!modelManifest.visibleAssemblyRequiredParts?.includes(id)) fail('visible assembly missing required part claim: ' + id);
  }
  if (!modelManifest.quarantinedSourceOnlyParts?.includes('canteen_lid')) fail('canteen_lid must be source-only in the visible assembly');
  const redEvidence = readJson(path.join(outDir, 'red-build-evidence.json'));
  if (redEvidence.actualVisibleRead?.includes('mantlet/front detail on the opposite side') !== true) fail('red-build evidence must record the orientation and seating visual failure');
  if (redEvidence.capturePath?.endsWith('Screenshot_20260717-130121.png') !== true) fail('red-build evidence must point at the corrected user screenshot candidate');
  const contract = modelManifest.relationshipContracts || {};
  if (JSON.stringify(contract.tankForwardAxis) !== JSON.stringify([0, 0, -1])) fail('assembly contract must declare tank-forward -Z');
  if (contract.turretMantletSharesGunAxis !== true) fail('assembly contract must require turret mantlet to share gun axis');
  if (contract.coaxialMgSharesGunAxis !== true) fail('assembly contract must require coaxial MG to share gun axis');
  if (contract.turretMustBeSeatedOnHull !== true) fail('assembly contract must require turret seating');
  if (contract.barrelMustOverlapTurretFront !== true) fail('assembly contract must require barrel/turret front overlap');
  const turretTransform = transformFor(modelManifest, 'tank_turret_housing');
  const gunTransform = transformFor(modelManifest, 'tank_gun_barrel');
  const mgTransform = transformFor(modelManifest, 'perforated_barrel_mac');
  if (!vectorClose(turretTransform?.rotationDeg, [0, 180, 0])) fail('turret must be rotated 180 degrees so mantlet/front detail faces the gun axis');
  if (!vectorClose(gunTransform?.rotationDeg, [0, 90, 0])) fail('main gun must rotate onto tank-forward -Z');
  if (!vectorClose(mgTransform?.rotationDeg, [0, -90, 0])) fail('MG must be flipped relative to the previous backwards orientation');
  if (!(turretTransform?.scale?.[0] <= 0.39)) fail('turret scale must be reduced from the red-build oversized setting');
  const assemblyJson = readGlbJson(path.join(outDir, 'meshy_component_kit_positioning_study.glb'));
  const sceneNodes = new Set((assemblyJson.scenes?.[assemblyJson.scene || 0]?.nodes || []).map((index) => assemblyJson.nodes?.[index]?.name));
  for (const id of ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac']) {
    if (!sceneNodes.has(id)) fail('visible assembly GLB scene missing node: ' + id);
  }
  if (sceneNodes.has('canteen_lid')) fail('canteen_lid must not be in the default visible tank assembly GLB scene');
  const bounds = nodeMeshBounds(assemblyJson);
  for (const id of ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac']) {
    if (!bounds[id]) fail('missing measured GLB bounds for: ' + id);
  }
  if (bounds.tank_hull && bounds.tank_turret_housing) {
    const hullTop = bounds.tank_hull.max[1];
    const turretBottom = bounds.tank_turret_housing.min[1];
    const seatingOverlap = hullTop - turretBottom;
    if (!(seatingOverlap >= 0.003 && seatingOverlap <= 0.03)) fail('turret seating must overlap hull roof by 0.003-0.03; got ' + seatingOverlap.toFixed(6));
    const widthRatio = bounds.tank_turret_housing.dim[0] / bounds.tank_hull.dim[0];
    const lengthRatio = bounds.tank_turret_housing.dim[2] / bounds.tank_hull.dim[2];
    if (!(widthRatio <= contract.turretMaxWidthRatioOfHull)) fail('turret too wide for hull: ratio ' + widthRatio.toFixed(3));
    if (!(lengthRatio <= contract.turretMaxLengthRatioOfHull)) fail('turret too long for hull: ratio ' + lengthRatio.toFixed(3));
  }
  if (bounds.tank_turret_housing && bounds.tank_gun_barrel && bounds.perforated_barrel_mac) {
    const turretFrontZ = bounds.tank_turret_housing.min[2];
    if (!(bounds.tank_gun_barrel.min[2] < turretFrontZ && bounds.tank_gun_barrel.max[2] > turretFrontZ)) fail('main gun must overlap turret front plane on -Z axis');
    if (!(bounds.perforated_barrel_mac.min[2] < turretFrontZ && bounds.perforated_barrel_mac.max[2] > turretFrontZ)) fail('coaxial MG must overlap turret front plane on -Z axis');
    if (!(Math.abs(bounds.tank_gun_barrel.center[1] - bounds.perforated_barrel_mac.center[1]) < 0.04)) fail('coaxial MG must stay vertically aligned with main gun');
    if (!(bounds.perforated_barrel_mac.center[0] > bounds.tank_gun_barrel.center[0] + 0.06)) fail('coaxial MG must sit as a visible side-offset barrel, not merge into the main gun');
  }
  const assemblyState = readJson(path.join(outDir, 'review-state.json'));
  if (assemblyState.version !== 2) fail('assembly review state must be version 2');
  if (!assemblyState.src?.includes('?v=')) fail('assembly review state must cache-bust LFS GLB URL');
  if (!assemblyState.manifest?.includes('?v=')) fail('assembly review state must cache-bust manifest URL');
  if (assemblyState.parts?.length !== 4) fail('assembly review state must list exactly the four visible tank components');
  for (const id of ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac']) {
    const part = assemblyState.parts.find((candidate) => candidate.id === id);
    if (!part || part.visible !== true) fail('assembly review state must show visible part: ' + id);
  }
  if (assemblyState.parts.some((part) => part.id === 'canteen_lid')) fail('assembly review state must not include canteen_lid');
  for (const id of expectedComponents) {
    const reviewPath = path.join(root, reviewRel, 'meshy-component-kit-' + id + '.json');
    if (!fs.existsSync(reviewPath)) fail('missing component review state: ' + id);
    else {
      const state = readJson(reviewPath);
      if (state.version !== 2) fail('component review state must be version 2: ' + id);
      if (!state.src?.startsWith('https://media.githubusercontent.com/media/Valar05/model-viewer-lab/')) fail('component review state must use media GitHub URL for LFS GLB: ' + id);
      if (!state.src?.includes('?v=')) fail('component review state must cache-bust LFS GLB URL: ' + id);
      if (!state.manifest?.includes('?v=')) fail('component review state must cache-bust manifest URL: ' + id);
    }
  }
}
if (!process.exitCode) console.log('[meshy-component-kit] ok: 5 source GLBs, manifest, review states, and positioning study valid');

