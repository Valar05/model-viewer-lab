import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MATERIALS = [
  material('TT_Main_Ivory', '#D8D0B7', 0.72, 0.00),
  material('TT_Industrial_Yellow', '#C99A32', 0.68, 0.00),
  material('TT_Graphite', '#292D2C', 0.78, 0.10),
  material('TT_Rubber', '#171918', 0.95, 0.00),
  material('TT_Pressure_Glass', '#283843', 0.22, 0.00),
  material('TT_Cool_Metal', '#555D60', 0.48, 0.72),
  material('TT_Service_Orange', '#A85A24', 0.62, 0.05),
  material('TT_Headlamp', '#F4EACB', 0.22, 0.00, [0.45, 0.38, 0.24]),
  material('TT_TailLamp', '#812B29', 0.35, 0.00, [0.10, 0.015, 0.012]),
  material('TT_Indicator_Amber', '#B86B1D', 0.35, 0.00, [0.12, 0.05, 0.005]),
  material('TT_Cheatgun', '#333638', 0.42, 0.76)
];
const MATERIAL_INDEX = Object.fromEntries(MATERIALS.map((entry, index) => [entry.name, index]));
const ZONE_ORDER = MATERIALS.map((entry) => entry.name);

function material(name, hex, roughnessFactor, metallicFactor, emissiveFactor = null) {
  const clean = hex.replace('#', '');
  const rgb = [0, 2, 4].map((offset) => parseInt(clean.slice(offset, offset + 2), 16) / 255);
  const result = {
    name,
    doubleSided: false,
    pbrMetallicRoughness: {
      baseColorFactor: [...rgb, 1],
      roughnessFactor,
      metallicFactor
    }
  };
  if (emissiveFactor) result.emissiveFactor = emissiveFactor;
  return result;
}

function parseGlb(buffer) {
  if (buffer.subarray(0, 4).toString('ascii') !== 'glTF') throw new Error('not a GLB');
  if (buffer.readUInt32LE(4) !== 2) throw new Error('only GLB v2 is supported');
  if (buffer.readUInt32LE(8) !== buffer.length) throw new Error('GLB byteLength mismatch');
  let offset = 12;
  let json = null;
  let bin = null;
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    offset += 8 + length;
    if (type === 0x4e4f534a) json = JSON.parse(data.toString('utf8').replace(/[\u0000 ]+$/g, ''));
    if (type === 0x004e4942) bin = Buffer.from(data);
  }
  if (!json || !bin) throw new Error('GLB requires JSON and BIN chunks');
  return { json, bin };
}

function componentBytes(componentType) {
  return ({ 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 })[componentType];
}
function components(type) {
  return ({ SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 })[type];
}
function readComponent(buffer, offset, componentType) {
  if (componentType === 5120) return buffer.readInt8(offset);
  if (componentType === 5121) return buffer.readUInt8(offset);
  if (componentType === 5122) return buffer.readInt16LE(offset);
  if (componentType === 5123) return buffer.readUInt16LE(offset);
  if (componentType === 5125) return buffer.readUInt32LE(offset);
  if (componentType === 5126) return buffer.readFloatLE(offset);
  throw new Error('unsupported accessor componentType ' + componentType);
}
function readAccessor(json, bin, accessorIndex) {
  const accessor = json.accessors[accessorIndex];
  const view = json.bufferViews[accessor.bufferView];
  const count = accessor.count;
  const width = components(accessor.type);
  const componentSize = componentBytes(accessor.componentType);
  const itemBytes = width * componentSize;
  const stride = view.byteStride || itemBytes;
  const base = (view.byteOffset || 0) + (accessor.byteOffset || 0);
  const rows = new Array(count);
  for (let row = 0; row < count; row += 1) {
    const values = new Array(width);
    const rowOffset = base + row * stride;
    for (let col = 0; col < width; col += 1) {
      values[col] = readComponent(bin, rowOffset + col * componentSize, accessor.componentType);
    }
    rows[row] = values;
  }
  return rows;
}

function cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
function normalize(v) {
  const length = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / length, v[1] / length, v[2] / length];
}
function triangleFacts(points) {
  const centroid = [0, 1, 2].map((axis) => (points[0][axis] + points[1][axis] + points[2][axis]) / 3);
  const a = points[0];
  const b = [points[1][0] - a[0], points[1][1] - a[1], points[1][2] - a[2]];
  const c = [points[2][0] - a[0], points[2][1] - a[1], points[2][2] - a[2]];
  return { centroid, normal: normalize(cross(b, c)) };
}

