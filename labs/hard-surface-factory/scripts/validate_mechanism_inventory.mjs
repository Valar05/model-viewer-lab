import fs from 'node:fs';
import path from 'node:path';

const labRoot = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const mechanismPath = path.join(labRoot, 'mechanisms', 'tread-system-v1', 'mechanism.json');
function fail(message) {
  console.error(`[mechanisms] ${message}`);
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
function assertNumber(object, key, min, max) {
  const value = object[key];
  if (!Number.isFinite(value) || value < min || value > max) fail(`${key} out of range: ${value}`);
}

if (!fs.existsSync(mechanismPath)) fail('missing tread-system-v1 mechanism.json');
else {
  const mech = JSON.parse(fs.readFileSync(mechanismPath, 'utf8'));
  if (mech.schemaVersion !== 1) fail('schemaVersion must be 1');
  if (mech.id !== 'tread-system-v1') fail('unexpected mechanism id');
  if (mech.forwardAxis !== '+z') fail('forwardAxis must be +z for tank-local controls');
  for (const key of ['trackGauge', 'trackWidth', 'trackLength', 'bottomY', 'topY', 'hullWidth', 'hullLength', 'hullHeight']) assertNumber(mech.dimensions, key, 0.01, 10);
  if (mech.dimensions.topY <= mech.dimensions.bottomY) fail('topY must be above bottomY');
  assertNumber(mech.tread, 'linksPerSide', 12, 240);
  assertNumber(mech.tread, 'shoeWidth', 0.01, 2);
  assertNumber(mech.tread, 'shoeLength', 0.01, 2);
  assertNumber(mech.tread, 'shoeThickness', 0.005, 1);
  assertNumber(mech.simulation, 'driveSpeed', 0.01, 10);
  assertNumber(mech.simulation, 'yawSpeed', 0.01, 10);
  assertNumber(mech.simulation, 'trackVisualSpeed', 0.01, 20);
  assertNumber(mech.simulation, 'joystickDeadzone', 0, 0.4);
}

const rels = walk(labRoot).map((file) => path.relative(labRoot, file).split(path.sep).join('/'));
for (const rel of rels) {
  if (rel.includes('__pycache__') || rel.endsWith('.pyc') || rel.endsWith('.blend1')) fail(`generated file should not be committed: ${rel}`);
}
if (!process.exitCode) console.log('[mechanisms] ok: tread-system-v1 inventory valid');
