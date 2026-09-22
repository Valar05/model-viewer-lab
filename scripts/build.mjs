import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { brotliDecompressSync } from 'node:zlib';
import { textureOutlawGlb } from './outlaw-semantic-texture.mjs';

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
  const sourceBuffers = sourceParts.map((rel) => {
    const bytes = readFileSync(path.join(root, rel));
    return rel.endsWith('.b64') ? Buffer.from(bytes.toString('utf8').trim(), 'base64') : bytes;
  });
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
  return glb;
}

function publishTexturedOutlawModel({ source, outputName, expectedSha256, expectedBytes }) {
  const glb = textureOutlawGlb(source);
  const actualSha256 = sha256(glb);
  if (glb.length !== expectedBytes || actualSha256 !== expectedSha256) {
    throw new Error(
      'Outlaw semantic albedo mismatch for ' + outputName +
      ': bytes=' + glb.length + '/' + expectedBytes +
      ' sha256=' + actualSha256 + '/' + expectedSha256
    );
  }
  const outputDir = path.join(distDir, 'models', 'outlaw');
  mkdirSync(outputDir, { recursive: true });
  writeFileSync(path.join(outputDir, outputName), glb);
  return glb;
}

await bundle('model-viewer');
await bundle('mechanism-viewer');
writeHtml('model-viewer.html', 'model-viewer.html', 'model-viewer');
writeHtml('mechanism-viewer.html', 'mechanism-viewer.html', 'mechanism-viewer');
copyFileSync(path.join(root, 'README.md'), path.join(distDir, 'README.md'));

const outlawBefore = publishOutlawModel({
  sourceParts: ['models/outlaw-source/Outlaw_Complete_WideTires_CLEAN.glb.br'],
  outputName: 'Outlaw_Complete_WideTires_CLEAN.glb',
  expectedBytes: 65832,
  expectedSha256: '468d50db3157045fbfa016a71509ade836ec5833aa4abeb892864637546065e1'
});

const outlawAfter = publishOutlawModel({
  sourceParts: [
    'models/outlaw-source/Outlaw_Complete_Clearance_CLEAN.glb.br.part0',
    'models/outlaw-source/Outlaw_Complete_Clearance_CLEAN.glb.br.part1'
  ],
  outputName: 'Outlaw_Complete_Clearance_CLEAN.glb',
  expectedBytes: 78692,
  expectedSha256: '6fc17cd21524fef4d3756afc9e01a8a88b840c1ab9a54f2a6a44ef7f755786cb'
});

const outlawFactoryBase = publishOutlawModel({
  sourceParts: ['models/outlaw-source/Outlaw_Factory_Base_WideTires_CLEAN.glb.br.b64'],
  outputName: 'Outlaw_Factory_Base_WideTires_CLEAN.glb',
  expectedBytes: 59076,
  expectedSha256: 'ae1c1f3aabfc1ad261aa5a0853b85bc1505969f83ef929eb1a654714bbc044f1'
});

publishTexturedOutlawModel({
  source: outlawBefore,
  outputName: 'Outlaw_Complete_WideTires_TEXTURED.glb',
  expectedBytes: 71924,
  expectedSha256: 'ed49c6b37ddbb99b9a2fc64afb6deca8ea923e09a377617c02eccba90316ac80'
});
publishTexturedOutlawModel({
  source: outlawAfter,
  outputName: 'Outlaw_Complete_Clearance_TEXTURED.glb',
  expectedBytes: 88588,
  expectedSha256: 'bb0a48eb60e0a8b1db9a0dc42be4e9d7cef0173ca54fb9bcdd1c46326f6cf7ef'
});
publishTexturedOutlawModel({
  source: outlawFactoryBase,
  outputName: 'Outlaw_Factory_Base_WideTires_TEXTURED.glb',
  expectedBytes: 65612,
  expectedSha256: 'c1ce0e45da7b9dbbeb772c2fbe5b54feb50d3dc9ba71c1981b06e7e87b35cdcc'
});

const mechanismSource = path.join(root, 'labs', 'hard-surface-factory', 'mechanisms');
if (existsSync(mechanismSource)) {
  cpSync(mechanismSource, path.join(distDir, 'labs', 'hard-surface-factory', 'mechanisms'), { recursive: true });
}

console.log('Built model-viewer-lab dist with provenance-locked Outlaw sources and deterministic semantic albedo outputs.');