function classifyBody(points) {
  const { centroid: [x, y, z], normal: n } = triangleFacts(points);
  const ay = Math.abs(y);
  if (x >= -1.35 && x <= -0.75 && ay <= 0.70 && z >= 1.55 && n[0] < -0.50 && n[2] > 0.50) return 'TT_Pressure_Glass';\n  if (x >= 0.10 && x <= 0.22 && z >= 1.68 && Math.abs(n[0]) > 0.75) return 'TT_Pressure_Glass';
  if (ay >= 0.90 && z >= 1.28 && z <= 1.56 && Math.abs(n[1]) > 0.45) return 'TT_Industrial_Yellow';
  if (x <= -2.56 && ay >= 0.55 && z >= 0.89 && n[0] < -0.75) return 'TT_Headlamp';
  if (x <= -2.60 && ay >= 0.68 && z >= 0.78 && z <= 0.89 && n[0] < -0.75) return 'TT_Indicator_Amber';
  if (x >= 2.60 && ay >= 0.82 && z >= 1.15 && z <= 1.35 && n[0] > 0.75) return 'TT_TailLamp';
  if (x >= -2.30 && x <= -2.14 && ay <= 0.48 && z >= 0.56 && z <= 1.16 && n[0] < -0.75) return 'TT_Graphite';
  if (x >= 0.10 && x <= 2.50) {
    if (n[2] > 0.80 && z <= 1.10 && ay <= 0.80) return 'TT_Graphite';
    if (Math.abs(n[1]) > 0.80 && ay >= 0.64 && ay <= 0.78 && z >= 0.95 && z <= 1.62) return 'TT_Graphite';
    if (Math.abs(n[0]) > 0.80 && ay <= 0.76 && z >= 0.95 && z <= 1.64) return 'TT_Graphite';
  }
  if (ay >= 0.60 && ay <= 0.90 && z <= 0.94) return 'TT_Graphite';
  if (x >= 2.40 && z <= 0.60 && ay <= 0.75) return 'TT_Cool_Metal';
  return 'TT_Main_Ivory';
}

function classifyNamedMesh(name) {
  const upper = String(name || '').toUpperCase();
  if (upper.startsWith('HAZARD_SHOULDER')) return 'TT_Industrial_Yellow';
  if (upper.includes('WINDOW') || upper.includes('WINDSHIELD')) return 'TT_Pressure_Glass';
  if (upper.startsWith('ROOF_LIGHT_')) return 'TT_Indicator_Amber';
  if (upper.includes('TIRE')) return 'TT_Rubber';
  if (upper.includes('RIM') || upper.includes('HUB') || upper.includes('BUMPER') || upper.includes('WINCH')) return 'TT_Cool_Metal';
  if (upper.includes('SHOCK')) return 'TT_Service_Orange';
  if (upper.includes('CHEATGUN')) return 'TT_Cheatgun';
  if (upper.includes('CHASSIS') || upper.includes('ARM') || upper.includes('BED_RAIL') || upper.includes('BED_FLOOR') || upper.includes('ROOF_RACK')) return 'TT_Graphite';
  return 'TT_Main_Ivory';
}

function appendIndices(json, binParts, indices) {
  let currentLength = binParts.reduce((sum, part) => sum + part.length, 0);
  const pad = (4 - (currentLength % 4)) % 4;
  if (pad) {
    binParts.push(Buffer.alloc(pad));
    currentLength += pad;
  }
  const data = Buffer.alloc(indices.length * 4);
  indices.forEach((value, index) => data.writeUInt32LE(value >>> 0, index * 4));
  const bufferView = json.bufferViews.length;
  json.bufferViews.push({ buffer: 0, byteOffset: currentLength, byteLength: data.length, target: 34963 });
  binParts.push(data);
  const accessor = json.accessors.length;
  let min = 0;
  let max = 0;
  if (indices.length) {
    min = indices[0];
    max = indices[0];
    for (const value of indices) {
      if (value < min) min = value;
      if (value > max) max = value;
    }
  }
  json.accessors.push({ bufferView, componentType: 5125, count: indices.length, type: 'SCALAR', min: [min], max: [max] });
  return accessor;
}

