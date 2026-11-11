---
title: Full selected f32 column from a native host call
type: source
date: 2026-11-11
---

# Full selected f32 column from a native host call

The [evidence packet](../../harness/evidence/native_host_column_f32_2026-11-11/README.md) publishes all 39 levels of the `(203,149)` column from the private #579 host tile: 624 input state/forcing f32 words and 510 output state/precipitation/RHOG words, while the rest of the tile stays private. The column is packed `(201,6)` within the actual second `232×39×139` C ABI tile at the 00:00:00→00:00:20 step, with runtime index 27945. Public replay checks complete word inventories, #579 three-level spot links and the saved B=1 output comparison; optional private tile replay is needed to independently verify extraction from the host tile.

The exact 624-word input was separately run through the installed f32 `kdm6_step_c`, with 510/510 outputs equal to its tile-selected output. Isolated scalar-capture DSO calls with capture off/on also match those output words. Optional private replay now reruns the full tile and the B=1 column with the installed DSO; it does not rerun the capture DSO. The live B=1 activation trace at native level 16 has `sw_percent≈0.8224`, pow operand `≈1.3814>1`, selected fraction `1`, and raw activation rate equal to NCCN cap. Its independent Python pow check permits 4 f32 ULP; cloud-complete evaporation is a recorded mask input. This trace was captured in the **separate B=1 replay**, not inside the WRF tile, and does not identify a tie derivative or internal schedule.

The #556/#578 input is from a different 00:00:40 checkpoint and historical f64 computation, so its boundary cannot be transferred to this 00:00:00 installed-f32 host input. A bounded TH sweep on the new input stopped after the separate rate-cap branch changed before a threshold was bracketed; no new boundary is certified. Full-tile host source, physical budgets, host AD, observation pressure interfaces and GK2A–RTTOV cost sensitivity remain open; scientific and physical-unit statuses remain `INCONCLUSIVE`.
