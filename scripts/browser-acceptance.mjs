#!/usr/bin/env node
import { mkdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const args = process.argv.slice(2);
function value(name, fallback = '') {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] || '' : fallback;
}
function flag(name) { return args.includes(name); }
function requireValue(name) {
  const found = value(name);
  if (!found) {
    console.error('missing required ' + name);
    process.exit(1);
  }
  return found;
}

const url = requireValue('--url');
const outDir = value('--out', 'artifacts/browser-acceptance');
const waitMs = Number(value('--wait-ms', '800'));
const timeoutMs = Number(value('--timeout-ms', '90000'));
const width = Number(value('--width', '1280'));
const height = Number(value('--height', '960'));
const views = value('--views', 'front,left,top,right,back,fit').split(',').map((item) => item.trim()).filter(Boolean);
const expectParts = value('--expect-parts').split(',').map((item) => item.trim()).filter(Boolean);
const expectVisibleParts = value('--expect-visible-parts').split(',').map((item) => item.trim()).filter(Boolean);
const expectTankAssemblyContract = flag('--expect-tank-assembly-contract');
const expectCanvasPixels = flag('--expect-canvas-pixels');
const expectStateUrl = value('--expect-state-url');
const expectSrc = value('--expect-src');
const requireCloudUrl = flag('--require-cloud-url');
const failOnBlank = !flag('--allow-blank');
mkdirSync(outDir, { recursive: true });


async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('failed to fetch JSON ' + url + ': ' + response.status);
  return response.json();
}
async function fetchGlbJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('failed to fetch GLB ' + url + ': ' + response.status);
  const data = Buffer.from(await response.arrayBuffer());
  if (data.readUInt32LE(0) !== 0x46546c67 || data.readUInt32LE(4) !== 2) throw new Error('invalid GLB header from ' + url);
  let offset = 12;
  while (offset < data.length) {
    const length = data.readUInt32LE(offset);
    const type = data.readUInt32LE(offset + 4);
    offset += 8;
    const chunk = data.subarray(offset, offset + length);
    offset += length;
    if (type === 0x4e4f534a) return JSON.parse(chunk.toString('utf8').trim());
  }
  throw new Error('missing GLB JSON chunk from ' + url);
}
function nodeMeshBounds(glbJson) {
  const bounds = {};
  function meshBounds(meshIndex) {
    const mesh = glbJson.meshes?.[meshIndex];
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (const primitive of mesh?.primitives || []) {
      const accessor = glbJson.accessors?.[primitive.attributes?.POSITION];
      if (!accessor?.min || !accessor?.max) continue;
      for (let axis = 0; axis < 3; axis++) {
        min[axis] = Math.min(min[axis], accessor.min[axis]);
        max[axis] = Math.max(max[axis], accessor.max[axis]);
      }
    }
    if (min[0] === Infinity) return null;
    return { min, max, dim: max.map((value, axis) => value - min[axis]), center: max.map((value, axis) => (value + min[axis]) / 2) };
  }
  for (const node of glbJson.nodes || []) if (node.mesh !== undefined && node.name) bounds[node.name] = meshBounds(node.mesh);
  return bounds;
}

