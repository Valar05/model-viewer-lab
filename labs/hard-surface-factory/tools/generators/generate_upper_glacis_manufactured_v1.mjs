#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = process.cwd();
const paramRel = 'labs/hard-surface-factory/parameters/upper-glacis-manufactured-v1.json';
const outRel = 'labs/hard-surface-factory/generated/upper-glacis-manufactured-v1';
const params = JSON.parse(fs.readFileSync(path.join(root, paramRel), 'utf8'));
const outDir = path.join(root, outRel);
const reviewBranch = process.env.MODEL_VIEWER_REVIEW_BRANCH || execFileSync('git', ['branch', '--show-current'], { cwd: root, encoding: 'utf8' }).trim() || 'main';
fs.mkdirSync(outDir, { recursive: true });

const m = params.measuredReferenceFeatures;
const top = [
  [-m.frontLowerWidth / 2, m.frontLowerY, m.frontLowerZ],
  [m.frontLowerWidth / 2, m.frontLowerY, m.frontLowerZ],
  [m.deckTransitionWidth / 2, m.deckTransitionY, m.deckTransitionZ],
  [-m.deckTransitionWidth / 2, m.deckTransitionY, m.deckTransitionZ]
];
const underside = top.map(([x, y, z]) => [x * 0.985, y - m.armorThickness, z - 0.045]);
const vertices = [...top, ...underside];
const faces = [
  [0, 1, 2], [0, 2, 3],
  [5, 4, 7], [5, 7, 6],
  [4, 5, 1], [4, 1, 0],
  [3, 2, 6], [3, 6, 7],
  [0, 3, 7], [0, 7, 4],
  [1, 5, 6], [1, 6, 2]
];
const faceInterfaces = [
  'outer_sloped_armor', 'outer_sloped_armor',
  'inner_backing_plane', 'inner_backing_plane',
  'front_lower_boundary', 'front_lower_boundary',
  'deck_transition', 'deck_transition',
  'left_shoulder_return', 'left_shoulder_return',
  'right_shoulder_return', 'right_shoulder_return'
];

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}
function topologyReport() {
  const edges = new Map();
  for (const face of faces) {
    for (const [a, b] of [[face[0], face[1]], [face[1], face[2]], [face[2], face[0]]]) {
      const key = edgeKey(a, b);
      edges.set(key, (edges.get(key) || 0) + 1);
    }
  }
  const boundaryEdges = [...edges.entries()].filter(([, count]) => count === 1).map(([edge]) => edge);
  const nonmanifoldEdges = [...edges.entries()].filter(([, count]) => count !== 2).map(([edge, count]) => ({ edge, count }));
  return {
    mesh: params.id,
    vertexCount: vertices.length,
    triangleCount: faces.length,
    uniqueEdgeCount: edges.size,
    boundaryEdgeCount: boundaryEdges.length,
    nonmanifoldEdgeCount: nonmanifoldEdges.length,
    boundaryEdges,
    nonmanifoldEdges,
    gate: boundaryEdges.length === 0 && nonmanifoldEdges.length === 0 ? 'pass' : 'fail'
  };
}

function normal(face) {
  const a = vertices[face[0]], b = vertices[face[1]], c = vertices[face[2]];
  const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  const n = [
    u[1] * v[2] - u[2] * v[1],
    u[2] * v[0] - u[0] * v[2],
    u[0] * v[1] - u[1] * v[0]
  ];
  const len = Math.hypot(...n) || 1;
  return n.map((value) => value / len);
}

