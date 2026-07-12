#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const outRel = 'labs/hard-surface-factory/generated/upper-glacis-manufactured-v1';
const outDir = path.join(root, outRel);
const required = [
  'real_sherman_upper_glacis_manufactured_v1.glb',
  'model_manifest.json',
  'measurement_report.json',
  'authored_solids_report.json',
  'topology_report.json',
  'silhouette_depth_report.json',
  'provenance_note.md',
  'review-state.json',
  'render-front.svg',
  'render-left_front_oblique.svg',
  'render-right_front_oblique.svg',
  'render-top.svg'
];

function fail(message) {
  console.error('[upper-glacis] ' + message);
  process.exitCode = 1;
}
for (const file of required) {
  if (!fs.existsSync(path.join(outDir, file))) fail('missing generated artifact: ' + file);
}
if (process.exitCode) process.exit();

const topology = JSON.parse(fs.readFileSync(path.join(outDir, 'topology_report.json'), 'utf8'));
if (topology.boundaryEdgeCount !== 0) fail('boundary edges must be zero');
if (topology.nonmanifoldEdgeCount !== 0) fail('nonmanifold edges must be zero');
if (topology.gate !== 'pass') fail('topology gate must pass');

const authored = JSON.parse(fs.readFileSync(path.join(outDir, 'authored_solids_report.json'), 'utf8'));
const primary = authored.solids?.find((solid) => solid.name === 'primary_armor_mass');
if (!primary) fail('primary_armor_mass solid is required');
for (const name of ['frontLowerBoundary', 'leftShoulderReturn', 'rightShoulderReturn', 'deckTransition', 'turretRingSocketBoundary']) {
  if (!primary.namedInterfaces?.[name]) fail('missing named interface: ' + name);
}
if (authored.sourceTrianglesUsedAsFinalAuthoredTopology !== false) fail('source triangle policy must be false');
if (authored.secondaryDetails?.status !== 'not_started') fail('secondary details must not proceed in primary-gate run');

const silhouette = JSON.parse(fs.readFileSync(path.join(outDir, 'silhouette_depth_report.json'), 'utf8'));
if (silhouette.gate !== 'pass') fail('silhouette/depth gate must pass');
if (!Array.isArray(silhouette.fixedAngles) || silhouette.fixedAngles.length < 4) fail('expected at least four fixed-angle renders');
for (const angle of silhouette.fixedAngles || []) {
  if (!angle.render || !fs.existsSync(path.join(root, angle.render))) fail('missing fixed-angle render for ' + angle.id);
  if (!(angle.silhouetteWidth > 0) || !(angle.depthSpan >= 0)) fail('invalid visual metrics for ' + angle.id);
}

const glb = fs.readFileSync(path.join(outDir, 'real_sherman_upper_glacis_manufactured_v1.glb'));
if (glb.readUInt32LE(0) !== 0x46546c67) fail('GLB magic is invalid');
if (glb.readUInt32LE(4) !== 2) fail('GLB version must be 2');

if (!process.exitCode) console.log('[upper-glacis] generated manufactured primary armor mass ok');
