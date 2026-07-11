#!/usr/bin/env node
import { pathToWorkspaceUrl, viewerPathForDist } from './path_utils.mjs';

const args = process.argv.slice(2);
function value(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : '';
}
const src = value('--src');
if (!src) {
  console.error('Usage: node tools/make_model_viewer_link.mjs --src PATH_OR_URL [--manifest PATH_OR_URL] [--title TITLE] [--port 8798]');
  process.exit(1);
}
const manifest = value('--manifest');
const title = value('--title') || src.split('/').pop() || 'model';
const port = value('--port') || process.env.MODEL_VIEWER_PORT || '8798';
const url = new URL('http://127.0.0.1:' + port + viewerPathForDist());
url.searchParams.set('src', pathToWorkspaceUrl(src));
if (manifest) url.searchParams.set('manifest', pathToWorkspaceUrl(manifest));
url.searchParams.set('title', title);
console.log(url.toString());