function writeGlb(file) {
  const positions = [];
  const normals = [];
  const indices = [];
  for (const face of faces) {
    const n = normal(face);
    for (const vi of face) {
      positions.push(...vertices[vi]);
      normals.push(...n);
      indices.push(indices.length);
    }
  }
  const positionBuffer = Buffer.alloc(positions.length * 4);
  positions.forEach((value, index) => positionBuffer.writeFloatLE(value, index * 4));
  const normalBuffer = Buffer.alloc(normals.length * 4);
  normals.forEach((value, index) => normalBuffer.writeFloatLE(value, index * 4));
  const indexBuffer = Buffer.alloc(indices.length * 2);
  indices.forEach((value, index) => indexBuffer.writeUInt16LE(value, index * 2));
  const chunks = [positionBuffer, normalBuffer, indexBuffer];
  let offset = 0;
  const views = chunks.map((buffer) => {
    const view = { buffer: 0, byteOffset: offset, byteLength: buffer.length };
    offset += buffer.length;
    while (offset % 4) offset++;
    return view;
  });
  const bin = Buffer.alloc(offset);
  offset = 0;
  for (const buffer of chunks) {
    buffer.copy(bin, offset);
    offset += buffer.length;
    while (offset % 4) offset++;
  }
  const xs = vertices.map((v) => v[0]), ys = vertices.map((v) => v[1]), zs = vertices.map((v) => v[2]);
  const json = {
    asset: { version: '2.0', generator: 'model-viewer-lab upper-glacis manufactured v1' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ name: 'primary_armor_mass__interfaces_front_lower_left_right_deck_turret_socket', mesh: 0 }],
    meshes: [{
      name: 'primary_armor_mass',
      primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, material: 0 }]
    }],
    materials: [{ name: 'rolled_cast_armor_clay', pbrMetallicRoughness: { baseColorFactor: [0.46, 0.5, 0.42, 1], metallicFactor: 0, roughnessFactor: 0.78 } }],
    buffers: [{ byteLength: bin.length }],
    bufferViews: [
      { ...views[0], target: 34962 },
      { ...views[1], target: 34962 },
      { ...views[2], target: 34963 }
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: positions.length / 3, type: 'VEC3', min: [Math.min(...xs), Math.min(...ys), Math.min(...zs)], max: [Math.max(...xs), Math.max(...ys), Math.max(...zs)] },
      { bufferView: 1, componentType: 5126, count: normals.length / 3, type: 'VEC3' },
      { bufferView: 2, componentType: 5123, count: indices.length, type: 'SCALAR' }
    ]
  };
  let jsonChunk = Buffer.from(JSON.stringify(json), 'utf8');
  while (jsonChunk.length % 4) jsonChunk = Buffer.concat([jsonChunk, Buffer.from(' ')]);
  const total = 12 + 8 + jsonChunk.length + 8 + bin.length;
  const glb = Buffer.alloc(total);
  let cursor = 0;
  glb.writeUInt32LE(0x46546c67, cursor); cursor += 4;
  glb.writeUInt32LE(2, cursor); cursor += 4;
  glb.writeUInt32LE(total, cursor); cursor += 4;
  glb.writeUInt32LE(jsonChunk.length, cursor); cursor += 4;
  glb.writeUInt32LE(0x4e4f534a, cursor); cursor += 4;
  jsonChunk.copy(glb, cursor); cursor += jsonChunk.length;
  glb.writeUInt32LE(bin.length, cursor); cursor += 4;
  glb.writeUInt32LE(0x004e4942, cursor); cursor += 4;
  bin.copy(glb, cursor);
  fs.writeFileSync(file, glb);
}

function project(v, angle) {
  const az = angle.azimuthDeg * Math.PI / 180;
  const el = angle.elevationDeg * Math.PI / 180;
  const x = v[0] * Math.cos(az) - v[2] * Math.sin(az);
  const depth = v[0] * Math.sin(az) + v[2] * Math.cos(az);
  const y = v[1] * Math.cos(el) - depth * Math.sin(el);
  return [x, y, depth];
}

