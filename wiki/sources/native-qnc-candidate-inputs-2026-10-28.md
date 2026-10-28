---
title: Native QNC candidate-input faces and receivers — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC candidate-input faces and receivers

Following [[native-qnc-domain-preflight-2026-10-28]], four accepted
full-domain trace off/on steps captured the six pre-limit and final
post-limit correction faces, low-order faces, and RK inputs for 54 liquid
failure-layer donors and their six immediate receivers. The 374-cell union
plus eight sampled tile-seam sentinels yields 382 face/state cells. No
limiter physics was changed; control and α endpoints match PR #474.

For both cases, 324 donor/receiver internal face incidences have identical
pre/post/low f32 words on both sides. Their post words reproduce the
recorded outward donor scale: 318 faces are outgoing from the selected
donor and six from its neighbor. All 382 original tendencies and RK outputs
have source-compatible arithmetic. Four sampled Y-seam face pairs also
match across the two local tile arrays, including nonzero faces.

This closes the missing-input gap for a declared **54-donor frozen-input
counterfactual**. The capture does not cover all active QNC donors, a
changed-scale seam, or multi-rank halos. The same α checkpoint remains
invalid on 54 fixed-M0 profiles / 378 channel cells. A numerical QNC
candidate still needs simultaneous shared-face application and receiver
state checks; physical number conservation separately needs a resolved
host/KDM/RTTOV unit basis. See the [report](../../docs/NATIVE_QNC_CANDIDATE_INPUTS_20261028.md)
and [packet](../../harness/evidence/native_qnc_candidate_inputs_2026-10-28/README.md).
