#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {compilePrompt} from './compiler.mjs';

const args = process.argv.slice(2);
const option = (name) => { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : undefined; };
const promptFile = option('--prompt-file');
const prompt = option('--prompt') || (promptFile ? fs.readFileSync(promptFile, 'utf8') : '');
const out = option('--out');

try {
  const compilation = compilePrompt(prompt, {strict: !args.includes('--allow-partial'), id: option('--id')});
  const payload = JSON.stringify(compilation, null, 2) + '\n';
  if (out) { fs.mkdirSync(path.dirname(path.resolve(out)), {recursive: true}); fs.writeFileSync(out, payload); }
  else process.stdout.write(payload);
} catch (error) {
  process.stderr.write(JSON.stringify({ok: false, code: error.code || 'COMPILE_FAILED', message: error.message, details: error.details || null}, null, 2) + '\n');
  process.exit(2);
}

