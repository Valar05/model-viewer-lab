# Final Report

Branch: agent/portable-ci-pages-upper-glacis

## Implementation

- Repaired default CI portability by making npm run smoke use committed review-state evidence instead of /storage/emulated/0 artifacts.
- Preserved phone-local artifact validation as npm run smoke:local-artifacts.
- Added package-lock.json and moved Actions workflows to npm ci.
- Hardened Pages workflow with npm run ci before upload and actions/configure-pages enablement: true.
- Added a measurement-driven upper-glacis manufactured-solid generator, parameter file, validator, generated GLB, manifest, reports, four fixed-angle renders, provenance note, and review state.

## Evidence

- PR CI uploads artifact `model-viewer-lab-pr-evidence` containing `dist/model-viewer.html`, `dist/mechanism-viewer.html`, built assets, mechanism fixture, generated upper-glacis evidence, and verification reports.
- npm ci && npm run ci: pass.
- npm run ci: pass.
- npm run smoke:local-artifacts: pass on this worker.
- Topology: 0 boundary edges, 0 nonmanifold edges.
- Model Viewer review URL: https://valar05.github.io/model-viewer-lab/model-viewer.html?state=https%3A%2F%2Fraw.githubusercontent.com%2FValar05%2Fmodel-viewer-lab%2Fagent%2Fportable-ci-pages-upper-glacis%2Flabs%2Fhard-surface-factory%2Fgenerated%2Fupper-glacis-manufactured-v1%2Freview-state.json&title=real_sherman_upper_glacis_manufactured_v1
- Mechanism Viewer review URL: https://valar05.github.io/model-viewer-lab/mechanism-viewer.html?mechanism=https%3A%2F%2Fraw.githubusercontent.com%2FValar05%2Fmodel-viewer-lab%2Fmain%2Flabs%2Fhard-surface-factory%2Fmechanisms%2Ftread-system-v1%2Fmechanism.json&title=tread-system-v1

## Pages Status

The repository Pages API returned HTTP 404 before this branch, matching the previous configure-pages failure. Code-side workflow configuration is repaired. If workflow enablement is blocked by repository policy, enable GitHub Pages for Valar05/model-viewer-lab with GitHub Actions as the source.

## Failed Experiments Preserved

- Initial normal clone failed on an existing Git LFS 404 for labs/hard-surface-factory/source-assets/meshy-envelope-assembly-v1/meshy_hull_envelope.glb. This is recorded in provenance and command-log, and no source triangles were promoted.
- Existing historical failed upper-glacis reports remain under labs/hard-surface-factory/history/raw-reports/.

## PR

Draft PR: https://github.com/Valar05/model-viewer-lab/pull/1
