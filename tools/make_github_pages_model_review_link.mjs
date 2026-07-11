#!/usr/bin/env node

const args = process.argv.slice(2);
function value(name, fallback = '') {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] || '' : fallback;
}
function requireValue(name) {
  const found = value(name);
  if (!found) {
    console.error('missing required ' + name);
    process.exit(1);
  }
  return found;
}
function rawGitHubUrl(repo, branch, filePath) {
  if (!filePath) return '';
  if (filePath.startsWith('http://') || filePath.startsWith('https://')) return filePath;
  return 'https://raw.githubusercontent.com/' + repo.replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '') + '/' + encodeURIComponent(branch).replace(/%2F/g, '/') + '/' + filePath.replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');
}

const assetRepo = requireValue('--asset-repo');
const branch = value('--branch', 'main');
const src = value('--src');
const manifest = value('--manifest');
const stateJson = value('--state-json');
const title = value('--title') || src.split('/').pop() || stateJson.split('/').pop() || 'model';
const viewerBase = value('--viewer-base', 'https://valar05.github.io/model-viewer-lab/model-viewer.html');

if (!src && !stateJson) {
  console.error('missing required --src or --state-json');
  process.exit(1);
}

const url = new URL(viewerBase);
if (stateJson) url.searchParams.set('state', rawGitHubUrl(assetRepo, branch, stateJson));
if (src) url.searchParams.set('src', rawGitHubUrl(assetRepo, branch, src));
if (manifest) url.searchParams.set('manifest', rawGitHubUrl(assetRepo, branch, manifest));
url.searchParams.set('title', title);
console.log(url.toString());
