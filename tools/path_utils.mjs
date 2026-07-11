import path from 'node:path';

export const workspaceRoot = '/storage/emulated/0/Documents/GodotProjects';

function encodePathParts(value) {
  return value.split('/').map((part, index) => index === 0 ? '' : encodeURIComponent(part)).join('/');
}

export function pathToWorkspaceUrl(input) {
  if (!input) return '';
  if (input.startsWith('http://') || input.startsWith('https://')) return input;
  if (input.startsWith(workspaceRoot + '/')) return encodePathParts('/' + input.slice(workspaceRoot.length + 1));
  if (input.startsWith('/')) return encodePathParts(input);
  const absolute = path.resolve(process.cwd(), input);
  if (absolute.startsWith(workspaceRoot + '/')) return encodePathParts('/' + absolute.slice(workspaceRoot.length + 1));
  return encodePathParts('/' + path.relative(workspaceRoot, absolute).split(path.sep).join('/'));
}

export function viewerPathForDist() {
  return '/model-viewer-lab/dist/model-viewer.html';
}
