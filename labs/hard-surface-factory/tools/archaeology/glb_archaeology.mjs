import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const COMPONENT_INFO = {
  5120: { bytes: 1, method: 'getInt8' },
  5121: { bytes: 1, method: 'getUint8' },
  5122: { bytes: 2, method: 'getInt16' },
  5123: { bytes: 2, method: 'getUint16' },
  5125: { bytes: 4, method: 'getUint32' },
  5126: { bytes: 4, method: 'getFloat32' },
};
const TYPE_COMPONENTS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };

export function parseGlb(buffer) {
  if (buffer.length < 20 || buffer.toString('ascii', 0, 4) !== 'glTF') throw new Error('expected GLB magic');
  const version = buffer.readUInt32LE(4);
  if (version !== 2) throw new Error(`unsupported GLB version ${version}`);
  const declaredLength = buffer.readUInt32LE(8);
  if (declaredLength !== buffer.length) throw new Error(`GLB length mismatch: header=${declaredLength}, bytes=${buffer.length}`);
  let offset = 12;
  let json = null;
  const binaryChunks = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    offset += 8;
    const chunk = buffer.subarray(offset, offset + length);
    offset += length;
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString('utf8').trim());
    else if (type === 0x004e4942) binaryChunks.push(chunk);
  }
  if (!json) throw new Error('GLB has no JSON chunk');
  if (!binaryChunks.length) throw new Error('GLB has no BIN chunk');
  return { json, bin: binaryChunks[0] };
}

function accessorValues(gltf, bin, accessorIndex) {
  const accessor = gltf.accessors?.[accessorIndex];
  if (!accessor) throw new Error(`missing accessor ${accessorIndex}`);
  const view = gltf.bufferViews?.[accessor.bufferView];
  if (!view) throw new Error(`accessor ${accessorIndex} missing bufferView`);
  const info = COMPONENT_INFO[accessor.componentType];
  const width = TYPE_COMPONENTS[accessor.type];
  if (!info || !width) throw new Error(`unsupported accessor format ${accessor.componentType}/${accessor.type}`);
  const stride = view.byteStride || info.bytes * width;
  const base = (view.byteOffset || 0) + (accessor.byteOffset || 0);
  const dv = new DataView(bin.buffer, bin.byteOffset, bin.byteLength);
  const out = new Array(accessor.count);
  for (let i = 0; i < accessor.count; i += 1) {
    const row = new Array(width);
    for (let j = 0; j < width; j += 1) row[j] = dv[info.method](base + i * stride + j * info.bytes, true);
    out[i] = width === 1 ? row[0] : row;
  }
  return out;
}

class UnionFind {
  constructor(n) { this.parent = Array.from({ length: n }, (_, i) => i); this.rank = new Uint8Array(n); }
  find(x) { let p = x; while (this.parent[p] !== p) p = this.parent[p]; while (this.parent[x] !== x) { const n = this.parent[x]; this.parent[x] = p; x = n; } return p; }
  union(a, b) { let ra = this.find(a); let rb = this.find(b); if (ra === rb) return; if (this.rank[ra] < this.rank[rb]) [ra, rb] = [rb, ra]; this.parent[rb] = ra; if (this.rank[ra] === this.rank[rb]) this.rank[ra] += 1; }
}

const add = (a,b) => a.map((v,i)=>v+b[i]);
const sub = (a,b) => a.map((v,i)=>v-b[i]);
const mul = (a,s) => a.map((v)=>v*s);
const norm = (a) => Math.hypot(...a);
const round = (n,d=6) => Number(n.toFixed(d));
const roundVec = (v,d=6) => v.map((n)=>round(n,d));

function triangleArea(a,b,c) {
  const ab=sub(b,a), ac=sub(c,a);
  const cross=[ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0]];
  return norm(cross)*0.5;
}

function familyKey(component) {
  const dims=[...component.dimensions].sort((a,b)=>a-b);
  const scale=Math.max(dims[2], 1e-9);
  const ratios=dims.map((d)=>round(d/scale,1));
  return `${component.vertex_count}:${component.triangle_count}:${ratios.join(':')}`;
}

function spatialCell(centroid, center) {
  const lr = centroid[0] < center[0] ? 'left' : centroid[0] > center[0] ? 'right' : 'center';
  const vh = centroid[1] < center[1] ? 'low' : centroid[1] > center[1] ? 'high' : 'mid';
  const fr = centroid[2] < center[2] ? 'rear' : centroid[2] > center[2] ? 'front' : 'mid';
  return `${lr}.${vh}.${fr}`;
}

