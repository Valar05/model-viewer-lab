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
const expectStateUrl = value('--expect-state-url');
const expectSrc = value('--expect-src');
const requireCloudUrl = flag('--require-cloud-url');
const failOnBlank = !flag('--allow-blank');
mkdirSync(outDir, { recursive: true });

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
      return { ok: true, width: canvas.width, height: canvas.height };
    });
    captures.push({ view, path: png, screenshotBytes, canvasProbe });
    if (failOnBlank && screenshotBytes < 20000) {
      throw new Error(`blank or low-information screenshot for ${view}: ${screenshotBytes} bytes`);
    }
  }
  report = { ok: true, url, viewport: { width, height }, views, ready, captures, consoleMessages, pageErrors };
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
