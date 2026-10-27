# PD/RK coefficient gate and rounded QNC state ledger — 2026-10-27

This is an offline companion to the immutable [PR461 state trace](../native_qnc_state7_2026-10-27/README.md), [PR462 exact state budget](../native_qnc_state_budget_2026-10-27/README.md), and [PR463 saved scale probe](../native_qnc_scale_backoff_2026-10-27/README.md). No host, KDM6, RTTOV or optimizer call was made.

The state-budget analyzer now requires `C1H` and `C2H` to be **raw-bit identical** at PD before/after and ordinary RK3 before/after for every selected cell. Its RK old/new mass factors use the coefficients read from the actual RK record. Changing target RK `C2H` one ULP in both RK before/after rows is rejected in control and alpha0.25. All 14 unmodified cell budgets and every previously published PR463 result field remain identical.

## Exact face versus stored-state comparison

For each of seven cells, the saved candidate and original RK3 states are compared with

```text
beta = -1/(MSFTX * MSFTY * RDZW)
delta_weighted_state = beta * Anew * (QNC_candidate - QNC_original)
```

`Anew` is the **exact rational expression of the saved f32 RK operands** `C1H`, `C2H`, `MU_NEW` and `MU_BASE`; it is not an observed rounded mass-factor word. The exact expression uses each case's saved PD old buffer and recomputed paired faces. The binary32 comparison uses only original-compatible tendency/RK arithmetic candidates and the original stored QNC.

| Seven-cell numerical-coordinate change | Control | Alpha0.25 |
| --- | ---: | ---: |
| Exact expression from saved operands | **0 exactly** | **0 exactly** |
| Final compatible binary32 state words | **+12,836.142997905** | **+10,268.913337873** |
| Neighbors with unchanged final QNC bits | 6/6 | 6/6 |

These nonzero values arise from the target's changed final binary32 state after large terms are rounded; the six neighbors keep their stored QNC bits. Exact paired-face cancellation and exact weighted state equality therefore **do not imply bitwise conservation of the rounded states**. The weight and raw NC coordinate are not certified physical air mass, volume or particle-number units, so the displayed change is not a physical particle source.

## Replay and provenance

```sh
python3 -m harness.evidence.native_qnc_coeff_rounding_2026-10-27.replay
```

The replay checks the three historical packet manifests and all listed assets, compares their past analyzer source pins with versioned snapshots, verifies unchanged sources, and requires all old saved budget/backoff fields to remain numerically identical. It then regenerates [analysis.json](analysis.json) byte for byte. The historic packets and their manifests are left unchanged.

This closes a validation gap and records a saved-input numerical diagnostic. It does not establish a generally correct one-ULP limiter rule, whole-domain positivity, a physical number budget, a new host variant, post-KDM admissibility, candidate RTTOV cost or a second assimilation.
