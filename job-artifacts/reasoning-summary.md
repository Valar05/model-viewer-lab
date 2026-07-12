# Reasoning Summary

Portable CI failed historically because the default model viewer smoke required a phone-local /storage/emulated/0 tank artifact. The repair makes default smoke portable through committed review-state fixtures and keeps the phone-local smoke as npm run smoke:local-artifacts.

The Pages workflow failed because configure-pages could not find an enabled Pages site. The workflow now runs npm ci, gates on npm run ci, and passes enablement: true to actions/configure-pages so the main-branch deployment path can create/use GitHub Actions Pages configuration. If repository policy blocks that, the required setting is: enable GitHub Pages for Valar05/model-viewer-lab with GitHub Actions as the source.

The upper-glacis generator authors a fresh closed trapezoid-prism primary armor mass from committed parameters and measured reference features. It writes GLB, manifest, measurement report, authored-solids report, topology report, silhouette/depth report, four fixed-angle SVG renders, provenance, and Model Viewer review state. Secondary details remain not_started until the bare primary mass passes topology and visual gates.
