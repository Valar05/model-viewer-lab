# Model Viewer Lab

Official workspace model review platform for generated GLB/GLTF mesh artifacts.

The viewer is portrait-first, full-screen, and intended for handoff links. It does not replace project-specific visual acceptance lanes; it makes every mesh artifact inspectable with full camera controls and hideable/tweakable object UI.

## Build

```sh
npm run build
```

The build script can reuse dependencies from `../tanks-for-the-memories/node_modules` if this repo has not installed its own dependencies.

## Serve

```sh
npm run serve
```

The server hosts `/storage/emulated/0/Documents/GodotProjects` as the web root so review URLs can point to ignored scratch archives or sibling project assets without copying GLBs.

## Link A Model

```sh
node tools/make_model_viewer_link.mjs --src /storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories/archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_chassis_kit_scratch_v1/real_sherman_chassis_kit_scratch_v1.glb --manifest /storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories/archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_chassis_kit_scratch_v1/model_manifest.json --title real_sherman_chassis_kit_scratch_v1
```


## Cloud Pages Links

For cloud-readable review, publish this repo with GitHub Pages. The included workflow builds `dist/` and deploys the viewer at:

`https://valar05.github.io/model-viewer-lab/model-viewer.html`

Generate a durable review URL for a GLB committed in another public GitHub repo:

```sh
npm run pages-link -- --asset-repo Valar05/tanks-for-the-memories --branch codex/upper-glacis-recovery-tools --src archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_upper_glacis_silhouette_edges_scratch_v07/real_sherman_upper_glacis_silhouette_edges_scratch_v07.glb --manifest archive/scratch/20260708-real-sherman-chassis-scratch/models/real_sherman_upper_glacis_silhouette_edges_scratch_v07/model_manifest.json --title real_sherman_upper_glacis_silhouette_edges_scratch_v07
```

The generated URL uses `raw.githubusercontent.com` for model assets, so the source repo/artifacts must be readable to the browser. Private asset repos need an authenticated hosting lane instead of this public Pages helper.
