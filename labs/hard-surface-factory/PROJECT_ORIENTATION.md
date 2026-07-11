# Hard Surface Factory Orientation

Start here before changing this lab.

## Role

This lab is a subproject of Model Viewer Lab. It owns hard-surface reconstruction tooling and source/reference assets. Model Viewer Lab owns cloud review and durable viewing links.

## Current Scope

The committed assets are source scaffolds and measurement references. They are not final tank assets. Completed authored tank models remain outside this lab.

## Working Rules

1. Treat noisy generated meshes as measurement inputs, not final topology.
2. Author final geometry from explicit manufactured parts, shared interfaces, and closed solids.
3. Preserve silhouette and manifold topology as separate acceptance gates.
4. Keep visual review anchored in Model Viewer review states.
5. Record provenance for every copied source mesh or generated reference image.
6. Do not import opinion-heavy scratch notes; rewrite lessons as neutral constraints.

## Dependencies

- Node.js for validation and review-state tooling.
- npm dependencies from the Model Viewer Lab root.
- Git LFS for committed GLB/PNG source scaffolds.
- Blender 4.x for exporter execution.
- Optional Termux/proot Debian Blender path for Android workers that cannot run host Blender directly.

## Entry Points

- `README.md`: lab inventory and boundaries.
- `docs/research/measurement-driven-reconstruction.md`: reusable reconstruction model.
- `docs/history/tank-upper-hull-investigation.md`: factual approach history.
- `docs/provenance/source-assets.md`: source asset inventory.
- `tools/exporters/legacy-tank-investigation/`: archived executable exporter code.
- `scripts/validate_factory_inventory.mjs`: repository guard for this lab.

## Cloud Review

Use the parent viewer with review-state JSON:

`https://valar05.github.io/model-viewer-lab/model-viewer.html?state=<raw-review-state-url>`

Review states in this lab point at raw GitHub URLs for the committed source/reference GLBs.
