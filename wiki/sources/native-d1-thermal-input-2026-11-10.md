---
title: Native TH16 and QV16 to D1 thermal inputs
type: source
date: 2026-11-10
---

# Native TH16 and QV16 to D1 thermal inputs

The [evidence packet](../../harness/evidence/native_d1_thermal_input_cpp_ad_2026-11-10/README.md) follows one saved native column and a 20-second f64 C++ call. Packed `TH16` is potential temperature, seeded in absolute kelvin; with fixed `pii`, initial physical temperature is `T=TH*pii`. `QV16` is seeded relatively. The selected D1 chain carries QV through `cpm` and snow-updated `t1` to graupel raw melt; the selected QV-only `work2` tangent and value differences are zero. These are full-call tangents, not independent process-off effects.

Ten overlapping native TH/QV endpoints anchor 620 D1 producer words and 4,680 final-state words by raw bits. The D1 branch stays active and uncapped for all seven new pairs; only four pairs without a recorded activation-upper crossing enter the final NC derivative comparison. Other internal branches were not all independently observed and cannot be assumed fixed. TH `+0.01 K`, QV `−0.001`, and mixed `−0.001` cross the activation-fraction upper selection; the mixed endpoint has no independent native capture. A smooth D1 branch does not certify smooth downstream activation or NCCN branches.

The evidence is limited to this column and selected f64 directions. Physical units and conservation, operational f32, the full host adjoint and GK2A–RTTOV cost sensitivity remain open. Scientific and physical-unit statuses remain `INCONCLUSIVE`; public CI replays saved private execution rather than rebuilding the private runner and archive.

The 16 ULP `work2` allowance applies only to an independent Python partial diagnostic; it does not certify whole-replay libm portability. The ten native endpoints bind the consumed `work2` by raw bits.
