# Hard Surface Factory Orientation

Start here before changing this lab.

## Role

This lab is a subproject of Model Viewer Lab. It owns hard-surface reconstruction tooling, source/reference assets, and the Foundry Ledger that turns geometry analysis into durable human-reviewed build decisions. Model Viewer Lab owns cloud review and durable viewing links.

## Current Scope

The committed assets are source scaffolds and measurement references. They are not final tank assets. Completed authored tank models remain outside this lab.

The Foundry Ledger is allowed to contain structured subjective judgment when it is attached to stable identifiers and explicit evidence. Raw conversational or opinion-heavy scratch notes remain outside the lab.

## Working Rules

1. Treat noisy generated meshes as measurement inputs, not final topology.
2. Author final geometry from explicit manufactured parts, shared interfaces, and closed solids.
3. Preserve silhouette and manifold topology as separate acceptance gates.
4. Keep visual review anchored in Model Viewer review states.
5. Record provenance for every copied source mesh or generated reference image.
6. Record durable human/agent judgments in the Foundry Ledger rather than loose scratch notes.
7. Never silently overwrite a prior ledger decision with a new machine inference; reconcile changes explicitly.
8. Preserve source specimens untouched and generate derived/promoted artifacts separately.

## Dependencies

- Node.js for validation and review-state tooling.
- npm dependencies from the Model Viewer Lab root.
- Git LFS for committed GLB/PNG source scaffolds.
- Blender 4.x for exporter execution.
- Optional Termux/proot Debian Blender path for Android workers that cannot run host Blender directly.
- Any spreadsheet editor for mobile ledger work; committed CSV remains canonical.

## Entry Points

- `README.md`: lab inventory and boundaries.
- `ledger/README.md`: Foundry Ledger contract and table meanings.
- `docs/workflows/foundry-ledger-workflow.md`: analyze/decide/compile workflow.
- `docs/research/measurement-driven-reconstruction.md`: reusable reconstruction model.
- `docs/history/tank-upper-hull-investigation.md`: factual approach history.
- `docs/provenance/source-assets.md`: source asset inventory.
- `tools/exporters/legacy-tank-investigation/`: archived executable exporter code.
- `scripts/validate_factory_inventory.mjs`: repository guard for this lab.
- `scripts/validate_foundry_ledger.mjs`: ledger schema and referential-integrity guard.

## Cloud Review

Use the parent viewer with review-state JSON:

`https://valar05.github.io/model-viewer-lab/model-viewer.html?state=<raw-review-state-url>`

Review states in this lab point at raw GitHub URLs for the committed source/reference GLBs.
