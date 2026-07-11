# Tank Upper-Hull Investigation History

This is a neutral map of approach families represented by the archived tools and reports. It is provided to help future agents avoid repeating implementation classes without inheriting project-specific judgments.

## Asset Intake

Source/reference meshes were generated as envelope assemblies and lower-detail envelope variants. These are stored under `source-assets/` and are the only committed mesh assets in this lab.

## Approach Families

### Chassis And Kit Exporters

Scripts named `export_real_sherman_chassis_*` created early whole-chassis and part-kit experiments. They are retained as examples of Blender scene creation, object organization, exporter wiring, and manifest generation.

### Reference Kit And Plate Kit Passes

Scripts with `reference_kit`, `platekit`, `castbudget`, and `handretopo` names explored how far large pieces, cast forms, and manually constrained regions could go. Their JSON manifests remain as factual history; their candidate mesh outputs are intentionally not copied here.

### Upper Glacis Retopo Passes

The `f01` through `f16` scripts explored landmarks, feature-oriented reconstruction, Quadriflow, island cleanup, primitive authoring, and hybrid repair. Their reports preserve depth and topology evidence where available.

### Measurement Solids And Cluster Passes

The `measurement_solids`, `measurement_features`, and `measurement_clusters` exporters introduced a stronger separation between source measurement and authored output. These scripts and reports are retained because they contain reusable face adjacency, clustering, plane fitting, measurement reporting, and topology checks.

### Silhouette Edge And Shared Interface Passes

The `silhouette_edges_v07` and `shared_interfaces_v08` exporters are retained for their edge-chain extraction, named interface, and report-generation patterns. The final geometry from those runs is not included as a reusable asset.

## Current Blank-Slate Position

Future work should begin from a fresh hard-surface generator that uses source meshes only to populate parameters. The lab provides source assets, prior algorithms, and reports. It does not provide an accepted finished hull.