export function textureOutlawGlb(sourceBuffer) {
  const source = Buffer.from(sourceBuffer);
  const { json, bin } = parseGlb(source);
  const sourceJson = structuredClone(json);
  const output = structuredClone(json);
  output.materials = structuredClone(MATERIALS);
  const binParts = [Buffer.from(bin)];
  const zoneCounts = Object.fromEntries(ZONE_ORDER.map((zone) => [zone, 0]));

  for (let meshIndex = 0; meshIndex < output.meshes.length; meshIndex += 1) {
    const mesh = output.meshes[meshIndex];
    const sourceMesh = sourceJson.meshes[meshIndex];
    const name = mesh.name || '';
    if (name !== 'body_shell') {
      const zone = classifyNamedMesh(name);
      for (let primitiveIndex = 0; primitiveIndex < mesh.primitives.length; primitiveIndex += 1) {
        const primitive = mesh.primitives[primitiveIndex];
        primitive.material = MATERIAL_INDEX[zone];
        const sourcePrimitive = sourceMesh.primitives[primitiveIndex];
        if (sourcePrimitive.indices !== undefined) zoneCounts[zone] += sourceJson.accessors[sourcePrimitive.indices].count / 3;
      }
      continue;
    }
    if (sourceMesh.primitives.length !== 1) throw new Error('body_shell must begin as one primitive');
    const sourcePrimitive = sourceMesh.primitives[0];
    const positions = readAccessor(sourceJson, bin, sourcePrimitive.attributes.POSITION);
    const sourceIndices = readAccessor(sourceJson, bin, sourcePrimitive.indices).map((row) => row[0]);
    if (sourceIndices.length % 3 !== 0) throw new Error('body_shell indices are not triangles');
    const grouped = Object.fromEntries(ZONE_ORDER.map((zone) => [zone, []]));
    for (let index = 0; index < sourceIndices.length; index += 3) {
      const tri = sourceIndices.slice(index, index + 3);
      const zone = classifyBody(tri.map((vertexIndex) => positions[vertexIndex]));
      grouped[zone].push(...tri);
      zoneCounts[zone] += 1;
    }
    const bodyPrimitives = [];
    for (const zone of ZONE_ORDER) {
      const indices = grouped[zone];
      if (!indices.length) continue;
      const accessor = appendIndices(output, binParts, indices);
      const primitive = structuredClone(sourcePrimitive);
      primitive.indices = accessor;
      primitive.material = MATERIAL_INDEX[zone];
      bodyPrimitives.push(primitive);
    }
    mesh.primitives = bodyPrimitives;
  }

  const paddedBinLength = binParts.reduce((sum, part) => sum + part.length, 0);
  const binPad = (4 - (paddedBinLength % 4)) % 4;
  if (binPad) binParts.push(Buffer.alloc(binPad));
  const outputBin = Buffer.concat(binParts);
  output.buffers[0].byteLength = outputBin.length;
  output.asset = output.asset || { version: '2.0' };
  output.asset.extras = {
    ...(output.asset.extras || {}),
    outlawSemanticAlbedo: 'v2',
    semanticZones: Object.fromEntries(ZONE_ORDER.filter((zone) => zoneCounts[zone] > 0).map((zone) => [zone, zoneCounts[zone]]))
  };

  let jsonBuffer = Buffer.from(JSON.stringify(output), 'utf8');
  const jsonPad = (4 - (jsonBuffer.length % 4)) % 4;
  if (jsonPad) jsonBuffer = Buffer.concat([jsonBuffer, Buffer.alloc(jsonPad, 0x20)]);
  const totalLength = 12 + 8 + jsonBuffer.length + 8 + outputBin.length;
  const header = Buffer.alloc(12);
  header.write('glTF', 0, 'ascii');
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(totalLength, 8);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(jsonBuffer.length, 0);
  jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(outputBin.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, jsonHeader, jsonBuffer, binHeader, outputBin]);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    console.error('usage: node scripts/outlaw-semantic-texture.mjs input.glb output.glb');
    process.exit(2);
  }
  writeFileSync(output, textureOutlawGlb(readFileSync(input)));
}