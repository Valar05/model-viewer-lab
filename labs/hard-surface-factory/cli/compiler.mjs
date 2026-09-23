import crypto from 'node:crypto';

export const RECIPE_VERSION = 'home-center.blender-workspace-recipe.v1';
export const COMPILER_VERSION = 'hard-surface-prompt-compiler.v1';

const number = String.raw`(-?\d+(?:\.\d+)?)`;
const ident = String.raw`([A-Za-z][A-Za-z0-9_.:-]*)`;

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 64) || 'recipe';
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  return value;
}

function digest(value) {
  return crypto.createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');
}

function sentences(prompt) {
  return prompt.replace(/\s+/g, ' ').split(/(?:\.(?=\s+[A-Z]|$)|;|\n|\bthen\b)/).map((part) => part.trim()).filter(Boolean);
}

function vec(match, start = 1) {
  return [Number(match[start]), Number(match[start + 1]), Number(match[start + 2])];
}

function parseSentence(text, context) {
  let match;
  const lower = text.toLowerCase();

  if (/^(preserve|protect|lock)\s+source\b/i.test(text) || /^(never|do not|don't)\s+(modify|mutate|overwrite|delete)\s+(the\s+)?source\b/i.test(text)) {
    context.locks.push({kind: 'preserve-source', text}); return;
  }
  if ((match = text.match(new RegExp(`^create\\s+(cube|cylinder|empty|camera|light)\\s+(?:named\\s+)?${ident}`, 'i')))) {
    context.operations.push({op: 'object.create', type: match[1].toLowerCase(), name: match[2], objectId: match[2]}); context.current = match[2]; return;
  }
  if ((match = text.match(new RegExp(`^set\\s+${ident}\\s+dimensions\\s+${number}\\s*(?:x|,|by)\\s*${number}\\s*(?:x|,|by)\\s*${number}`, 'i')))) {
    context.operations.push({op: 'object.transform', objectId: match[1], dimensions: vec(match, 2), apply: true, applyScale: true}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^(?:move|translate)\\s+${ident}\\s+(?:to\\s+)?${number}\\s*[, ]\\s*${number}\\s*[, ]\\s*${number}`, 'i')))) {
    context.operations.push({op: 'object.transform', objectId: match[1], location: vec(match, 2)}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^rotate\\s+${ident}\\s+${number}\\s*[, ]\\s*${number}\\s*[, ]\\s*${number}`, 'i')))) {
    context.operations.push({op: 'object.transform', objectId: match[1], rotation: vec(match, 2).map((degrees) => degrees * Math.PI / 180)}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^(?:duplicate|copy)\\s+${ident}\\s+as\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'object.duplicate', sourceObjectId: match[1], name: match[2], objectId: match[2]}); context.current = match[2]; return;
  }
  if ((match = text.match(new RegExp(`^(?:instance|linked duplicate)\\s+${ident}\\s+as\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'object.linked_duplicate', sourceObjectId: match[1], name: match[2], objectId: match[2]}); context.current = match[2]; return;
  }
  if ((match = text.match(new RegExp(`^bevel\\s+${ident}\\s+(?:width\\s+)?${number}(?:\\s+(?:with\\s+)?${number}\\s+segments?)?`, 'i')))) {
    context.operations.push({op: 'mesh.bevel', objectId: match[1], width: Number(match[2]), segments: Number(match[3] || 2)}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^(?:add\\s+)?(mirror|solidify|shrinkwrap|decimate|weighted normal|subdivision)\\s+(?:modifier\\s+)?(?:to\\s+)?${ident}`, 'i')))) {
    const types = {'weighted normal': 'WEIGHTED_NORMAL', subdivision: 'SUBSURF'};
    context.operations.push({op: 'modifier.add', objectId: match[2], type: types[match[1].toLowerCase()] || match[1].toUpperCase()}); context.current = match[2]; return;
  }
  if ((match = text.match(new RegExp(`^assign\\s+material\\s+${ident}\\s+to\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'material.assign', name: match[1], objectId: match[2]}); context.current = match[2]; return;
  }
  if ((match = text.match(new RegExp(`^make\\s+material\\s+${ident}(?:\\s+roughness\\s+${number})?(?:\\s+metallic\\s+${number})?`, 'i')))) {
    context.operations.push({op: 'material.create', name: match[1], roughness: Number(match[2] || 0.5), metallic: Number(match[3] || 0)}); return;
  }
  if ((match = text.match(new RegExp(`^(?:parent|attach)\\s+${ident}\\s+to\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'object.parent', objectId: match[1], parentObjectId: match[2], keepWorld: true}); return;
  }
  if ((match = text.match(new RegExp(`^smart uv\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'uv.smart_project', objectId: match[1]}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^(?:shade smooth|smooth)\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'mesh.smooth', objectId: match[1], smooth: true}); context.current = match[1]; return;
  }
  if ((match = text.match(new RegExp(`^delete\\s+${ident}`, 'i')))) {
    context.operations.push({op: 'object.delete', objectId: match[1]}); return;
  }
  if (/\b(retopoflow|polyquilt|bsurfaces|f2|looptools)\b/i.test(text)) {
    const plugin = lower.match(/retopoflow|polyquilt|bsurfaces|f2|looptools/)[0];
    context.manual.push({kind: 'interactive-plugin', plugin, text, reason: `${plugin} is not represented as a headless Home Center recipe operation`}); return;
  }
  if (/\b(quadriflow|voxel remesh|retopolog(?:y|ize)|unwrap|rig|pose|render|export)\b/i.test(text)) {
    context.unsupported.push({text, reason: 'recognized modeling intent has no lossless recipe-v1 lowering'}); return;
  }
  context.unknown.push(text);
}

export function compilePrompt(prompt, options = {}) {
  if (typeof prompt !== 'string' || !prompt.trim()) throw new Error('prompt is required');
  const context = {operations: [], locks: [], manual: [], unsupported: [], unknown: [], current: null};
  for (const sentence of sentences(prompt)) parseSentence(sentence, context);
  const strict = options.strict !== false;
  const blockers = [...context.unsupported, ...context.unknown];
  if (strict && (blockers.length || context.manual.length)) {
    const items = [...blockers, ...context.manual];
    const error = new Error(`prompt did not compile losslessly: ${items.map((item) => item.text || item).join(' | ')}`);
    error.code = 'PROMPT_NOT_LOSSLESS'; error.details = {blockers, manual: context.manual}; throw error;
  }
  if (!context.operations.length) throw new Error('prompt produced no executable operations');
  const recipe = {contractVersion: RECIPE_VERSION, operations: context.operations};
  const compilation = {contractVersion: COMPILER_VERSION, id: options.id || slug(prompt), prompt, recipe, locks: context.locks, manual: context.manual, unsupported: context.unsupported, unknown: context.unknown, execution: context.manual.length ? 'hybrid' : 'headless'};
  compilation.recipeSha256 = digest(recipe);
  compilation.compilationSha256 = digest(compilation);
  return compilation;
}
