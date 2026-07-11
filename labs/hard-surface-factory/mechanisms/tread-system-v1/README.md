# Tread System v1

A mechanism is an instanced piece set plus the system that places and animates those pieces. This first mechanism uses procedural tread shoes and deterministic belt placement instead of a completed tank model.

## Controls

- Joystick up/down: tank-local forward/back.
- Joystick left/right: tank-local yaw turn.
- Camera orbit does not affect movement direction.
- Differential tracks are derived from joystick input: left speed is `forward + turn`, right speed is `forward - turn`.

## Geometry

The tread shoes are instanced procedural hard-surface pieces. The side belts use one shared rounded-rectangle path definition mirrored across the track gauge.
