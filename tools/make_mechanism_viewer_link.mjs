#!/usr/bin/env node
import path from 'node:path';
import { pathToWorkspaceUrl } from './path_utils.mjs';

const args = process.argv.slice(2);
function value(name, fallback = '') {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] || '' : fallback;
}
function rawGitHubUrl(repo, branch, filePath) {
  if (!filePath) return '';
  if (filePath.startsWith('http://') || filePath.startsWith('https://')) return filePath;
  return 'https://raw.githubusercontent.com/' + repo.replace(/^https:\/\/github\.com\//, '').replace(/\.git$/, '') + '/' + encodeURIComponent(branch).replace(/%2F/g, '/') + '/' + filePath.replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');
}

const mechanism = value('--mechanism', 'labs/hard-surface-factory/mechanisms/tread-system-v1/mechanism.json');
const title = value('--title', path.basename(path.dirname(mechanism)) || 'mechanism');
const local = args.includes('--local');
const assetRepo = value('--asset-repo', 'Valar05/model-viewer-lab');
const branch = value('--branch', 'main');
const viewerBase = value('--viewer-base', local ? 'http://127.0.0.1:8798/model-viewer-lab/dist/mechanism-viewer.html' : 'https://valar05.github.io/model-viewer-lab/mechanism-viewer.html');

const url = new URL(viewerBase);
if (local && mechanism.startsWith('/')) url.searchParams.set('mechanism', pathToWorkspaceUrl(mechanism));
else if (local) url.searchParams.set('mechanism', '/model-viewer-lab/dist/' + mechanism.replace(/^\/+/, ''));
else url.searchParams.set('mechanism', rawGitHubUrl(assetRepo, branch, mechanism));
url.searchParams.set('title', title);
console.log(url.toString());
