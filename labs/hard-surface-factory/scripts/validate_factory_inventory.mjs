import fs from 'node:fs';
import path from 'node:path';

const labRoot = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const required = [
  'README.md',
  'PROJECT_ORIENTATION.md',
  'docs/research/measurement-driven-reconstruction.md',
  'docs/history/tank-upper-hull-investigation.md',
  'docs/provenance/source-assets.md',
  'source-assets/meshy-envelope-assembly-v1/meshy_hull_envelope.glb',
  'source-assets/meshy-envelope-assembly-v1/meshy_turret_kit_envelope.glb',
  'source-assets/meshy-envelope-assembly-v1/meshy_treads_envelope.glb',
  'source-assets/meshy-lowpoly-envelope-v1/lowpoly_hull_envelope.glb',
  'source-assets/meshy-lowpoly-envelope-v1/lowpoly_turret_envelope.glb',
  'source-assets/meshy-lowpoly-envelope-v1/lowpoly_treads_envelope.glb',
  'review-states/meshy-envelope-hull.json',
  'review-states/meshy-lowpoly-hull.json',
  'source-assets/meshy-component-kit-071716/kit_manifest.json',
  'source-assets/meshy-component-kit-071716/PROVENANCE.md',
  'review-states/meshy-component-kit-tank_hull.json',
  'review-states/meshy-component-kit-tank_turret_housing.json',
  'review-states/meshy-component-kit-tank_gun_barrel.json',
  'review-states/meshy-component-kit-perforated_barrel_mac.json',
  'review-states/meshy-component-kit-canteen_lid.json',
];

const bannedPathFragments = [
  '/assets/authored/',
  '/public/tftm/models/authored_',
  '/generated/cloud-visual-truth/',
  '__pycache__',
];
const bannedExtensions = ['.blend1', '.pyc'];
const bannedMarkdownTerms = ['garbage', 'shitty', 'kiddie', 'burger'];

function fail(message) {
  console.error(`[hard-surface-factory] ${message}`);
  process.exitCode = 1;
}
function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

for (const rel of required) {
  if (!fs.existsSync(path.join(labRoot, rel))) fail(`missing required file: ${rel}`);
}

const files = walk(labRoot);
const rels = files.map((file) => path.relative(labRoot, file).split(path.sep).join('/'));
const exporters = rels.filter((rel) => rel.startsWith('tools/exporters/') && rel.endsWith('.py'));
const reports = rels.filter((rel) => rel.startsWith('history/raw-reports/') && rel.endsWith('.json'));
const glbs = rels.filter((rel) => rel.endsWith('.glb'));
const sourceGlbs = glbs.filter((rel) => rel.startsWith('source-assets/'));
const generatedGlbs = glbs.filter((rel) => rel.startsWith('generated/'));

if (exporters.length < 40) fail(`expected at least 40 archived exporter scripts, found ${exporters.length}`);
if (reports.length < 100) fail(`expected at least 100 raw JSON reports, found ${reports.length}`);
if (sourceGlbs.length !== 11) fail(`expected exactly 11 source/reference GLBs, found ${sourceGlbs.length}`);
for (const rel of generatedGlbs) {
  if (!rel.startsWith('generated/upper-glacis-manufactured-v1/') && !rel.startsWith('generated/meshy-component-kit-positioning-study/')) {
    fail(`unexpected generated GLB outside approved evidence packages: ${rel}`);
  }
}

for (const rel of rels) {
  for (const fragment of bannedPathFragments) {
    if (`/${rel}`.includes(fragment)) fail(`banned path fragment in lab: ${rel}`);
  }
  for (const ext of bannedExtensions) {
    if (rel.endsWith(ext)) fail(`banned generated/backup file: ${rel}`);
  }
  if (rel.endsWith('.blend')) fail(`Blend candidate output should not be committed here: ${rel}`);
}

for (const rel of rels.filter((rel) => rel.endsWith('.md'))) {
  const body = fs.readFileSync(path.join(labRoot, rel), 'utf8').toLowerCase();
  for (const term of bannedMarkdownTerms) {
    if (body.includes(term)) fail(`opinion-heavy term '${term}' found in ${rel}`);
  }
}

const stateFiles = rels.filter((rel) => rel.startsWith('review-states/') && rel.endsWith('.json'));
for (const rel of stateFiles) {
  const state = JSON.parse(fs.readFileSync(path.join(labRoot, rel), 'utf8'));
  if (state.version !== 2) fail(`review state must be version 2: ${rel}`);
  if (!state.src || !state.src.startsWith('https://raw.githubusercontent.com/Valar05/model-viewer-lab/')) {
    fail(`review state src must be a raw GitHub URL: ${rel}`);
  }
}

if (!process.exitCode) {
  const kitManifestPath = path.join(labRoot, 'source-assets/meshy-component-kit-071716/kit_manifest.json');
  const kitManifest = JSON.parse(fs.readFileSync(kitManifestPath, 'utf8'));
  if (kitManifest.sourcePolicy?.productionTopology !== false || kitManifest.sourcePolicy?.finalAuthoredGeometry !== false) {
    fail('Meshy component kit must remain reference-only, not production/authored topology');
  }
  const canteen = kitManifest.components?.find((component) => component.id === 'canteen_lid');
  if (!canteen || canteen.category !== 'quarantined_hatch_candidate') {
    fail('Meshy component kit canteen_lid must remain quarantined');
  }
  console.log(`[hard-surface-factory] ok: ${exporters.length} exporters, ${reports.length} reports, ${sourceGlbs.length} source/reference GLBs, ${generatedGlbs.length} generated evidence GLBs, ${stateFiles.length} review states`);
}
