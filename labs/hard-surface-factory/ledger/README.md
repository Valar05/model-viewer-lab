# Foundry Ledger

The Foundry Ledger is the human-editable judgment and experiment control plane for Hard Surface Factory.

The repository remains authoritative for executable tooling, schemas, source/reference assets, review states, and reproducible build inputs. The ledger records structured decisions that machines cannot safely infer from geometry alone.

The ledger is deliberately spreadsheet-shaped. Each CSV can be opened directly in Google Sheets, LibreOffice, Excel, or any text editor without changing the repository format.

## Tables

- `parts.csv` — one row per discovered or promoted geometric part/family. Stores machine observations plus human decisions such as semantic role, keep/reject, canonical representative, symmetry, treatment, and variant axes.
- `genes.csv` — phenotype parameters that can vary across related assets. Stores defaults, bounds/options, affected assemblies, and implementation lane.
- `experiments.csv` — append-only experiment history linking specimen, parent, parameter changes, generation inputs, geometry metrics, visual judgment, and promotion/rejection outcome.

## Ownership boundary

Machine analysis may populate observation columns. Humans or explicitly authorized agents own judgment columns. Build tools consume only explicit decisions; they do not silently rewrite them.

Recommended flow:

`analyze -> ledger -> decide -> compile -> build -> measure -> ledger`

A generated GLB is never mutated in place. Preserve the source specimen, derive connected-component or semantic inventories from it, record judgments in the ledger, and generate promoted artifacts separately.

## Synchronization

The canonical durable representation is the CSV committed here. A Google Sheet may be used as a mobile editing surface, but it is a projection of these tables rather than a second source of truth. Any sync tool must round-trip exact column names and preserve stable IDs.

## Validation

From the repository root:

```sh
npm run validate:foundry-ledger
```

The validator checks required tables, exact required columns, stable IDs, enum values, duplicate IDs, and referential integrity between parts, genes, and experiments.
