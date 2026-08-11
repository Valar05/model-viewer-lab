import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function parseCsv(text) {
  const rows=[]; let row=[], cell='', quoted=false;
  for (let i=0;i<text.length;i+=1) {
    const ch=text[i];
    if (quoted) { if (ch==='"'&&text[i+1]==='"') {cell+='"';i+=1;} else if (ch==='"') quoted=false; else cell+=ch; }
    else if (ch==='"') quoted=true; else if (ch===',') {row.push(cell);cell='';} else if (ch==='\n') {row.push(cell.replace(/\r$/,''));rows.push(row);row=[];cell='';} else cell+=ch;
  }
  if (cell.length||row.length) {row.push(cell.replace(/\r$/,''));rows.push(row);}
  const clean=rows.filter((r)=>r.some((v)=>v!=='')); if (!clean.length) return [];
  const headers=clean[0]; return clean.slice(1).map((values)=>Object.fromEntries(headers.map((h,i)=>[h,values[i]??''])));
}

function readTable(root,name) { const p=path.join(root,name); return fs.existsSync(p)?parseCsv(fs.readFileSync(p,'utf8')):[]; }
function split(value) { return String(value||'').split(';').map((s)=>s.trim()).filter(Boolean); }
function parseJson(value,fallback={}) { if (!value) return fallback; try { return JSON.parse(value); } catch { return fallback; } }

export function compileFoundryPlan(ledgerRoot,{variantId=''}={}) {
  const tables={
    parts:readTable(ledgerRoot,'parts.csv'), genes:readTable(ledgerRoot,'genes.csv'), experiments:readTable(ledgerRoot,'experiments.csv'),
    specimens:readTable(ledgerRoot,'specimens.csv'), assemblies:readTable(ledgerRoot,'assemblies.csv'), variants:readTable(ledgerRoot,'variants.csv'),
    recipes:readTable(ledgerRoot,'recipes.csv'), materials:readTable(ledgerRoot,'materials.csv'),
  };
  const geneMap=Object.fromEntries(tables.genes.map((g)=>[g.gene_id,g]));
  const defaults=Object.fromEntries(tables.genes.map((g)=>[g.gene_id,g.default_value]));
  const variant=variantId?tables.variants.find((v)=>v.variant_id===variantId):null;
  if (variantId&&!variant) throw new Error(`variant '${variantId}' not found`);
  const geneValues={...defaults,...parseJson(variant?.gene_values_json,{})};
  const actions={preserve:[],retopo:[],rebuild:[],instance:[],generate:[],texture:[],discard:[],inspect:[],reference:[],undecided:[]};
  for (const part of tables.parts) {
    const decision=part.keep_decision||'undecided';
    const treatment=part.treatment||'inspect';
    const item={part_id:part.part_id,specimen_id:part.specimen_id,parent_assembly:part.parent_assembly,source_component_ids:split(part.source_component_ids),canonical_part_id:part.canonical_part_id,variant_axes:split(part.variant_axes),gene_values:Object.fromEntries(split(part.variant_axes).map((id)=>[id,geneValues[id]]).filter(([,v])=>v!==undefined)),notes:part.notes};
    if (decision==='reject'||treatment==='discard') actions.discard.push(item);
    else if (decision==='reference') actions.reference.push(item);
    else if (actions[treatment]) actions[treatment].push(item);
    else actions.inspect.push(item);
  }
  const unresolvedGenes=Object.keys(geneValues).filter((id)=>!geneMap[id]);
  return {
    schema_version:1, compiled_at:new Date().toISOString(), variant_id:variantId||null, variant_name:variant?.name||null,
    gene_values:geneValues, unresolved_genes:unresolvedGenes,
    action_counts:Object.fromEntries(Object.entries(actions).map(([k,v])=>[k,v.length])), actions,
    assemblies:tables.assemblies, recipes:tables.recipes, materials:tables.materials, specimens:tables.specimens,
    active_experiments:tables.experiments.filter((e)=>['planned','running','inconclusive'].includes(e.outcome)),
  };
}

if (process.argv[1] && path.resolve(process.argv[1])===path.resolve(fileURLToPath(import.meta.url))) {
  const here=path.dirname(fileURLToPath(import.meta.url)); const ledgerRoot=path.resolve(here,'..','..','ledger');
  const variantArg=process.argv.find((a)=>a.startsWith('--variant=')); const outArg=process.argv.find((a)=>a.startsWith('--out='));
  const variantId=variantArg?variantArg.slice('--variant='.length):''; const plan=compileFoundryPlan(ledgerRoot,{variantId});
  const text=JSON.stringify(plan,null,2)+'\n';
  if (outArg) { const out=path.resolve(outArg.slice('--out='.length)); fs.mkdirSync(path.dirname(out),{recursive:true});fs.writeFileSync(out,text); }
  else process.stdout.write(text);
}
