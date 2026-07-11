# Hard Surface Factory Tools

## Exporters

`tools/exporters/legacy-tank-investigation/` contains Blender Python exporters from the tank upper-hull investigation. They are archived as reusable implementation examples for:

- scene setup
- mesh extraction
- face adjacency
- clustering
- plane fitting
- authored solid construction
- topology checks
- diagnostic rendering
- report writing

They are not expected to run unchanged in a new project because many retain original tank-project paths.

## Diagnostics

`tools/diagnostics/` contains focused diagnostic scripts that can be copied into a new experiment when the input/output paths are updated.