function assertTankAssemblyContract({ manifest, bounds, src }) {
  const contract = manifest.relationshipContracts || {};
  const requiredNodes = ['tank_hull', 'tank_turret_housing', 'tank_gun_barrel', 'perforated_barrel_mac'];
  for (const id of requiredNodes) if (!bounds[id]) throw new Error('cloud GLB missing measured bounds for ' + id + ' from ' + src);
  if (JSON.stringify(contract.tankForwardAxis) !== JSON.stringify([0, 0, -1])) throw new Error('cloud manifest does not declare tank-forward -Z');
  if (contract.turretMantletSharesGunAxis !== true || contract.coaxialMgSharesGunAxis !== true) throw new Error('cloud manifest is missing gun/mantlet/MG axis contract');
  if (contract.turretMustBeSeatedOnHull !== true || contract.barrelMustOverlapTurretFront !== true) throw new Error('cloud manifest is missing turret seating/front-overlap contract');
  const hullTop = bounds.tank_hull.max[1];
  const turretBottom = bounds.tank_turret_housing.min[1];
  const seatingOverlap = hullTop - turretBottom;
  if (!(seatingOverlap >= 0.003 && seatingOverlap <= 0.03)) throw new Error('cloud turret is not seated on hull roof; overlap=' + seatingOverlap.toFixed(6));
  const widthRatio = bounds.tank_turret_housing.dim[0] / bounds.tank_hull.dim[0];
  const lengthRatio = bounds.tank_turret_housing.dim[2] / bounds.tank_hull.dim[2];
  if (!(widthRatio <= contract.turretMaxWidthRatioOfHull)) throw new Error('cloud turret is too wide for hull; ratio=' + widthRatio.toFixed(3));
  if (!(lengthRatio <= contract.turretMaxLengthRatioOfHull)) throw new Error('cloud turret is too long for hull; ratio=' + lengthRatio.toFixed(3));
  const turretFrontZ = bounds.tank_turret_housing.min[2];
  if (!(bounds.tank_gun_barrel.min[2] < turretFrontZ && bounds.tank_gun_barrel.max[2] > turretFrontZ)) throw new Error('cloud main gun does not overlap turret front -Z plane');
  if (!(bounds.perforated_barrel_mac.min[2] < turretFrontZ && bounds.perforated_barrel_mac.max[2] > turretFrontZ)) throw new Error('cloud MG does not overlap turret front -Z plane');
  if (!(Math.abs(bounds.tank_gun_barrel.center[1] - bounds.perforated_barrel_mac.center[1]) < 0.04)) throw new Error('cloud MG is not vertically aligned with main gun');
  if (!(bounds.perforated_barrel_mac.center[0] > bounds.tank_gun_barrel.center[0] + 0.06)) throw new Error('cloud MG is not a visible side-offset coaxial barrel');
  return { contract, bounds, seatingOverlap, widthRatio, lengthRatio, turretFrontZ };
}

