# One restricted-control KO7 confirmation

PR #447 completed the original full-domain case with no acceptable update.
This follow-up preserves that result and screens one post-hoc control-space
projection. It keeps every baseline observation, weight and the global
normalizer Z=381,528. The physical operator and original 128×B512+B452
partition remain unchanged.

The first actual confirmation completed as `RESTRICTED_UPDATE_ACCEPTED`:
129/129 blocks, unchanged support, J=11.144979224162192 and exact agreement
with screening. Full state/rate arrays and public replay are linked in
[the measured report](../harness/evidence/native_satellite_restricted_2026-10-25/REPORT.md).

The union of the three rejected proposals' lost profiles occupies 25 original
blocks. Both T/Q controls are frozen in those blocks; their observations still
contribute to the cost. The other 104 blocks retain the original alpha=1
proposal. This is a discontinuous, batch-dependent search subspace, not a
smooth spatial analysis or a new optimizer.

## Fixed candidate

For the parent normalized native gradient, form `g_z=where(active,S*g,0)` and
`d0=-g_z/max(abs(g_z))` over the complete array. Then assign positive zero to
both controls in the frozen blocks. Do not renormalize after projection.

```text
Frozen block IDs (0-based):
1,35,51,52,53,54,60,62,64,66,67,69,70,73,82,89,91,93,100,102,
108,109,113,118,124
```

The source-bound [candidate specification](../harness/evidence/native_satellite_restricted_2026-10-25/restricted_candidate_sourcebound.json)
pins z SHA-256 `1177f076e4d8421bfe855f3fd9e064d54bedcf353fcda211c35a4d7059710c38`.
The full-array expression retains negative zero outside active controls.
The older bounded helper initialized those positions with positive zero.
There are 789,828 zero-sign differences, but the reconstructed native T/Q
inputs are bit-identical. Both the alternate hash and this qualification are
retained in the independent screening audit; no hash tolerance is used.

Saved-array reconstruction gives J=11.144979224162192, versus parent
11.153458878209252 (about 0.076% lower). The first actual 129-block forward
confirmed this exact value and accepted the restricted update. Screening and
actual execution remain separate evidence; neither establishes forecast skill.

## Execution boundary

Use the parent-exact physics source snapshot, with only the new runner and
objective helper overlaid. Pin the snapshot and referenced publication/input
assets before execution. The known parent `native_batch_microphysics.py`
EOF-byte distinction is preserved rather than silently waived by the source
gate. Private host inputs, the isolated research library and RTTOV assets are
required; a public checkout alone cannot execute this scientific case.

```sh
python -m harness.run_native_satellite_case \
  --stage restricted-confirmation \
  --parent-run /path/to/parent/RUN_v4 \
  --candidate-json /path/to/restricted_candidate_sourcebound.json \
  --output-root /path/to/new/RUN \
  --workers 3 --preflight-only
```

Omit `--preflight-only` for the single confirmation. All original blocks are
actually evaluated, including frozen blocks. The budget is 129 KDM value-only
forwards and at most 129 fresh RTTOV direct calls, with zero K/JVP/VJP or host
calls. There is no automatic additional alpha. Explicit `--resume` accepts
only matching run/stage/parent/control receipts.

The runner writes `CONFIRMATION.json` after all blocks. It compares fixed
support, actual BT/quality and global cost against the saved-array prediction.
A reproduced support-preserving cost decrease is an accepted restricted
candidate; disagreement remains a reproduction mismatch. Required state/rate
exports, figures and audits must finish before a final completion marker.

The public exception wrapper also protects parent/unrelated runs from failure
markers and keeps preflight read-only. That exception-path correction is
separately attributed from the already frozen execution source; it changes no
successful physical calculation.

## Applied state and named rates

`export_restricted_tendencies` reads the parent baseline and new confirmation
receipts; it requires no child baseline manifest and makes no model calls.
The same new KDM calls capture before/raw/forcing buffers. A local cleanup
replay must match the actual QV/cloud outputs before those arrays are used.

Export full native H_RATE, QV_RATE and QC_RATE arrays for baseline, candidate
and their differences, together with actual receiving T/Q/QC states. H_RATE
is finish-defined moist-theta heating memory in K/s, including the clip and
water cross-term. QV/QC rates are cleaned-minus-input mixing ratios divided
by 20 seconds. The old-state subtraction is retained. RTTOV consumes the
applied state and live EOS/profile; do not apply the rate a second time.

Per-column raw/cleanup/applied water changes use each call's actual DEN×DELZ.
Across-column summaries are unweighted diagnostic sums, not regional mass.
Precipitation is not captured, so no closed water/energy/number budget is
certified. Pixel UTC, provider navigation, IR133 spectral identity and legacy
host number-unit qualifications remain unchanged. No native host/RK cycle is
performed.
