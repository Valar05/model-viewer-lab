#!/usr/bin/env node
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

const args = process.argv.slice(2);
const script = args.shift();
if (!script) {
  process.stderr.write('usage: run-blender-tool.mjs <script.py> [-- <script args>]\n');
  process.exit(2);
}

const scriptPath = path.resolve(script);
const blenderArgs = ['--background', '--python-exit-code', '1', '--python', scriptPath];
if (args.length) blenderArgs.push('--', ...args.filter((arg) => arg !== '--'));

const attempts = process.env.BLENDER_BIN
  ? [{command: process.env.BLENDER_BIN, args: blenderArgs, label: 'BLENDER_BIN'}]
  : [
      {command: 'blender', args: blenderArgs, label: 'PATH'},
      {command: 'proot-distro', args: ['login', 'debian', '--', 'blender', ...blenderArgs], label: 'proot Debian'},
    ];

for (const attempt of attempts) {
  const result = spawnSync(attempt.command, attempt.args, {stdio: 'inherit'});
  if (!result.error) process.exit(result.status ?? 1);
  if (result.error.code !== 'ENOENT') {
    process.stderr.write(`Blender launch failed via ${attempt.label}: ${result.error.message}\n`);
    process.exit(1);
  }
}

process.stderr.write('Blender was not found. Set BLENDER_BIN, add blender to PATH, or install it in proot Debian.\n');
process.exit(127);
