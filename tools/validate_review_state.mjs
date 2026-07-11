#!/usr/bin/env node
import fs from 'node:fs';

const files = process.argv.slice(2);
if (!files.length) {
  console.error('Usage: node tools/validate_review_state.mjs STATE.json [...]');
  process.exit(1);
}
function fail(file, message) {
  console.error(file + ': ' + message);
  process.exitCode = 1;
}
function isVec3(value) {
  return Array.isArray(value) && value.length === 3 && value.every((item) => Number.isFinite(item));
}
for (const file of files) {
  let state;
  try { state = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (error) { fail(file, 'cannot parse JSON: ' + error.message); continue; }
  if (state.version !== 2) fail(file, 'version must be 2');
  if (!state.src || typeof state.src !== 'string') fail(file, 'src is required');
  if (state.manifest !== undefined && typeof state.manifest !== 'string') fail(file, 'manifest must be a string when present');
  if (!state.title || typeof state.title !== 'string') fail(file, 'title is required');
  if (!state.camera || !isVec3(state.camera.position) || !isVec3(state.camera.target) || !Number.isFinite(state.camera.fov)) fail(file, 'camera.position, camera.target, and camera.fov are required');
  if (!state.display || typeof state.display !== 'object') fail(file, 'display object is required');
  for (const key of ['clay', 'wire', 'grid', 'boxes']) if (typeof state.display[key] !== 'boolean') fail(file, 'display.' + key + ' must be boolean');
  if (!Array.isArray(state.parts)) fail(file, 'parts array is required');
  for (const [index, part] of (state.parts || []).entries()) {
    if (!part.id || typeof part.id !== 'string') fail(file, 'parts[' + index + '].id is required');
    if (!part.label || typeof part.label !== 'string') fail(file, 'parts[' + index + '].label is required');
    if (typeof part.visible !== 'boolean') fail(file, 'parts[' + index + '].visible must be boolean');
    if (!isVec3(part.position)) fail(file, 'parts[' + index + '].position must be vec3');
    if (!isVec3(part.rotationDeg)) fail(file, 'parts[' + index + '].rotationDeg must be vec3');
    if (!isVec3(part.scale)) fail(file, 'parts[' + index + '].scale must be vec3');
  }
  if (!process.exitCode) console.log(file + ': review state ok');
}
