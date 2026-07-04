---
title: WRF KIM-meso Host
type: entity
date_modified: 2026-06-25
---
# WRF KIM-meso Host

## Key Facts

- The host tree lives under `host/KIM-meso_v1.0/`.
- It dispatches [[KDM6]] as `mp_physics=37` and [[KDM6AD]] as `mp_physics=137`.
- The microphysics driver supplies the same WRF state surface to both schemes.

## Connections

- Owns the runtime integration surface for [[KDM6]] and [[KDM6AD]].
- Loads the self-built `libkdm6_c.dylib` for the [[KDM6AD]] mp137 path.
- Provides the SS real-case run artifacts used by [[KDM6AD Forward Parity]] evidence.

## From [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]

- Existing final SS run artifacts for mp37 and mp137 both exited 0 and completed WRF successfully.

