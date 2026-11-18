---
title: Native D1 graupel melt amount production
type: source
date: 2026-11-09
---

# Native D1 graupel melt amount production

The [evidence packet](../../harness/evidence/native_d1_melt_amount_producer_cpp_ad_2026-11-09/README.md) follows initial QG17/BRS17 directions through one selected native column and the 20-second f64 C++ call. Snow melt changes `t1`, which feeds `xka` and graupel bracket terms 1 and 2. Their source-order calculation produces signed raw rate `P`, candidate amount `B=P*dt`, then `A=where(warm && qg>0, min(max(B,-qg),0),0)`. `A` is the signed amount consumed by the D1 QR/NR update; `A/dt` is a separately stored applied rate. In the selected joint direction `d(t1)=d(xka)=0`; the two bracket terms have nonzero tangents. Parent outputs and JVPs/VJPs are checked for hook noninterference.

The #553 native producer capture anchors 62 fields in each of the baseline and two joint large-step endpoint cases. The other 22 endpoint intermediates are isolated C++ values without independent native capture. Source-order scalar replay checks three branch bits and 22 derived f64 values across all 25 cases. The [November 4 packet](../../harness/evidence/native_d1_melt_producer_ad_2026-11-04/README.md) instead describes conditional local QV/T derivatives in a different mp137 call; it does not establish these full-call QG17/BRS17 derivatives.

This selected active uncapped f64 path does not establish every upstream input derivative, active limiter-boundary behavior, physical units or number conservation, operational f32, host AD or GK2A–RTTOV cost sensitivity. Scientific and physical-unit statuses remain `INCONCLUSIVE`.
