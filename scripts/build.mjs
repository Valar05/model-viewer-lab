import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { brotliDecompressSync } from 'node:zlib';

const require = createRequire(import.meta.url);
let esbuild;
try {
  esbuild = require('esbuild-wasm');
} catch (_err) {
  esbuild = require('../../tanks-for-the-memories/node_modules/esbuild-wasm');
}

const root = process.cwd();
const srcDir = path.join(root, 'src');
const distDir = path.join(root, 'dist');
const assetsDir = path.join(distDir, 'assets');
const fallbackNodeModules = path.resolve(root, '../tanks-for-the-memories/node_modules');
const assetVersion = process.env.MODEL_VIEWER_ASSET_VERSION || String(Date.now());

rmSync(distDir, { recursive: true, force: true });
mkdirSync(assetsDir, { recursive: true });

function resolveExisting(candidates) {
  for (const candidate of candidates) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

function resolveImport(importPath, resolveDir) {
  const base = path.resolve(resolveDir, importPath);
  const ext = path.extname(base);
  return resolveExisting(ext ? [base] : [base, base + '.ts', base + '.tsx', base + '.js', base + '.jsx', base + '.css']);
}

function modulePath(...segments) {
  const local = path.join(root, 'node_modules', ...segments);
  if (existsSync(local)) return local;
  return path.join(fallbackNodeModules, ...segments);
}

function resolver() {
  return {
    name: 'workspace-local-resolver',
    setup(build) {
      build.onResolve({ filter: new RegExp('^three$') }, () => ({ path: modulePath('three', 'build', 'three.module.js') }));
      build.onResolve({ filter: new RegExp('^three/examples/jsm/loaders/GLTFLoader\\.js$') }, () => ({ path: modulePath('three', 'examples', 'jsm', 'loaders', 'GLTFLoader.js') }));
      build.onResolve({ filter: new RegExp('^three/examples/jsm/controls/OrbitControls\\.js$') }, () => ({ path: modulePath('three', 'examples', 'jsm', 'controls', 'OrbitControls.js') }));
      build.onResolve({ filter: new RegExp('^\\.|^/') }, (args) => {
        const resolved = resolveImport(args.path, args.resolveDir);
        if (!resolved) return { errors: [{ text: 'Could not resolve ' + args.path + ' from ' + args.resolveDir }] };
        return { path: resolved };
      });
      build.onLoad({ filter: new RegExp('\\.(ts|tsx|js|jsx)$') }, (args) => ({
        contents: readFileSync(args.path, 'utf8'),
        loader: path.extname(args.path).slice(1) === 'ts' ? 'ts' : path.extname(args.path).slice(1) === 'tsx' ? 'tsx' : 'js'
      }));
      build.onLoad({ filter: new RegExp('\\.css$') }, (args) => ({ contents: readFileSync(args.path, 'utf8'), loader: 'css' }));
    }
  };
}

async function bundle(entry) {
  await esbuild.build({
    stdin: {
      contents: readFileSync(path.join(srcDir, entry + '.ts'), 'utf8'),
      resolveDir: srcDir,
      sourcefile: entry + '.ts',
      loader: 'ts'
    },
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: 'es2022',
    outdir: assetsDir,
    entryNames: entry,
    loader: { '.css': 'css' },
    write: true,
    plugins: [resolver()]
  });
}

function writeHtml(sourceHtml, outputHtml, entry) {
  const html = readFileSync(path.join(root, sourceHtml), 'utf8')
    .replace('</head>', '    <link rel="stylesheet" href="./assets/' + entry + '.css?v=' + assetVersion + '" />' + '\n  </head>')
    .replace(new RegExp('<script type="module" src="[^"]+"></script>'), '<script type="module" src="./assets/' + entry + '.js?v=' + assetVersion + '"></script>');
  writeFileSync(path.join(distDir, outputHtml), html);
}

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function publishOutlawModel({ sourceParts, outputName, expectedSha256, expectedBytes }) {
  const sourceBuffers = sourceParts.map((rel) => readFileSync(path.join(root, rel)));
  const compressed = Buffer.concat(sourceBuffers);
  const glb = brotliDecompressSync(compressed);
  const actualSha256 = sha256(glb);
  if (glb.length !== expectedBytes || actualSha256 !== expectedSha256) {
    throw new Error(
      'Outlaw model provenance mismatch for ' + outputName +
      ': bytes=' + glb.length + '/' + expectedBytes +
      ' sha256=' + actualSha256 + '/' + expectedSha256
    );
  }
  const outputDir = path.join(distDir, 'models', 'outlaw');
  mkdirSync(outputDir, { recursive: true });
  writeFileSync(path.join(outputDir, outputName), glb);
}

await bundle('model-viewer');
await bundle('mechanism-viewer');
writeHtml('model-viewer.html', 'model-viewer.html', 'model-viewer');
writeHtml('mechanism-viewer.html', 'mechanism-viewer.html', 'mechanism-viewer');
copyFileSync(path.join(root, 'README.md'), path.join(distDir, 'README.md'));

publishOutlawModel({
  sourceParts: ['models/outlaw-source/Outlaw_Complete_WideTires_CLEAN.glb.br'],
  outputName: 'Outlaw_Complete_WideTires_CLEAN.glb',
  expectedBytes: 65832,
  expectedSha256: '468d50db3157045fbfa016a71509ade836ec5833aa4abeb892864637546065e1'
});

publishOutlawModel({
  sourceParts: [
    'models/outlaw-source/Outlaw_Complete_Clearance_CLEAN.glb.br.part0',
    'models/outlaw-source/Outlaw_Complete_Clearance_CLEAN.glb.br.part1'
  ],
  outputName: 'Outlaw_Complete_Clearance_CLEAN.glb',
  expectedBytes: 78692,
  expectedSha256: '6fc17cd21524fef4d3756afc9e01a8a88b840c1ab9a54f2a6a44ef7f755786cb'
});

const mechanismSource = path.join(root, 'labs', 'hard-surface-factory', 'mechanisms');
if (existsSync(mechanismSource)) {
  cpSync(mechanismSource, path.join(distDir, 'labs', 'hard-surface-factory', 'mechanisms'), { recursive: true });
}

console.log('Built model-viewer-lab dist using esbuild-wasm with verified Outlaw review models.');
