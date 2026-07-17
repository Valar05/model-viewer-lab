#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = process.cwd();
const kitId = 'meshy-component-kit-071716';
const sourceRel = 'labs/hard-surface-factory/source-assets/meshy-component-kit-071716';
const outRel = 'labs/hard-surface-factory/generated/meshy-component-kit-positioning-study';
const reviewRel = 'labs/hard-surface-factory/review-states';
const sourceDir = path.join(root, sourceRel);
const outDir = path.join(root, outRel);
const reviewDir = path.join(root, reviewRel);
const reviewBranch = process.env.MODEL_VIEWER_REVIEW_BRANCH || execFileSync('git', ['branch', '--show-current'], { cwd: root, encoding: 'utf8' }).trim() || 'main';
const rawBase = 'https://raw.githubusercontent.com/Valar05/model-viewer-lab/' + reviewBranch;
const mediaBase = 'https://media.githubusercontent.com/media/Valar05/model-viewer-lab/' + reviewBranch;

const components = [
  { id: 'tank_hull', label: 'tank_hull', sourceFilename: 'Meshy_AI_Tank_hull_0717161907_texture.glb', filename: 'tank_hull.glb', category: 'hull_reference_scaffold', intendedUse: 'source reference scaffold for hull proportions and texture cues', participatesInDefaultAssembly: true, transform: { position: [0, 0, 0], rotationDeg: [0, 0, 0], scale: [1, 1, 1] } },
  { id: 'tank_turret_housing', label: 'tank_turret_housing', sourceFilename: 'Meshy_AI_Tank_turret_housing_0717162705_texture.glb', filename: 'tank_turret_housing.glb', category: 'turret_reference_scaffold', intendedUse: 'source reference scaffold for turret housing proportions; rotated so mantlet/front detail shares the tank forward axis', participatesInDefaultAssembly: true, transform: { position: [0, 0.226, -0.04], rotationDeg: [0, 180, 0], scale: [0.42, 0.42, 0.42] } },
  { id: 'tank_gun_barrel', label: 'tank_gun_barrel', sourceFilename: 'Meshy_AI_Tank_gun_barrel_0717163811_texture.glb', filename: 'tank_gun_barrel.glb', category: 'main_gun_reference_scaffold', intendedUse: 'source reference scaffold for main gun barrel; local X is rotated to tank-forward -Z and seated into the mantlet face', participatesInDefaultAssembly: true, transform: { position: [0, 0.26, -0.54], rotationDeg: [0, 90, 0], scale: [0.68, 0.68, 0.68] } },
  { id: 'perforated_barrel_mac', label: 'perforated_barrel_mac', sourceFilename: 'Meshy_AI_Perforated_Barrel_Mac_0717163656_texture.glb', filename: 'perforated_barrel_mac.glb', category: 'secondary_barrel_reference_scaffold', intendedUse: 'source reference scaffold for coaxial MG detail; flipped so receiver/muzzle read in the same tank-forward -Z direction as the main gun', participatesInDefaultAssembly: true, transform: { position: [0.115, 0.245, -0.395], rotationDeg: [0, -90, 0], scale: [0.3, 0.3, 0.3] } },
  { id: 'canteen_lid', label: 'canteen_lid', sourceFilename: 'Meshy_AI_Canteen_lid_0717163648_texture.glb', filename: 'canteen_lid.glb', category: 'quarantined_hatch_candidate', intendedUse: 'quarantined non-tank semantic candidate; inspect only as possible hatch/lid reference', participatesInDefaultAssembly: false, transform: { position: [1.05, 0.18, 0.08], rotationDeg: [0, 0, 0], scale: [0.22, 0.22, 0.22] } }
];

fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(reviewDir, { recursive: true });

