import assert from 'node:assert/strict';
import { analyzeGlb, archaeologyCsv, explodeManifest } from './glb_archaeology.mjs';

function makeFixture() {
  const positions = new Float32Array([
    -2,0,0, -1,0,0, -1.5,1,0, -1.5,0.5,1,
     2,0,0,  1,0,0,  1.5,1,0,  1.5,0.5,1,
  ]);
  const indices = new Uint16Array([
    0,1,2, 0,3,1, 1,3,2, 2,3,0,
    4,6,5, 4,5,7, 5,6,7, 6,4,7,
  ]);
  const posBytes = Buffer.from(positions.buffer);
  const idxBytes = Buffer.from(indices.buffer);
  const bin = Buffer.concat([posBytes, idxBytes]);
  const gltf = {
    asset:{version:'2.0',generator:'foundry-test'},
    buffers:[{byteLength:bin.length}],
    bufferViews:[
      {buffer:0,byteOffset:0,byteLength:posBytes.length,target:34962},
      {buffer:0,byteOffset:posBytes.length,byteLength:idxBytes.length,target:34963},
    ],
    accessors:[
      {bufferView:0,componentType:5126,count:8,type:'VEC3'},
      {bufferView:1,componentType:5123,count:24,type:'SCALAR'},
    ],
    meshes:[{primitives:[{attributes:{POSITION:0},indices:1,mode:4}]}],
    nodes:[{mesh:0}],scenes:[{nodes:[0]}],scene:0,
  };
  let json = Buffer.from(JSON.stringify(gltf),'utf8');
  const jsonPad = (4 - (json.length % 4)) % 4;
  json = Buffer.concat([json, Buffer.alloc(jsonPad,0x20)]);
  const binPad = (4 - (bin.length % 4)) % 4;
  const paddedBin = Buffer.concat([bin,Buffer.alloc(binPad)]);
  const header=Buffer.alloc(12); header.write('glTF',0); header.writeUInt32LE(2,4); header.writeUInt32LE(12+8+json.length+8+paddedBin.length,8);
  const jh=Buffer.alloc(8);jh.writeUInt32LE(json.length,0);jh.writeUInt32LE(0x4e4f534a,4);
  const bh=Buffer.alloc(8);bh.writeUInt32LE(paddedBin.length,0);bh.writeUInt32LE(0x004e4942,4);
  return Buffer.concat([header,jh,json,bh,paddedBin]);
}

const report=analyzeGlb(makeFixture(),{specimenId:'fixture',sourceRef:'synthetic'});
assert.equal(report.summary.component_count,2);
assert.equal(report.summary.family_count,1);
assert.equal(report.summary.symmetry_pair_count,1);
assert.equal(report.summary.watertight_component_count,2);
assert.ok(report.components.every((c)=>c.family_id==='f0000'));
assert.match(archaeologyCsv(report),/component_id,specimen_id/);
assert.equal(explodeManifest(report).components.length,2);
console.log('[glb-archaeology-test] ok');
