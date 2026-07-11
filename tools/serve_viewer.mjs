#!/usr/bin/env node
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { workspaceRoot, viewerPathForDist } from './path_utils.mjs';

const requestedPort = Number(process.env.PORT || process.argv.find((arg) => arg.startsWith('--port='))?.split('=')[1] || 8798);
const host = '0.0.0.0';
const mime = new Map([
  ['.html', 'text/html; charset=utf-8'], ['.js', 'text/javascript; charset=utf-8'], ['.css', 'text/css; charset=utf-8'], ['.json', 'application/json; charset=utf-8'],
  ['.glb', 'model/gltf-binary'], ['.gltf', 'model/gltf+json'], ['.bin', 'application/octet-stream'], ['.png', 'image/png'], ['.jpg', 'image/jpeg'], ['.jpeg', 'image/jpeg'], ['.webp', 'image/webp']
]);

function send(res, status, body, type = 'text/plain; charset=utf-8') {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store, max-age=0', 'access-control-allow-origin': '*' });
  res.end(body);
}

function fileForUrl(reqUrl) {
  const url = new URL(reqUrl, 'http://local');
  let pathname = decodeURIComponent(url.pathname);
  if (pathname === '/' || pathname === '/model-viewer-lab/') pathname = viewerPathForDist();
  const normalized = path.normalize(pathname).split(path.sep).filter(Boolean).join(path.sep);
  const filePath = path.join(workspaceRoot, normalized);
  if (!filePath.startsWith(workspaceRoot)) return null;
  return filePath;
}

function createServer() {
  return http.createServer((req, res) => {
    if (!req.url) return send(res, 400, 'missing url');
    if (req.method === 'OPTIONS') return send(res, 204, '');
    const filePath = fileForUrl(req.url);
    if (!filePath) return send(res, 403, 'outside workspace');
    fs.stat(filePath, (err, stat) => {
      if (err || !stat.isFile()) return send(res, 404, 'not found: ' + filePath);
      const ext = path.extname(filePath).toLowerCase();
      res.writeHead(200, { 'content-type': mime.get(ext) || 'application/octet-stream', 'cache-control': 'no-store, max-age=0', 'access-control-allow-origin': '*' });
      fs.createReadStream(filePath).pipe(res);
    });
  });
}

function listen(port) {
  const server = createServer();
  server.once('error', (err) => {
    server.close();
    if (err.code === 'EADDRINUSE' && port < requestedPort + 20) return listen(port + 1);
    console.error(err);
    process.exit(1);
  });
  server.listen(port, host, () => {
    console.log('Model Viewer Lab serving ' + workspaceRoot);
    console.log('Viewer: http://127.0.0.1:' + port + viewerPathForDist());
  });
}
listen(requestedPort);