function pad4(n) { return (4 - (n % 4)) % 4; }
function paddedBuffer(buffer, padByte = 0) {
  const pad = pad4(buffer.length);
  return pad ? Buffer.concat([buffer, Buffer.alloc(pad, padByte)]) : buffer;
}
function readGlb(file) {
  const data = fs.readFileSync(file);
  if (data.readUInt32LE(0) !== 0x46546c67) throw new Error(file + ': invalid GLB magic');
  if (data.readUInt32LE(4) !== 2) throw new Error(file + ': expected GLB v2');
  let offset = 12;
  let json = null;
  let bin = Buffer.alloc(0);
  while (offset < data.length) {
    const length = data.readUInt32LE(offset);
    const type = data.readUInt32LE(offset + 4);
    offset += 8;
    const chunk = data.subarray(offset, offset + length);
    offset += length;
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString('utf8').trim());
    if (type === 0x004e4942) bin = chunk;
  }
  if (!json) throw new Error(file + ': missing GLB JSON chunk');
  return { json, bin, bytes: data.length };
}
function componentStats(component) {
  const file = path.join(sourceDir, component.filename);
  const { json, bytes } = readGlb(file);
  const positionAccessors = [];
  for (const mesh of json.meshes || []) {
    for (const primitive of mesh.primitives || []) {
      if (primitive.attributes?.POSITION !== undefined) positionAccessors.push(primitive.attributes.POSITION);
    }
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const index of positionAccessors) {
    const accessor = json.accessors?.[index];
    if (!accessor?.min || !accessor?.max) continue;
    for (let axis = 0; axis < 3; axis++) {
      min[axis] = Math.min(min[axis], accessor.min[axis]);
      max[axis] = Math.max(max[axis], accessor.max[axis]);
    }
  }
  const triangles = (json.meshes || []).reduce((sum, mesh) => sum + (mesh.primitives || []).reduce((inner, primitive) => {
    const accessor = json.accessors?.[primitive.indices];
    return inner + (accessor ? Math.floor(accessor.count / 3) : 0);
  }, 0), 0);
  const hasBounds = min[0] !== Infinity;
  return {
    ...component,
    bytes,
    asset: json.asset || {},
    nodeCount: json.nodes?.length || 0,
    meshCount: json.meshes?.length || 0,
    materialCount: json.materials?.length || 0,
    embeddedImageCount: (json.images || []).filter((image) => image.bufferView !== undefined).length,
    textureCount: json.textures?.length || 0,
    vertexCount: positionAccessors.reduce((sum, index) => sum + (json.accessors?.[index]?.count || 0), 0),
    indexedTriangleCountApprox: triangles,
    bounds: hasBounds ? { min, max, dimensions: max.map((value, axis) => Number((value - min[axis]).toFixed(6))) } : null,
    sourcePath: sourceRel + '/' + component.filename
  };
}
function degToRad(deg) { return deg * Math.PI / 180; }
function eulerToQuat(rotationDeg) {
  const x = degToRad(rotationDeg[0]) / 2;
  const y = degToRad(rotationDeg[1]) / 2;
  const z = degToRad(rotationDeg[2]) / 2;
  const sx = Math.sin(x), cx = Math.cos(x);
  const sy = Math.sin(y), cy = Math.cos(y);
  const sz = Math.sin(z), cz = Math.cos(z);
  return [
    sx * cy * cz - cx * sy * sz,
    cx * sy * cz + sx * cy * sz,
    cx * cy * sz - sx * sy * cz,
    cx * cy * cz + sx * sy * sz
  ].map((value) => Number(value.toFixed(8)));
}
function prefixedName(prefix, value, fallback) { return prefix + '__' + (value || fallback); }
function degToQuatXYZ(rotationDeg) {
  const x = degToRad(rotationDeg[0]) / 2;
  const y = degToRad(rotationDeg[1]) / 2;
  const z = degToRad(rotationDeg[2]) / 2;
  const sx = Math.sin(x), cx = Math.cos(x);
  const sy = Math.sin(y), cy = Math.cos(y);
  const sz = Math.sin(z), cz = Math.cos(z);
  return [
    sx * cy * cz - cx * sy * sz,
    cx * sy * cz + sx * cy * sz,
    cx * cy * sz - sx * sy * cz,
    cx * cy * cz + sx * sy * sz
  ];
}
function rotateVecByQuat(v, q) {
  const [x, y, z] = v;
  const [qx, qy, qz, qw] = q;
  const ix = qw * x + qy * z - qz * y;
  const iy = qw * y + qz * x - qx * z;
  const iz = qw * z + qx * y - qy * x;
  const iw = -qx * x - qy * y - qz * z;
  return [
    ix * qw + iw * -qx + iy * -qz - iz * -qy,
    iy * qw + iw * -qy + iz * -qx - ix * -qz,
    iz * qw + iw * -qz + ix * -qy - iy * -qx
  ];
}
function transformSourceBin(component, json, bin) {
  const out = Buffer.from(bin);
  const q = degToQuatXYZ(component.transform.rotationDeg);
  const scale = component.transform.scale;
  const translate = component.transform.position;
  for (const mesh of json.meshes || []) {
    for (const primitive of mesh.primitives || []) {
      for (const [semantic, accessorIndex] of Object.entries(primitive.attributes || {})) {
        if (semantic !== 'POSITION' && semantic !== 'NORMAL') continue;
        const accessor = json.accessors?.[accessorIndex];
        const view = json.bufferViews?.[accessor?.bufferView];
        if (!accessor || !view || accessor.componentType !== 5126 || accessor.type !== 'VEC3') continue;
        const stride = view.byteStride || 12;
        const start = (view.byteOffset || 0) + (accessor.byteOffset || 0);
        const values = [];
        for (let i = 0; i < accessor.count; i++) {
          const offset = start + i * stride;
          const raw = [out.readFloatLE(offset), out.readFloatLE(offset + 4), out.readFloatLE(offset + 8)];
          let transformed;
          if (semantic === 'POSITION') {
            const scaled = [raw[0] * scale[0], raw[1] * scale[1], raw[2] * scale[2]];
            const rotated = rotateVecByQuat(scaled, q);
            transformed = [rotated[0] + translate[0], rotated[1] + translate[1], rotated[2] + translate[2]];
          } else {
            transformed = rotateVecByQuat(raw, q);
            const len = Math.hypot(transformed[0], transformed[1], transformed[2]) || 1;
            transformed = transformed.map((value) => value / len);
          }
          for (let axis = 0; axis < 3; axis++) out.writeFloatLE(transformed[axis], offset + axis * 4);
          if (semantic === 'POSITION') values.push(transformed);
        }
        if (semantic === 'POSITION' && values.length) {
          accessor.min = [0, 1, 2].map((axis) => Math.min(...values.map((v) => v[axis])));
          accessor.max = [0, 1, 2].map((axis) => Math.max(...values.map((v) => v[axis])));
        }
      }
    }
  }
  return out;
}
function mergeGlbs(stats) {
  const merged = { asset: { version: '2.0', generator: 'model-viewer-lab meshy component kit positioning study' }, scene: 0, scenes: [{ name: 'meshy_component_kit_positioning_study', nodes: [] }], nodes: [], meshes: [], materials: [], textures: [], images: [], samplers: [], accessors: [], bufferViews: [], buffers: [] };
  const binChunks = [];
  let byteOffset = 0;
  for (const component of stats.filter((entry) => entry.participatesInDefaultAssembly)) {
    const loaded = readGlb(path.join(sourceDir, component.filename));
    const json = loaded.json;
    const bin = transformSourceBin(component, json, loaded.bin);
    const bufferViewOffset = merged.bufferViews.length;
    const accessorOffset = merged.accessors.length;
    const materialOffset = merged.materials.length;
    const textureOffset = merged.textures.length;
    const imageOffset = merged.images.length;
    const samplerOffset = merged.samplers.length;
    const meshOffset = merged.meshes.length;
    const chunk = paddedBuffer(bin);
    for (const view of json.bufferViews || []) merged.bufferViews.push({ ...view, buffer: 0, byteOffset: (view.byteOffset || 0) + byteOffset });
    binChunks.push(chunk);
    byteOffset += chunk.length;
    for (const sampler of json.samplers || []) merged.samplers.push({ ...sampler });
    for (const image of json.images || []) {
      const next = { ...image };
      if (next.bufferView !== undefined) next.bufferView += bufferViewOffset;
      if (next.name) next.name = prefixedName(component.id, next.name, 'image');
      merged.images.push(next);
    }
    for (const texture of json.textures || []) {
      const next = { ...texture };
      if (next.source !== undefined) next.source += imageOffset;
      if (next.sampler !== undefined) next.sampler += samplerOffset;
      if (next.name) next.name = prefixedName(component.id, next.name, 'texture');
      merged.textures.push(next);
    }
    for (const material of json.materials || []) {
      const next = JSON.parse(JSON.stringify(material));
      if (next.name) next.name = prefixedName(component.id, next.name, 'material');
      const pbr = next.pbrMetallicRoughness;
      if (pbr?.baseColorTexture?.index !== undefined) pbr.baseColorTexture.index += textureOffset;
      if (pbr?.metallicRoughnessTexture?.index !== undefined) pbr.metallicRoughnessTexture.index += textureOffset;
      if (next.normalTexture?.index !== undefined) next.normalTexture.index += textureOffset;
      if (next.occlusionTexture?.index !== undefined) next.occlusionTexture.index += textureOffset;
      if (next.emissiveTexture?.index !== undefined) next.emissiveTexture.index += textureOffset;
      merged.materials.push(next);
    }
    for (const accessor of json.accessors || []) {
      const next = { ...accessor };
      if (next.bufferView !== undefined) next.bufferView += bufferViewOffset;
      merged.accessors.push(next);
    }
    for (const mesh of json.meshes || []) {
      const next = JSON.parse(JSON.stringify(mesh));
      next.name = prefixedName(component.id, next.name, 'mesh');
      for (const primitive of next.primitives || []) {
        if (primitive.indices !== undefined) primitive.indices += accessorOffset;
        for (const [attribute, index] of Object.entries(primitive.attributes || {})) primitive.attributes[attribute] = index + accessorOffset;
        if (primitive.material !== undefined) primitive.material += materialOffset;
      }
      merged.meshes.push(next);
    }
    const sourceNodes = json.nodes || [];
    const childNodes = [];
    for (const node of sourceNodes) {
      const next = JSON.parse(JSON.stringify(node));
      next.name = component.id;
      if (next.mesh !== undefined) next.mesh += meshOffset;
      if (next.children) next.children = next.children.map((child) => child + merged.nodes.length);
      childNodes.push(merged.nodes.length);
      merged.nodes.push(next);
    }
    for (const nodeIndex of childNodes) {
      merged.nodes[nodeIndex].extras = { category: component.category, intendedUse: component.intendedUse, bakedIntoVisibleTankAssembly: true };
      merged.scenes[0].nodes.push(nodeIndex);
    }
  }
  const bin = Buffer.concat(binChunks);
  merged.buffers = [{ byteLength: bin.length }];
  let jsonBuffer = paddedBuffer(Buffer.from(JSON.stringify(merged), 'utf8'), 0x20);
  const totalLength = 12 + 8 + jsonBuffer.length + 8 + bin.length;
  const glb = Buffer.alloc(totalLength);
  let cursor = 0;
  glb.writeUInt32LE(0x46546c67, cursor); cursor += 4;
  glb.writeUInt32LE(2, cursor); cursor += 4;
  glb.writeUInt32LE(totalLength, cursor); cursor += 4;
  glb.writeUInt32LE(jsonBuffer.length, cursor); cursor += 4;
  glb.writeUInt32LE(0x4e4f534a, cursor); cursor += 4;
  jsonBuffer.copy(glb, cursor); cursor += jsonBuffer.length;
  glb.writeUInt32LE(bin.length, cursor); cursor += 4;
  glb.writeUInt32LE(0x004e4942, cursor); cursor += 4;
  bin.copy(glb, cursor);
  fs.writeFileSync(path.join(outDir, 'meshy_component_kit_positioning_study.glb'), glb);
}
function writeReviewState(file, state) { fs.writeFileSync(path.join(reviewDir, file), JSON.stringify(state, null, 2) + '\n'); }
function componentReviewState(component) {
  return { version: 2, src: mediaBase + '/' + sourceRel + '/' + component.filename, manifest: rawBase + '/' + sourceRel + '/kit_manifest.json', title: 'Meshy component ' + component.id, camera: { position: [0, 1.2, 3.2], target: [0, 0, 0], fov: 38 }, display: { clay: false, wire: false, grid: true, boxes: false }, selectedPartId: component.id, parts: [{ id: component.id, label: component.label, visible: true, position: [0, 0, 0], rotationDeg: [0, 0, 0], scale: [1, 1, 1] }] };
}
function assemblyReviewState(stats) {
  return { version: 2, src: mediaBase + '/' + outRel + '/meshy_component_kit_positioning_study.glb', manifest: rawBase + '/' + outRel + '/model_manifest.json', title: 'meshy_component_kit_positioning_study', camera: { position: [0, 1.0, 3.0], target: [0, 0.18, -0.08], fov: 34 }, display: { clay: false, wire: false, grid: true, boxes: false }, selectedPartId: 'tank_hull', parts: stats.filter((component) => component.participatesInDefaultAssembly).map((component) => ({ id: component.id, label: component.label, visible: true, position: [0, 0, 0], rotationDeg: [0, 0, 0], scale: [1, 1, 1] })) };
}