function analyzePrimitive({ positions, indices, primitiveIndex, meshIndex, modelCenter }) {
  if (indices.length % 3 !== 0) throw new Error(`primitive ${meshIndex}/${primitiveIndex} index count is not triangles`);
  const uf=new UnionFind(positions.length);
  const triangles=[];
  for (let i=0;i<indices.length;i+=3) {
    const tri=[indices[i],indices[i+1],indices[i+2]];
    triangles.push(tri);
    uf.union(tri[0],tri[1]); uf.union(tri[1],tri[2]); uf.union(tri[2],tri[0]);
  }
  const verticesByRoot=new Map();
  for (let i=0;i<positions.length;i+=1) { const r=uf.find(i); if (!verticesByRoot.has(r)) verticesByRoot.set(r,[]); verticesByRoot.get(r).push(i); }
  const trianglesByRoot=new Map();
  for (const tri of triangles) { const r=uf.find(tri[0]); if (!trianglesByRoot.has(r)) trianglesByRoot.set(r,[]); trianglesByRoot.get(r).push(tri); }
  const sorted=[...verticesByRoot.entries()].sort((a,b)=>Math.min(...a[1])-Math.min(...b[1]));
  const components=[];
  for (let seq=0;seq<sorted.length;seq+=1) {
    const [root, vertexIds]=sorted[seq];
    const tris=trianglesByRoot.get(root) || [];
    const min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity], sum=[0,0,0];
    for (const vi of vertexIds) {
      const p=positions[vi];
      for (let k=0;k<3;k+=1) { min[k]=Math.min(min[k],p[k]); max[k]=Math.max(max[k],p[k]); sum[k]+=p[k]; }
    }
    const centroid=sum.map((x)=>x/vertexIds.length);
    const dimensions=sub(max,min);
    const edges=new Map();
    let area=0;
    for (const tri of tris) {
      area += triangleArea(positions[tri[0]],positions[tri[1]],positions[tri[2]]);
      for (const [a,b] of [[tri[0],tri[1]],[tri[1],tri[2]],[tri[2],tri[0]]]) {
        const key=a<b?`${a}:${b}`:`${b}:${a}`;
        edges.set(key,(edges.get(key)||0)+1);
      }
    }
    const boundary=[...edges.values()].filter((n)=>n===1).length;
    const nonmanifold=[...edges.values()].filter((n)=>n>2).length;
    const delta=sub(centroid,modelCenter); const d=norm(delta); const explode=d>1e-9?mul(delta,1/d):[0,1,0];
    components.push({
      component_id:`m${meshIndex}p${primitiveIndex}c${String(seq).padStart(4,'0')}`,
      mesh_index:meshIndex, primitive_index:primitiveIndex, first_vertex:Math.min(...vertexIds),
      vertex_count:vertexIds.length, triangle_count:tris.length,
      bounds_min:roundVec(min), bounds_max:roundVec(max), centroid:roundVec(centroid), dimensions:roundVec(dimensions),
      surface_area:round(area,8), boundary_edges:boundary, nonmanifold_edges:nonmanifold,
      watertight:boundary===0&&nonmanifold===0, spatial_cell:spatialCell(centroid,modelCenter), explode_vector:roundVec(explode),
    });
  }
  return components;
}

function pairSymmetry(components, axis=0, tolerance=0.08) {
  const pairs=[]; const used=new Set();
  const scale=Math.max(...components.flatMap((c)=>c.dimensions),1e-9);
  for (let i=0;i<components.length;i+=1) {
    if (used.has(i)) continue;
    const a=components[i]; let best=-1, bestScore=Infinity;
    for (let j=i+1;j<components.length;j+=1) {
      if (used.has(j)) continue; const b=components[j];
      const mirrored=[...a.centroid]; mirrored[axis]*=-1;
      const cd=norm(sub(mirrored,b.centroid))/scale;
      const dd=norm(sub(a.dimensions,b.dimensions))/scale;
      const topology=Math.abs(a.vertex_count-b.vertex_count)/Math.max(a.vertex_count,b.vertex_count,1)+Math.abs(a.triangle_count-b.triangle_count)/Math.max(a.triangle_count,b.triangle_count,1);
      const score=cd+dd+topology*0.25;
      if (score<bestScore) { bestScore=score; best=j; }
    }
    if (best>=0 && bestScore<=tolerance) { used.add(i);used.add(best);pairs.push({a:a.component_id,b:components[best].component_id,score:round(bestScore,5),axis:['x','y','z'][axis]}); }
  }
  return pairs;
}

