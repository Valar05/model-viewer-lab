import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ledgerRoot = path.resolve(here, '..', 'ledger');

const specs = {
  'parts.csv': {
    id: 'part_id',
    required: ['part_id','specimen_id','parent_assembly','source_ref','source_component_ids','semantic_role','geometry_family','repeat_count','symmetry','keep_decision','canonical_part_id','treatment','variant_axes','confidence','notes'],
  },
  'genes.csv': {
    id: 'gene_id',
    required: ['gene_id','description','value_type','default_value','min_value','max_value','allowed_values','affected_assemblies','implementation_lane','units','notes'],
  },
  'experiments.csv': {
    id: 'experiment_id',
    required: ['experiment_id','specimen_id','parent_experiment_id','changed_genes','generation_lane','prompt_or_recipe','source_ref','result_ref','geometry_metrics','visual_judgment','outcome','failure_reason','created_at','notes'],
  },
};

function fail(message) {
  console.error(`[foundry-ledger] ${message}`);
  process.exitCode = 1;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i += 1; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n') { row.push(cell.replace(/\r$/, '')); rows.push(row); row = []; cell = ''; }
    else cell += ch;
  }
  if (quoted) throw new Error('unterminated quoted field');
  if (cell.length || row.length) { row.push(cell.replace(/\r$/, '')); rows.push(row); }
  return rows.filter((r) => !(r.length === 1 && r[0] === ''));
}

function load(name) {
  const full = path.join(ledgerRoot, name);
  if (!fs.existsSync(full)) { fail(`missing table: ${name}`); return { headers: [], records: [] }; }
  let rows;
  try { rows = parseCsv(fs.readFileSync(full, 'utf8')); }
  catch (error) { fail(`${name}: ${error.message}`); return { headers: [], records: [] }; }
  if (!rows.length) { fail(`${name}: empty file`); return { headers: [], records: [] }; }
  const headers = rows[0];
  const duplicateHeaders = headers.filter((h, i) => headers.indexOf(h) !== i);
  if (duplicateHeaders.length) fail(`${name}: duplicate columns: ${[...new Set(duplicateHeaders)].join(', ')}`);
  for (const required of specs[name].required) if (!headers.includes(required)) fail(`${name}: missing required column '${required}'`);
  const records = rows.slice(1).filter((r) => r.some((v) => v.trim() !== '')).map((values, rowIndex) => {
    if (values.length !== headers.length) fail(`${name}: row ${rowIndex + 2} has ${values.length} cells; expected ${headers.length}`);
    return Object.fromEntries(headers.map((h, i) => [h, values[i] ?? '']));
  });
  return { headers, records };
}

const tables = Object.fromEntries(Object.keys(specs).map((name) => [name, load(name)]));
const ids = {};
const stableId = /^[a-z0-9][a-z0-9._:-]*$/i;

for (const [name, spec] of Object.entries(specs)) {
  const seen = new Set();
  for (const [index, record] of tables[name].records.entries()) {
    const id = record[spec.id]?.trim();
    if (!id) { fail(`${name}: row ${index + 2} missing ${spec.id}`); continue; }
    if (!stableId.test(id)) fail(`${name}: invalid stable id '${id}'`);
    if (seen.has(id)) fail(`${name}: duplicate ${spec.id} '${id}'`);
    seen.add(id);
  }
  ids[name] = seen;
}

const allowed = {
  symmetry: new Set(['','none','center','left','right','bilateral','radial','repeated']),
  keep_decision: new Set(['','undecided','keep','reject','reference']),
  treatment: new Set(['','preserve','retopo','rebuild','instance','generate','texture-only','discard','inspect']),
  value_type: new Set(['','number','integer','boolean','enum','string']),
  implementation_lane: new Set(['','blender','meshy','texture','viewer','manual','hybrid']),
  outcome: new Set(['','planned','running','promoted','rejected','inconclusive']),
};

for (const [index, part] of tables['parts.csv'].records.entries()) {
  for (const field of ['symmetry','keep_decision','treatment']) if (!allowed[field].has(part[field])) fail(`parts.csv: row ${index + 2} invalid ${field} '${part[field]}'`);
  if (part.repeat_count && (!Number.isInteger(Number(part.repeat_count)) || Number(part.repeat_count) < 1)) fail(`parts.csv: row ${index + 2} repeat_count must be a positive integer`);
  if (part.confidence && (Number.isNaN(Number(part.confidence)) || Number(part.confidence) < 0 || Number(part.confidence) > 1)) fail(`parts.csv: row ${index + 2} confidence must be 0..1`);
  if (part.canonical_part_id && !ids['parts.csv'].has(part.canonical_part_id)) fail(`parts.csv: row ${index + 2} canonical_part_id '${part.canonical_part_id}' not found`);
  for (const gene of part.variant_axes.split(';').map((v) => v.trim()).filter(Boolean)) if (!ids['genes.csv'].has(gene)) fail(`parts.csv: row ${index + 2} variant gene '${gene}' not found`);
}

for (const [index, gene] of tables['genes.csv'].records.entries()) {
  for (const field of ['value_type','implementation_lane']) if (!allowed[field].has(gene[field])) fail(`genes.csv: row ${index + 2} invalid ${field} '${gene[field]}'`);
  if (gene.min_value && gene.max_value && Number(gene.min_value) > Number(gene.max_value)) fail(`genes.csv: row ${index + 2} min_value exceeds max_value`);
}

for (const [index, experiment] of tables['experiments.csv'].records.entries()) {
  if (!allowed.outcome.has(experiment.outcome)) fail(`experiments.csv: row ${index + 2} invalid outcome '${experiment.outcome}'`);
  if (experiment.parent_experiment_id && !ids['experiments.csv'].has(experiment.parent_experiment_id)) fail(`experiments.csv: row ${index + 2} parent experiment '${experiment.parent_experiment_id}' not found`);
  for (const gene of experiment.changed_genes.split(';').map((v) => v.trim()).filter(Boolean)) if (!ids['genes.csv'].has(gene)) fail(`experiments.csv: row ${index + 2} changed gene '${gene}' not found`);
}

if (!process.exitCode) {
  console.log(`[foundry-ledger] ok: ${tables['parts.csv'].records.length} parts, ${tables['genes.csv'].records.length} genes, ${tables['experiments.csv'].records.length} experiments`);
}