const stats = components.map(componentStats);
mergeGlbs(stats);
const reviewStates = Object.fromEntries(stats.map((component) => [component.id, reviewRel + '/meshy-component-kit-' + component.id + '.json']));
const manifest = { id: kitId, type: 'meshy-reference-component-kit', generatedAt: new Date().toISOString(), sourcePolicy: { assetClass: 'generated Meshy reference scaffolds', productionTopology: false, finalAuthoredGeometry: false, taskManifestsAvailable: false, notes: 'Original GLBs were found untracked at the Model Viewer Lab repo root. No Meshy task manifest or prompt payload accompanied them.' }, components: stats, positioningStudy: { id: 'meshy_component_kit_positioning_study', claim: 'non-production layout/reference study only; not visual acceptance and not authored topology', glb: outRel + '/meshy_component_kit_positioning_study.glb', manifest: outRel + '/model_manifest.json', reviewState: outRel + '/review-state.json' }, reviewStates };
fs.writeFileSync(path.join(sourceDir, 'kit_manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
const provenance = '# Meshy Component Kit 071716 Provenance\n\n- Asset class: generated Meshy reference scaffolds.\n- Original location: untracked GLBs at the Model Viewer Lab repository root.\n- Ingest target: ' + sourceRel + '.\n- Meshy task manifests: not present with the files at ingest time.\n- Production status: not production geometry, not clean authored topology, and not visual acceptance.\n- Target use: measurement/reference scaffolds and a Model Viewer positioning study for follow-up hard-surface authoring.\n- Quarantine note: canteen_lid is retained only as a possible hatch/lid reference candidate and is hidden in the default assembly review state.\n';
fs.writeFileSync(path.join(sourceDir, 'PROVENANCE.md'), provenance);
for (const component of stats) writeReviewState('meshy-component-kit-' + component.id + '.json', componentReviewState(component));
const assemblyState = assemblyReviewState(stats);
fs.writeFileSync(path.join(outDir, 'review-state.json'), JSON.stringify(assemblyState, null, 2) + '\n');
const redBuildEvidence = {
  id: 'red-build-20260717-orientation-seating',
  capturePath: '/storage/emulated/0/Pictures/Screenshots/Screenshot_20260717-130121.png',
  captureTimestampLocal: '2026-07-17 13:01:21 America/Chicago',
  expectedVisibleState: 'mantlet, main gun, and coaxial MG share one tank-forward axis; turret is scaled to the hull roof and visibly seated on the turret ring',
  actualVisibleRead: 'capture shows the mantlet/front detail on the opposite side from the main gun axis, the MG reads backwards relative to the gun, and the turret is oversized with a visible dark seating gap above the hull roof',
  failingGate: 'previous cloud capture proved the required part names were visible but did not prove part orientation, gun/mantlet relationship, or turret seating',
  requiredRepair: 'generated assembly GLB must rotate the turret front detail onto the gun axis, flip/reposition the MG as a coaxial barrel, shrink the turret, and lower it until its base overlaps the hull roof plane'
};
fs.writeFileSync(path.join(outDir, 'red-build-evidence.json'), JSON.stringify(redBuildEvidence, null, 2) + '\n');
const modelManifest = { id: 'meshy_component_kit_positioning_study', type: 'visible-tank-positioning-study', sourceKit: sourceRel + '/kit_manifest.json', glb: outRel + '/meshy_component_kit_positioning_study.glb', reviewState: outRel + '/review-state.json', redBuildEvidence: outRel + '/red-build-evidence.json', claim: 'non-production visible tank assembly study only; not visual acceptance and not authored topology', visibleAssemblyRequiredParts: ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac'], relationshipContracts: { tankForwardAxis: [0, 0, -1], turretMantletSharesGunAxis: true, coaxialMgSharesGunAxis: true, turretMustBeSeatedOnHull: true, turretMaxWidthRatioOfHull: 0.7, turretMaxLengthRatioOfHull: 0.55, barrelMustOverlapTurretFront: true }, quarantinedSourceOnlyParts: ['canteen_lid'], parts: stats.map((component) => ({ id: component.id, category: component.category, source: component.sourcePath, originalTransform: component.transform, visibleByDefault: component.participatesInDefaultAssembly })) };
fs.writeFileSync(path.join(outDir, 'model_manifest.json'), JSON.stringify(modelManifest, null, 2) + '\n');
console.log(JSON.stringify({ ok: true, kit: sourceRel, output: outRel, componentCount: stats.length }, null, 2));