const browser = await chromium.launch({
  headless: true,
  args: [
    '--ignore-gpu-blocklist',
    '--enable-webgl',
    '--enable-webgl2',
    '--use-gl=swiftshader',
    '--use-angle=swiftshader',
    '--disable-dev-shm-usage',
    '--no-sandbox',
  ],
});
const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
const consoleMessages = [];
const pageErrors = [];
page.on('console', (message) => consoleMessages.push({ type: message.type(), text: message.text() }));
page.on('pageerror', (error) => pageErrors.push(String(error?.stack || error)));
let report;
try {
  const parsedUrl = new URL(url);
  if (requireCloudUrl && parsedUrl.origin !== 'https://valar05.github.io') throw new Error('expected GitHub Pages cloud URL, got ' + parsedUrl.origin);
  if (expectStateUrl && parsedUrl.searchParams.get('state') !== expectStateUrl) throw new Error('cloud URL state mismatch: expected ' + expectStateUrl + ' got ' + parsedUrl.searchParams.get('state'));
  await page.goto(url, { waitUntil: 'networkidle', timeout: timeoutMs });
  await page.waitForFunction(() => document.body.dataset.modelReady === 'true' || document.body.dataset.modelReady === 'error', null, { timeout: timeoutMs });
  const ready = await page.evaluate(() => ({
    dataset: document.body.dataset.modelReady,
    signal: window.__MODEL_VIEWER_LAB_READY || null,
    status: document.querySelector('[data-status]')?.textContent || '',
    domPartIds: [...document.querySelectorAll('.object-row .object-name')].map((button) => button.textContent || '').filter(Boolean),
    domVisiblePartIds: [...document.querySelectorAll('.object-row')].filter((row) => !row.classList.contains('is-hidden')).map((row) => row.querySelector('.object-name')?.textContent || '').filter(Boolean),
    webgl: (() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return { ok: false, reason: 'missing canvas' };
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      if (!gl) return { ok: false, reason: 'no webgl context' };
      return { ok: true, renderer: gl.getParameter(gl.RENDERER), vendor: gl.getParameter(gl.VENDOR) };
    })(),
  }));
  if (ready.dataset !== 'true') throw new Error('model did not become ready: ' + JSON.stringify(ready));
  const runtimeStateUrl = ready.signal?.stateUrl || parsedUrl.searchParams.get('state') || '';
  if (expectStateUrl && runtimeStateUrl !== expectStateUrl) throw new Error('runtime state URL mismatch: expected ' + expectStateUrl + ' got ' + runtimeStateUrl);
  if (expectSrc && ready.signal?.src !== expectSrc) throw new Error('runtime src mismatch: expected ' + expectSrc + ' got ' + ready.signal?.src);
  const partIds = new Set((ready.signal?.partIds?.length ? ready.signal.partIds : ready.domPartIds) || []);
  const visiblePartIds = new Set((ready.signal?.visiblePartIds?.length ? ready.signal.visiblePartIds : ready.domVisiblePartIds) || []);
  for (const part of expectParts) if (!partIds.has(part)) throw new Error('missing expected runtime part: ' + part + ' in ' + JSON.stringify([...partIds]));
  for (const part of expectVisibleParts) if (!visiblePartIds.has(part)) throw new Error('missing expected visible runtime part: ' + part + ' in ' + JSON.stringify([...visiblePartIds]));
  let tankAssemblyContract = null;
  if (expectTankAssemblyContract) {
    const stateJson = await fetchJson(runtimeStateUrl);
    const manifestUrl = ready.signal?.manifest || stateJson.manifest;
    const srcUrl = expectSrc || ready.signal?.src || stateJson.src;
    if (!manifestUrl) throw new Error('missing manifest URL for tank assembly contract');
    if (!srcUrl) throw new Error('missing src URL for tank assembly contract');
    const manifest = await fetchJson(manifestUrl);
    const glbJson = await fetchGlbJson(srcUrl);
    tankAssemblyContract = assertTankAssemblyContract({ manifest, bounds: nodeMeshBounds(glbJson), src: srcUrl });
  }
  const captures = [];
  for (const view of views) {
    const clicked = await page.evaluate((viewName) => {
      const button = document.querySelector(`[data-view=\"${viewName}\"]`);
      if (!(button instanceof HTMLButtonElement)) return false;
      button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
      return true;
    }, view);
    if (!clicked) throw new Error('missing camera button for ' + view);
    await page.waitForTimeout(waitMs);
    const png = path.join(outDir, `model-viewer-${view}.png`);
    await page.screenshot({ path: png, fullPage: false });
    const screenshotBytes = statSync(png).size;
    const canvasProbe = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return { ok: false, reason: 'missing canvas' };
      const rect = canvas.getBoundingClientRect();
      return { ok: true, width: canvas.width, height: canvas.height, rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } };
    });
    let canvasScreenshot = null;
    if (canvasProbe.ok) {
      const canvasElement = await page.$('canvas');
      if (canvasElement) {
        const canvasPng = path.join(outDir, `model-viewer-${view}-canvas.png`);
        await canvasElement.screenshot({ path: canvasPng });
        canvasScreenshot = { path: canvasPng, bytes: statSync(canvasPng).size };
      }
    }
    captures.push({ view, path: png, screenshotBytes, canvasProbe, canvasScreenshot });
    if (failOnBlank && screenshotBytes < 20000) {
      throw new Error(`blank or low-information screenshot for ${view}: ${screenshotBytes} bytes`);
    }
    if (expectCanvasPixels) {
      if (!canvasProbe.ok || !canvasScreenshot) throw new Error(`canvas screenshot probe failed for ${view}: ${JSON.stringify(canvasProbe)}`);
      if (canvasScreenshot.bytes < 120000) throw new Error(`blank or low-information canvas screenshot for ${view}: ${canvasScreenshot.bytes} bytes`);
    }
  }
  report = { ok: true, url, viewport: { width, height }, views, ready, tankAssemblyContract, captures, consoleMessages, pageErrors };
} catch (error) {
  const failurePng = path.join(outDir, 'failure.png');
  await page.screenshot({ path: failurePng, fullPage: false }).catch(() => {});
  report = { ok: false, url, error: String(error?.stack || error), failureScreenshot: failurePng, consoleMessages, pageErrors };
  process.exitCode = 1;
} finally {
  writeFileSync(path.join(outDir, 'browser-acceptance-report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close();
}
console.log(JSON.stringify(report, null, 2));
