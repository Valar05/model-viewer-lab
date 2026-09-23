# Hard Surface Factory — state.md

Designation: HSF-BLENDER-PROMPT-CLI
Status: ACTIVE CANDIDATE
Authority: Drew Clarke
State Owner: Adam
Authoritative Home: `Valar05/model-viewer-lab/labs/hard-surface-factory/state.md`
Updated: 2026-08-11 America/Chicago

## Commission

Build a Blender CLI layer that farms Sherman Labs, factories, Tanks for the Memories, and Pose Lab into a deterministic promptable modeling playbook with no AI/model in the execution backend. Consume RetopoFlow and other useful zero-license-fee Blender extensions without pretending interactive tools are headless capabilities.

## Locked boundaries

- Consolidate existing 3D tooling under Hard Surface Factory; do not replace it with a disconnected repository.
- Home Center Blender Workspace is the persistent execution and immutable-revision lane.
- Foundry is retired; its ledger and history remain evidence, not active runtime authority.
- Source meshes are preserved as evidence/scaffolds unless a commission explicitly authorizes reuse.
- Machine validity, Blender artifact evidence, delivery runtime, and Drew's acceptance remain separate.
- No paid add-on is required.

## Capability state

- Requested: broad deterministic prompt-to-Blender product and free extension consumption.
- Implemented candidate: prompt compiler, typed recipe output, strict lossless gate, plugin capability ledger, test, and playbook.
- Tested: `Model Viewer Lab CI` run `31517072030` passed at head `1b81cc3925ec5a3f8a06caa9728809952b8f72d3`; deterministic canary recipe hash `505cd77677649525182d411929a4b67f5d2052d3816db196fc96723e842324b0`.
- Deployed/callable/delivered/accepted: not yet claimed.

## Working set

- `cli/compiler.mjs`
- `cli/blender-prompt.mjs`
- `cli/test-compiler.mjs`
- `cli/free-stack.json`
- `cli/PLAYBOOK.md`
- Home Center recipe contract `home-center.blender-workspace-recipe.v1`

## Active gate

Home Center advertises `blender.workspace.create`, but the deployed call rejected the exact canary before dispatch with `Blender workspace task target is not configured.` No workspace or Blender artifact was created. Runtime configuration, execution, inspect, and export remain blocked.

## Next authorized action

Expand the verb registry from recovered exporter and Pose Lab operations, add plugin background-mode probes, then compile ledger rows into recipe fragments without letting machine inference overwrite human decisions.

## Recent delta

- Draft PR: `https://github.com/Valar05/model-viewer-lab/pull/6`.
- Candidate head: `1b81cc3925ec5a3f8a06caa9728809952b8f72d3`.
- Repository CI: green.
- Browser acceptance workflow: running at last readback; it is not Blender execution evidence.
- Home Center Blender Workspace: advertised but currently unconfigured; rejection occurred before dispatch.
