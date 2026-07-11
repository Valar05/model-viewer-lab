# Hard Surface Factory

Hard Surface Factory is a lab inside Model Viewer Lab. It stores reusable hard-surface reconstruction research, Blender exporter experiments, source mesh scaffolds, and objective run history for future authored-geometry work.

This lab is not a finished-asset library. It does not promote any tank output as production geometry. The committed mesh assets here are source/reference scaffolds only.

## What Belongs Here

- Measurement and reconstruction research that can apply to hard-surface vehicle parts.
- Blender/Python tooling used to inspect, segment, measure, author, render, or validate hard-surface meshes.
- Source or reference meshes used as measurement scaffolds.
- Objective machine reports from prior experiments.
- Model Viewer review-state files for cloud-readable inspection.

## What Does Not Belong Here

- Completed runtime tank models.
- Promoted production GLBs or texture plates.
- Raw conversation transcripts.
- Raw scratch notes that encode subjective judgments.
- Build outputs, pycache, backup Blend files, or local-only browser captures.

## Layout

- `source-assets/`: source/reference GLBs, source images, and manifests.
- `tools/exporters/legacy-tank-investigation/`: archived Blender exporter scripts from the tank investigation.
- `tools/diagnostics/`: focused diagnostic scripts that can be reused.
- `history/raw-reports/`: JSON reports copied from attempts, without GLB/Blend candidate outputs.
- `docs/research/`: neutral reusable reconstruction notes.
- `docs/history/`: condensed factual history of approach families.
- `review-states/`: viewer states for browser-readable source asset review.

## Validation

Run from the repository root:

```sh
npm run validate:hard-surface-factory
npm run ci
```
