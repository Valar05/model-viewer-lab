# Foundry Ledger Workflow

The Foundry Ledger converts generated-mesh archaeology into durable, executable decisions.

## 1. Analyze

Run geometry tooling against an untouched source specimen. Produce stable component identifiers and objective measurements such as connected-island membership, bounds, triangle count, volume/area estimates, spatial clustering, symmetry candidates, repetition candidates, material membership, UV/normals state, and topology diagnostics.

Do not rename or mutate source geometry merely to make the report prettier.

## 2. Populate `parts.csv`

Machine tooling may populate:

- `part_id`
- `specimen_id`
- `source_ref`
- `source_component_ids`
- `geometry_family`
- `repeat_count`
- `symmetry`
- `confidence`

Human review owns or confirms:

- `parent_assembly`
- `semantic_role`
- `keep_decision`
- `canonical_part_id`
- `treatment`
- `variant_axes`
- `notes`

A tool must not silently change a prior human decision when re-running analysis. New machine evidence should be emitted separately and reconciled explicitly.

## 3. Define phenotype genes

Use `genes.csv` for parameters that should survive beyond a single specimen. Examples include hull length, armor growth, flesh exposure, locomotion pitch, turret mass, asymmetry, damage state, or biological/mechanical ratio.

A gene is not merely a prompt phrase. Its `implementation_lane` states where the variation is actually produced: Blender, Meshy, texturing, viewer-only presentation, manual authoring, or a hybrid.

## 4. Record experiments

Every meaningful generation/reconstruction attempt receives an `experiment_id` in `experiments.csv` before promotion. Record parent lineage, changed genes, exact generation lane, prompt/recipe, source/result references, objective metrics, visual judgment, outcome, and failure reason.

Rejected experiments remain valuable evidence and should stay in the ledger unless they contain secrets or invalid provenance.

## 5. Compile decisions

Future compiler tooling should treat ledger rows as declarative instructions:

- `keep + preserve` — isolate without redesign.
- `keep + retopo` — rebuild topology while preserving measured form.
- `keep + instance` — choose/promote `canonical_part_id` and reproduce placement.
- `keep + generate` — issue a bounded generation task with the source family and genes.
- `reject + discard` — exclude from promoted assemblies while retaining source evidence.
- `reference` — preserve for measurement or visual comparison, not final assembly.

Compiler output belongs outside the ledger. The ledger says what should happen; executable tooling performs it.

## 6. Review and measure again

Generated outputs return through Model Viewer review states and geometry diagnostics. Objective findings can create new evidence; subjective judgments are recorded as explicit ledger edits. Promotion requires both.

## Stable IDs and list fields

IDs must remain stable across reorderings and spreadsheet round trips. Use letters, numbers, `.`, `_`, `:`, or `-`.

Columns containing multiple IDs use semicolon-separated values, e.g. `armor_growth;flesh_exposure`.

## Spreadsheet projection

For mobile work, import each CSV as a separate tab named `parts`, `genes`, and `experiments`. Export back to CSV without renaming columns. The Git repository copy remains canonical so changes are diffable and can participate in CI.
