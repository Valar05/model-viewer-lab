#!/usr/bin/env node
import { mkdirSync, writeFileSync } from 'node:fs';
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
  await page.goto(url, { waitUntil: 'networkidle', timeout: timeoutMs });
  await page.waitForFunction(() => document.body.dataset.modelReady === 'true' || document.body.dataset.modelReady === 'error', null, { timeout: timeoutMs });
  const ready = await page.evaluate(() => ({
    dataset: document.body.dataset.modelReady,
    signal: window.__MODEL_VIEWER_LAB_READY || null,
    status: document.querySelector('[data-status]')?.textContent || '',
    webgl: (() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return { ok: false, reason: 'missing canvas' };
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      if (!gl) return { ok: false, reason: 'no webgl context' };
      return { ok: true, renderer: gl.getParameter(gl.RENDERER), vendor: gl.getParameter(gl.VENDOR) };
    })(),
  }));
  if (ready.dataset !== 'true') throw new Error('model did not become ready: ' + JSON.stringify(ready));
  const captures = [];
  for (const view of views) {
    await page.locator(`[data-view="${view}"]`).click({ timeout: 5000 });
    await page.waitForTimeout(waitMs);
    const png = path.join(outDir, `model-viewer-${view}.png`);
    await page.screenshot({ path: png, fullPage: false });
    const pixelProbe = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return { ok: false, reason: 'missing canvas' };
      const probe = document.createElement('canvas');
      probe.width = 32;
      probe.height = 32;
      const ctx = probe.getContext('2d', { willReadFrequently: true });
      if (!ctx) return { ok: false, reason: 'missing 2d context' };
      ctx.drawImage(canvas, 0, 0, 32, 32);
      const data = ctx.getImageData(0, 0, 32, 32).data;
      let nonTransparent = 0;
      const colors = new Set();
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] > 0) nonTransparent += 1;
        colors.add(`${data[i]},${data[i + 1]},${data[i + 2]},${data[i + 3]}`);
      }
      return { ok: true, nonTransparent, uniqueColors: colors.size };
    });
    captures.push({ view, path: png, pixelProbe });
    if (failOnBlank && (!pixelProbe.ok || pixelProbe.uniqueColors < 4 || pixelProbe.nonTransparent < 128)) {
      throw new Error(`blank or low-information canvas for ${view}: ${JSON.stringify(pixelProbe)}`);
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