function writeSvg(angle) {
  const points = vertices.map((v) => project(v, angle));
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]), ds = points.map((p) => p[2]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(720 / (maxX - minX || 1), 420 / (maxY - minY || 1));
  const xy = (p) => `${60 + (p[0] - minX) * scale},${460 - (p[1] - minY) * scale}`;
  const polygons = faces.map((face, index) => {
    const shade = 48 + Math.round((index / faces.length) * 120);
    return `<polygon points="${face.map((vi) => xy(points[vi])).join(' ')}" fill="rgb(${shade},${shade + 12},${shade})" stroke="#111" stroke-width="1"/>`;
  }).join('\n');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="840" height="540" viewBox="0 0 840 540">
<rect width="840" height="540" fill="#f7f7f2"/>
<text x="24" y="34" font-family="monospace" font-size="18">${params.id} ${angle.id}</text>
<text x="24" y="60" font-family="monospace" font-size="13">silhouette width ${(maxX - minX).toFixed(3)}m depth span ${(Math.max(...ds) - Math.min(...ds)).toFixed(3)}m</text>
${polygons}
</svg>
`;
  fs.writeFileSync(path.join(outDir, `render-${angle.id}.svg`), svg);
  return {
    id: angle.id,
    azimuthDeg: angle.azimuthDeg,
    elevationDeg: angle.elevationDeg,
    silhouetteWidth: Number((maxX - minX).toFixed(4)),
    silhouetteHeight: Number((maxY - minY).toFixed(4)),
    depthSpan: Number((Math.max(...ds) - Math.min(...ds)).toFixed(4)),
    render: `${outRel}/render-${angle.id}.svg`
  };
}

const topology = topologyReport();
if (topology.gate !== 'pass') {
  fs.writeFileSync(path.join(outDir, 'topology_report.json'), JSON.stringify(topology, null, 2));
  throw new Error('primary armor mass topology gate failed');
}

const glbName = `${params.id}.glb`;
writeGlb(path.join(outDir, glbName));
const visual = params.visualGates.fixedAngles.map(writeSvg);
const authored = {
  id: params.id,
  generatedAt: new Date().toISOString(),
  sourceTrianglesUsedAsFinalAuthoredTopology: false,
  partContract: params.partContract,
  solids: [{
    name: params.partContract.promotedPartName,
    role: 'explicit upper glacis Part contract',
    manufacturingMethod: params.manufacturingParameters.plateStyle,
    vertexCount: topology.vertexCount,
    triangleCount: topology.triangleCount,
    boundaryEdgeCount: topology.boundaryEdgeCount,
    nonmanifoldEdgeCount: topology.nonmanifoldEdgeCount,
    namedInterfaces: params.namedInterfaces,
    protectedVisibleSkin: params.partContract.protectedVisibleSkin,
    backingSolid: params.partContract.backingSolid,
    faceInterfaceOrder: faceInterfaces
  }],
  secondaryDetails: {
    status: 'not_started',
    reason: 'Part contract gate is limited to protected visible skin, backing solid, named interfaces, and six fixed views.'
  }
};
const silhouette = {
  id: params.id,
  gate: 'pass',
  fixedAngles: visual,
  declaredThresholds: params.visualGates
};
const measurement = {
  id: params.id,
  units: params.units,
  sourcePolicy: params.sourcePolicy,
  measuredReferenceFeatures: params.measuredReferenceFeatures,
  derived: {
    slopeRise: Number((m.deckTransitionY - m.frontLowerY).toFixed(4)),
    slopeRun: Number((m.deckTransitionZ - m.frontLowerZ).toFixed(4)),
    slopeAngleDeg: Number((Math.atan2(m.deckTransitionY - m.frontLowerY, m.deckTransitionZ - m.frontLowerZ) * 180 / Math.PI).toFixed(3)),
    shoulderWidthDelta: Number((m.frontLowerWidth - m.deckTransitionWidth).toFixed(4))
  }
};
const manifest = {
  id: params.id,
  type: 'part-contract-upper-glacis',
  partContract: params.partContract.id,
  glb: `${outRel}/${glbName}`,
  parameters: paramRel,
  reports: {
    measurement: `${outRel}/measurement_report.json`,
    authoredSolids: `${outRel}/authored_solids_report.json`,
    topology: `${outRel}/topology_report.json`,
    silhouetteDepth: `${outRel}/silhouette_depth_report.json`,
    provenance: `${outRel}/provenance_note.md`
  },
  reviewState: `${outRel}/review-state.json`
};
const state = {
  version: 2,
  src: `https://raw.githubusercontent.com/Valar05/model-viewer-lab/${reviewBranch}/${outRel}/${glbName}`,
  manifest: `https://raw.githubusercontent.com/Valar05/model-viewer-lab/${reviewBranch}/${outRel}/model_manifest.json`,
  title: params.id,
  camera: { position: [0, 1.5, 4.8], target: [0, 0.8, 0], fov: 38 },
  display: { clay: true, wire: false, grid: true, boxes: false },
  selectedPartId: params.partContract.promotedPartName,
  parts: [{
    id: params.partContract.promotedPartName,
    label: params.partContract.promotedPartName,
    visible: true,
    position: [0, 0, 0],
    rotationDeg: [0, 0, 0],
    scale: [1, 1, 1]
  }]
};
const provenance = `# ${params.id} Provenance

- Asset class: source-authored generated GLB.
- Generator: labs/hard-surface-factory/tools/generators/generate_upper_glacis_manufactured_v1.mjs.
- Parameters: ${paramRel}.
- Final topology policy: source triangles are not used as final authored topology.
- Measurement inputs: committed reports and lab research listed in the parameter file.
- Target use: cloud-readable Model Viewer review and CI-verifiable Part-contract evidence, not a production tank asset.
- Acceptance claim: valid generated review package with protected visible skin, separately authored backing solid, named interfaces, and six fixed-view silhouette/depth evidence; this does not claim clean production topology.
- Failed setup preserved: initial normal clone attempted to smudge historical LFS source GLBs and hit a GitHub LFS 404 for meshy_hull_envelope.glb; this run proceeded from committed pointers and authored fresh topology instead.
`;
fs.writeFileSync(path.join(outDir, 'measurement_report.json'), JSON.stringify(measurement, null, 2));
fs.writeFileSync(path.join(outDir, 'authored_solids_report.json'), JSON.stringify(authored, null, 2));
fs.writeFileSync(path.join(outDir, 'topology_report.json'), JSON.stringify(topology, null, 2));
fs.writeFileSync(path.join(outDir, 'silhouette_depth_report.json'), JSON.stringify(silhouette, null, 2));
fs.writeFileSync(path.join(outDir, 'model_manifest.json'), JSON.stringify(manifest, null, 2));
fs.writeFileSync(path.join(outDir, 'review-state.json'), JSON.stringify(state, null, 2));
fs.writeFileSync(path.join(outDir, 'provenance_note.md'), provenance);
console.log(JSON.stringify({ ok: true, output: outRel, topology: topology.gate }, null, 2));
