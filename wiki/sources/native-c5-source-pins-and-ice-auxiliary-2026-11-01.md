---
title: Native C5 evidence source pins and ice auxiliary response — 2026-11-01
type: source
date: 2026-11-01
---
# Native C5 source pins and ice auxiliary response

The native C3/C4 and C5 packets now retain the public source bytes from their
respective executions. Their run receipts authenticate these snapshots; the
compiled capture overlays remain separately identified. A later change to the
live C++ coordinator no longer makes the earlier C3/C4 local replay fail.
Current oracle and replay sources are still pinned separately, so their edits
require review and a manifest update.

At the selected native levels 21 and 23, C3 and C5 read `pre.supcol` and
`forcing.dend` from the same unchanged tensors. The C5 verifier requires the
two recorded dtypes and raw words to agree. Re-pinned mutations of either
shared operand are rejected even when the chosen C5 output is unaffected.

On the captured smooth ice branch, QI and NI determine the local slope,
`rslope2_i`, and intercept `n0i`. Recomputing those auxiliaries matches their
captured f64 bits at both levels. Passing them through C4, the ordered limiter
and the ice state update preserves the captured baseline output bits. At level
23, the extra QI output sensitivity per unit relative change is
`+7.237213036e−8` for QI and `+1.447442543e−7` for NI. JVP, VJP, represented
central differences and endpoint branch checks support these conditional
values. The earlier map with frozen auxiliaries remains a separate diagnostic.
The auxiliary CLI verifies one packet byte string before forming both level
views. Its C4 audit uses the recomputed intercept and slope that C4 consumes;
a nearby half-saturation cap probe checks that the audited winner changes with
the actual selected rate. Exact selected-branch ties remain outside the local
derivative claim.

This result uses the post-freeze working coordinate, fixed density and fixed
other producer inputs. The selected number rewrite is inactive. It does not
certify an upstream host derivative or the physical basis of QNICE;
`scientific_status: INCONCLUSIVE` remains.

See the [C3/C4 packet](../../harness/evidence/native_c3_c4_dsd_call_2026-11-01/README.md),
[C5 packet and local replay](../../harness/evidence/native_c5_limiter_call_2026-11-01/README.md),
and [detailed derivative note](../../docs/NATIVE_C5_LIMITER_SAME_CALL_AD_20261101.md).
