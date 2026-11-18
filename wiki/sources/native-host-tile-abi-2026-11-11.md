---
title: Private native host tile f32 ABI replay receipt
type: source
date: 2026-11-11
---

# Private native host tile f32 ABI replay receipt

The [public receipt packet](../../harness/evidence/native_host_tile_abi_2026-11-11/README.md) describes a private one-rank, one-thread WRF `mp_physics=137` call at the 2025-07-19 00:00:00→00:00:20 step. The actual second ABI tile is `232×39×139`; host bounds and clipping place native `(203,149)` at packed `(201,6)`, runtime index 27945. Replaying the entire captured f32 tile through the same installed DSO recorded zero raw output mismatches for the 12 state arrays, three precipitation increments and RHOG. A separate B=1 call of the mapped column also matched its tile output, without exposing the internal substep schedule.

In sequential proxy-on/off host runs, 254 forecast and five energy variables matched by raw bits at both saved times, 00:00:00 and 00:00:20. Ocean and precipitation streams had no saved frames. The earlier #556 native-column input originated at a 00:00:40 checkpoint under an isolated f64 path; its complete 16×39 signature was absent from this f32 tile. The #578 activation boundary therefore cannot be transferred to this host call by input identity.

The full tile, NetCDF frames and binary libraries remain in private `host/research_evidence/`. Public CI checks only the distributed receipt and selected three-level summaries; optional replay with the private tile and matching DSO recomputes the full ABI output locally. The comparator hash was established retrospectively, the paired-on run has no separate live loader snapshot, and the public proxy source is a sanitized view of the private executed file. Public metadata alone does not authenticate the WRF invocation. This case does not establish mp37 parity, land/sea ncmin discrimination, host AD, physical budgets or GK2A–RTTOV cost sensitivity; scientific and physical-unit statuses remain `INCONCLUSIVE`.
