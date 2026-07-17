# Source Asset Provenance

## Source Classifications

- `source-assets/meshy-envelope-assembly-v1`: generated reference mesh envelopes and source images for hull, turret kit, and treads.
- `source-assets/meshy-lowpoly-envelope-v1`: generated lower-detail reference mesh envelopes and the same source-image set.
- `source-assets/meshy-component-kit-071716`: untracked root-level Meshy component GLBs ingested as quarantined reference scaffolds for hull, turret, barrel, secondary barrel, and a hatch-candidate lid.

These assets are committed as reference scaffolds for measurement and review. They are not production runtime assets and are not accepted final models.

## Original Repository Paths

- `tanks-for-the-memories/public/tftm/models/meshy_sherman_envelope_assembly_v1`
- `tanks-for-the-memories/public/tftm/models/meshy_sherman_lowpoly_envelope_v1`

## Included Files

- GLB reference meshes.
- Source images used by the reference mesh generation pass.
- Source manifests supplied by the originating repository.
- For `meshy-component-kit-071716`, a generated kit manifest and provenance note created at ingest because no Meshy task manifest accompanied the root-level GLBs.

## Excluded Files

- `assets/authored/*` from the tank project.
- Public completed tank GLBs.
- Texture plates for promoted assets.
- Scratch candidate Blend files.
- Backup `.blend1` files.
- Pycache and local generated build outputs.

## Intended Use

Use these assets as measurement scaffolds, viewer fixtures, and regression references. Do not promote them directly into a runtime game without a separate acceptance process. The `meshy-component-kit-071716` positioning study is a layout/reference artifact only; it is not visual acceptance, clean authored topology, or a production tank model.
