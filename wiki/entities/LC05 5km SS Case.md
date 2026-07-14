---
title: LC05 5km SS Case
type: entity
date_modified: 2026-07-14
---
# LC05 5km SS Case

The **real 5 km SS case** that is the single target of the real-time data
assimilation. Full disambiguation map: `docs/HOST_RUN_LAYOUT.md`.

## Key Facts

- **Resolution: 5 km** (`DX/DY = 5000`), grid **234 × 282** (e_we 235 / e_sn 283),
  39 levels — WRF V4.6.0. **5 km is the fixed model resolution.**
- Run dir: **`host/lc05_da_run/`** (a symlink farm). Canonical case data lives
  OUTSIDE the repo at
  `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/`
  (`wrfinput_d01` 374 MB, `wrfbdy_d01`, all WRF tables).
- Observations: **GK2A 2025-07-19** (00/01 UTC), superobbed onto the 5 km grid
  → `obs_products/gk2a_superob_{0000,0100}.pt` (65 988 = 234×282 cells × 16 ch).
- Forcing: the 3 h 5 km forecast trajectory `klfs_lc05_fcst.202507190000`
  (3.6 GB, 37 frames, 5-min), produced by `../KIM-meso_v1.0/main/wrf.exe`.
- Evidence: `docs/reports/v10_fulldomain_lc05.json` (`n_domain = 65 988 = 234×282`
  confirms 5 km; input `wrfinput_d01` SHA-256 in the manifest).

## Connections

- The concrete case behind [[KDM6AD Forward Parity]] and the real-observation
  4D-Var described in `docs/DA_REALTIME_PLAN.md`.
- Runs on [[WRF KIM-meso Host]]; `wrf.exe` links the C ABI hardened in
  [[KDM6AD C ABI Hardening]] (host loads `libtorch/install/lib/libkdm6_c.dylib`).

> [!warning] Do not confuse with the previous experiments
> `host/KIM-meso_v1.0/run/` is a **100 km ideal** experiment (`ideal_case 7`,
> dx=100000, 41×81); `wrfinput_d01.37` there is a **1 km** per-scheme IC copy.
> Neither is this 5 km case. `/Users/yhlee/KDM6AD` (no `+`/`-k`) is a stale
> sibling. See [[host-run-dir-confusion-2026-07-14]].

Provenance: `docs/HOST_RUN_LAYOUT.md`; live `ncdump`/`otool` verification 2026-07-14.
