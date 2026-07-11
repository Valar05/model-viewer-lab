# Review State Schema

Model Viewer Lab review state lets multiple agents share the same camera, display, selected object, visibility, and tweak context without sharing a browser session. It is not live collaborative editing; it is a durable handoff packet.

## URL Parameters

- `src`: GLB/GLTF URL.
- `manifest`: optional model manifest URL.
- `title`: readable review title.
- `state`: URL to a browser-readable review-state JSON document.
- `state64`: base64url-encoded review-state JSON for compact inline sharing.

When `state` or `state64` is present, that state provides defaults. Explicit `src`, `manifest`, or `title` query parameters override the state fields.

## Version 2 Shape

```json
{
  "version": 2,
  "src": "https://example.com/model.glb",
  "manifest": "https://example.com/model_manifest.json",
  "title": "model id",
  "camera": { "position": [0, 1.4, 5], "target": [0, 0.8, 0], "fov": 38 },
  "display": { "clay": false, "wire": false, "grid": true, "boxes": false },
  "selectedPartId": "hull",
  "parts": [
    { "id": "hull", "label": "hull", "visible": true, "position": [0,0,0], "rotationDeg": [0,0,0], "scale": [1,1,1] }
  ]
}
```

Validate committed state files with:

```sh
npm run validate:review-state
node tools/validate_review_state.mjs path/to/state.json
```
