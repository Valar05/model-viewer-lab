import assert from 'node:assert/strict';
import {compilePrompt, RECIPE_VERSION} from './compiler.mjs';

const prompt = ['Create cube named carrier_hull.', 'Set carrier_hull dimensions 6 x 3.2 x 1.8.', 'Bevel carrier_hull width 0.16 with 3 segments.', 'Make material canary_clay roughness 0.52 metallic 0.1.', 'Assign material canary_clay to carrier_hull.', 'Preserve source.'].join(' ');
const first = compilePrompt(prompt); const second = compilePrompt(prompt);
assert.equal(first.recipe.contractVersion, RECIPE_VERSION);
assert.equal(first.recipe.operations.length, 5);
assert.deepEqual(first.recipe, second.recipe);
assert.equal(first.recipeSha256, second.recipeSha256);
assert.equal(first.execution, 'headless');
assert.equal(first.locks[0].kind, 'preserve-source');
assert.throws(() => compilePrompt('RetopoFlow the hull. Export it.'), (error) => error.code === 'PROMPT_NOT_LOSSLESS' && error.details.manual[0].plugin === 'retopoflow');
const hybrid = compilePrompt('Create cube named cage. RetopoFlow the cage.', {strict: false});
assert.equal(hybrid.execution, 'hybrid');
console.log(JSON.stringify({ok: true, compiler: first.contractVersion, recipeSha256: first.recipeSha256, operations: first.recipe.operations.length}));

