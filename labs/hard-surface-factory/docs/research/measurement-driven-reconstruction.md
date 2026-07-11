# Measurement-Driven Hard-Surface Reconstruction

The reusable finding from the tank investigation is a separation of responsibilities.

## Source Mesh Role

A generated or scanned source mesh should answer measurement questions:

- dominant planes
- silhouette extents
- curve centers and radii
- seam locations
- symmetry axis
- depth ranges
- feature ownership

The source mesh should not provide final triangles, final topology, or arbitrary vertex locations for the authored output.

## Authored Geometry Role

The generated output should own its topology. Vertices exist because a manufactured part requires them. Regions should be explicit closed solids such as plates, returns, cheek pieces, sockets, rings, housings, and caps.

## Core Pipeline

1. Import source/reference meshes.
2. Extract world-space vertices, faces, normals, and edge adjacency.
3. Segment evidence only enough to measure named features.
4. Fit stable planes, lines, radii, and stations.
5. Regularize measurements into a small manufactured template.
6. Author closed solids from template parameters.
7. Validate topology per object and globally.
8. Render shaded, depth, silhouette, and interface diagnostics.
9. Publish a Model Viewer state for review.

## Acceptance Gates

Topology and visual shape are independent gates:

- zero boundary edges for authored solids
- zero nonmanifold edges for authored solids
- no loose debris
- no duplicate coincident faces in final authored regions
- preserved exterior silhouette at the intended review angle
- major planes and interfaces remain readable after texture and material removal
- source comparison uses depth and silhouette evidence, not only aggregate metrics

## Useful Diagnostic Reports

The prior tools produced these machine-readable reports:

- `measurement_report.json`: fitted planes, centers, radii, dimensions, thresholds.
- `feature_cluster_report.json`: face-cluster evidence before authoring.
- `authored_solids.json`: authored region topology and ownership.
- `silhouette_edge_report.json`: chain extraction and polygon simplification evidence.
- `shared_interface_report.json`: canonical boundary definitions consumed by multiple solids.
- `depth_error_report.json`: source/candidate depth comparison.
- `retopo_landmarks.json`: named measured landmarks.

## Transferable Constraint

When an experiment improves topology but loses silhouette, the next experiment should not keep tuning topology. When an experiment improves silhouette but loses manifold structure, the next experiment should not keep copying source topology. The durable target is authored manufactured parts that satisfy both gates.