export function analyzeGlb(buffer,{specimenId='specimen',sourceRef=''}={}) {
  const {json:gltf,bin}=parseGlb(buffer);
  const allPositions=[];
  for (const mesh of gltf.meshes||[]) for (const primitive of mesh.primitives||[]) {
    if (primitive.attributes?.POSITION !== undefined) allPositions.push(...accessorValues(gltf,bin,primitive.attributes.POSITION));
  }
  if (!allPositions.length) throw new Error('no POSITION data');
  const modelMin=[Infinity,Infinity,Infinity], modelMax=[-Infinity,-Infinity,-Infinity];
  for (const p of allPositions) for (let k=0;k<3;k+=1) { modelMin[k]=Math.min(modelMin[k],p[k]);modelMax[k]=Math.max(modelMax[k],p[k]); }
  const modelCenter=mul(add(modelMin,modelMax),0.5);
  const components=[];
  let primitiveCount=0, triangleCount=0, vertexCount=0;
  (gltf.meshes||[]).forEach((mesh,meshIndex)=>(mesh.primitives||[]).forEach((primitive,primitiveIndex)=>{
    if (primitive.mode !== undefined && primitive.mode !== 4) return;
    if (primitive.attributes?.POSITION === undefined || primitive.indices === undefined) return;
    const positions=accessorValues(gltf,bin,primitive.attributes.POSITION);
    const indices=accessorValues(gltf,bin,primitive.indices);
    primitiveCount+=1; triangleCount+=indices.length/3; vertexCount+=positions.length;
    components.push(...analyzePrimitive({positions,indices,primitiveIndex,meshIndex,modelCenter}));
  }));
  const familiesMap=new Map();
  for (const c of components) { const key=familyKey(c); if (!familiesMap.has(key)) familiesMap.set(key,[]); familiesMap.get(key).push(c.component_id); }
  const families=[...familiesMap.entries()].filter(([,ids])=>ids.length>1).sort((a,b)=>b[1].length-a[1].length).map(([key,ids],i)=>({family_id:`f${String(i).padStart(4,'0')}`,fingerprint:key,count:ids.length,component_ids:ids}));
  const familyByComponent=new Map(); for (const f of families) for (const id of f.component_ids) familyByComponent.set(id,f.family_id);
  for (const c of components) c.family_id=familyByComponent.get(c.component_id)||'';
  const symmetry_pairs=pairSymmetry(components,0,0.08);
  const hash=crypto.createHash('sha256').update(buffer).digest('hex');
  return {
    schema_version:1, specimen_id:specimenId, source_ref:sourceRef, sha256:hash,
    generator:gltf.asset?.generator||'', gltf_version:gltf.asset?.version||'', bytes:buffer.length,
    summary:{mesh_count:(gltf.meshes||[]).length,primitive_count:primitiveCount,vertex_count:vertexCount,triangle_count:triangleCount,component_count:components.length,family_count:families.length,symmetry_pair_count:symmetry_pairs.length,watertight_component_count:components.filter((c)=>c.watertight).length},
    bounds:{min:roundVec(modelMin),max:roundVec(modelMax),center:roundVec(modelCenter),dimensions:roundVec(sub(modelMax,modelMin))},
    components,families,symmetry_pairs,
  };
}

function csvCell(value) { const s=String(value??''); return /[",\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s; }
export function archaeologyCsv(report) {
  const headers=['component_id','specimen_id','source_ref','mesh_index','primitive_index','first_vertex','vertex_count','triangle_count','family_id','spatial_cell','centroid_x','centroid_y','centroid_z','size_x','size_y','size_z','surface_area','boundary_edges','nonmanifold_edges','watertight','explode_x','explode_y','explode_z'];
  const rows=[headers];
  for (const c of report.components) rows.push([c.component_id,report.specimen_id,report.source_ref,c.mesh_index,c.primitive_index,c.first_vertex,c.vertex_count,c.triangle_count,c.family_id,c.spatial_cell,...c.centroid,...c.dimensions,c.surface_area,c.boundary_edges,c.nonmanifold_edges,c.watertight,...c.explode_vector]);
  return rows.map((r)=>r.map(csvCell).join(',')).join('\n')+'\n';
}

export function explodeManifest(report) {
  return {schema_version:1,specimen_id:report.specimen_id,source_ref:report.source_ref,default_factor:1.0,components:report.components.map((c)=>({id:c.component_id,centroid:c.centroid,explode_vector:c.explode_vector,family_id:c.family_id,spatial_cell:c.spatial_cell}))};
}

function parseArgs(argv) {
  const out={}; for (let i=0;i<argv.length;i+=1) { const a=argv[i]; if (a.startsWith('--')) { const k=a.slice(2); out[k]=argv[i+1]&&!argv[i+1].startsWith('--')?argv[++i]:true; } }
  return out;
}

if (process.argv[1] && path.resolve(process.argv[1])===path.resolve(new URL(import.meta.url).pathname)) {
  const args=parseArgs(process.argv.slice(2));
  if (!args.input) { console.error('usage: node glb_archaeology.mjs --input model.glb [--specimen id] [--source-ref ref] [--out-dir dir]'); process.exit(2); }
  const input=fs.readFileSync(args.input); const specimenId=args.specimen||path.basename(args.input,path.extname(args.input)); const sourceRef=args['source-ref']||args.input;
  const report=analyzeGlb(input,{specimenId,sourceRef}); const outDir=args['out-dir']||path.join(path.dirname(args.input),`${specimenId}.archaeology`); fs.mkdirSync(outDir,{recursive:true});
  fs.writeFileSync(path.join(outDir,'report.json'),JSON.stringify(report,null,2)+'\n'); fs.writeFileSync(path.join(outDir,'components.csv'),archaeologyCsv(report)); fs.writeFileSync(path.join(outDir,'explode.json'),JSON.stringify(explodeManifest(report),null,2)+'\n');
  console.log(JSON.stringify({ok:true,out_dir:outDir,...report.summary,sha256:report.sha256},null,2));
}
