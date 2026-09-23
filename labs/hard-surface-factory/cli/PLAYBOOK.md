# Blender Prompt CLI Playbook

This layer turns bounded modeling language into deterministic Home Center Blender Workspace recipes. No model, network call, autonomous agent, or generated Python enters the execution path.

## Contract

`prompt -> normalized sentences -> typed verbs -> lossless lowering -> recipe hash -> dry run -> immutable Blender revision -> inspect -> export -> human review`

The compiler fails closed when it recognizes intent that recipe v1 cannot express. `--allow-partial` is planning mode only; it never launders an interactive RetopoFlow instruction into a headless success claim.

## First verbs

- `Create cube named carrier_hull.`
- `Set carrier_hull dimensions 6 x 3.2 x 1.8.`
- `Move carrier_hull to 0, 0, 1.`
- `Rotate carrier_hull 0, 0, 90.`
- `Duplicate carrier_hull as damaged_hull.`
- `Instance wheel as wheel_right.`
- `Bevel carrier_hull width 0.16 with 3 segments.`
- `Add mirror modifier to carrier_hull.`
- `Make material cast_steel roughness 0.62 metallic 0.15.`
- `Assign material cast_steel to carrier_hull.`
- `Parent barrel to mantlet.`
- `Smart UV carrier_hull.`
- `Shade smooth carrier_hull.`
- `Preserve source.`

## Use

```sh
npm run blender:prompt -- --prompt "Create cube named carrier_hull. Set carrier_hull dimensions 6 x 3.2 x 1.8. Bevel carrier_hull width 0.16 with 3 segments."
npm run blender:prompt:test
```

The emitted `recipe` is the exact payload for `blender.workspace.create` or `blender.workspace.mutate`. Mutation always names an explicit base revision. A stale base fails rather than overwriting newer work.

## Sherman / Factory doctrine

1. Intake preserves the source specimen and hashes.
2. Analyze writes objective component, bounds, topology, symmetry, repetition, and interface evidence.
3. The Foundry Ledger owns semantic role, keep/reject, treatment, variant genes, and experiment lineage.
4. Reconstruction follows manufacturing family: cast/forged sections, welded plates, stamped sheet paths, revolved machined profiles, canonical repeated units.
5. Every topology group receives a visible-purpose record and a budget ceiling.
6. Source scaffolds inform measurements; they are not silently promoted or reused when fresh reconstruction is locked.
7. Review the naked primary form before attachments, the unit before the assembly, and the assembly at delivery distance.
8. Machine validity, runtime delivery, and human visual acceptance remain separate.

## Pose Lab doctrine

Pose commands must choose direct final-rig authoring, explicit retargeting, or appearance transfer. The layer preserves final rig, clip, weapon composition, camera, keys, root policy, source hashes, and review authority. A correct Blender render does not prove the hosted Pose Lab route, and neither proves human acceptance.

## Free extension stack

`free-stack.json` is a capability ledger, not an install-everything bonfire. Each adapter records version, source, license, interactive/headless mode, verbs, and probe state. RetopoFlow, PolyQuilt, and F2 remain interactive until a real background-mode probe proves otherwise. Native deterministic equivalents are used only when they preserve the commissioned method; they are never silent substitutes.

```sh
npm run blender:plugins:test
npm run blender:plugins:probe > free-stack-probe.json
```

The read-only probe searches the active Blender profile for matching modules and named operators. It does not install, enable, disable, or call an extension. Presence does not prove background-context safety: promotion to `headless: true` requires a pinned fixture, before/after mesh assertions, a clean `--background --python-exit-code 1` run, and a human ruling on the visible result.

The zero-fee governed intake currently covers RetopoFlow, PolyQuilt, BSurfaces, LoopTools, F2, Auto Mirror, Bool Tool, and Material Utilities. RetopoFlow code may be audited and adapted under its code license, but the repository must not absorb RetopoFlow's excluded non-code assets. The factory stores provenance, adapters, probes, and results—not copied vendor payloads.

## Acceptance bundle

Each run retains the prompt, compiler version, typed recipe, both hashes, source identity, Blender version, immutable workspace/revision IDs, inspection and validation JSON, GLB/.blend hashes, clay/wire/raking views when available, rejected-history links, and `humanAcceptance: unreviewed` until Drew rules on the actual artifact.
