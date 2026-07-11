# Blender Exporter Workflow

The archived exporters are executable references, not a single blessed pipeline.

## Local Blender

Run an exporter with Blender in background mode:

```sh
blender --background --python labs/hard-surface-factory/tools/exporters/legacy-tank-investigation/export_upper_glacis_silhouette_edges_v07.py
```

Each exporter may contain source and output paths from the originating tank repository. Update paths before using the script in a new project.

## Android / Termux Pattern

When host Blender is unavailable, use the existing proot Debian Blender path if installed:

```sh
proot-distro login debian -- blender --background --python /absolute/path/to/exporter.py
```

## Review Pattern

1. Export GLB and reports into an experiment-specific output directory.
2. Add or update a review-state JSON file that points at a browser-readable GLB URL.
3. Validate the review state with `node tools/validate_review_state.mjs <state.json>`.
4. Open the state in the GitHub Pages viewer.

## Required Reports For New Experiments

New experiments should write at minimum:

- model manifest
- measurement report
- authored solids report
- topology report or topology fields in authored solids
- depth/silhouette comparison report when a source scaffold exists
- provenance note for any copied asset
