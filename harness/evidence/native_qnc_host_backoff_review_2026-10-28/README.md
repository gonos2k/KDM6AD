# Current-source guard and three-baseline QNC response — 2026-10-28

This companion preserves the immutable [PR #465 host-variant packet](../native_qnc_host_backoff_2026-10-27/README.md). Its historical replay and manifest represent the code and results published in that PR. The current command below additionally pins both calculation files that the historical replay calls transitively: `harness/analyze_saved_qnc_scale_backoff.py` and `harness/analyze_native_qnc_saved_state_budget.py`. It rejects a comment-only source change or substitution of the archived pre-gate budget analyzer **before** calculating anything.

```sh
python3 -m harness.evidence.native_qnc_host_backoff_review_2026-10-28.replay
```

The command checks the 24 historical assets, all historically declared source pins, the two newly pinned current calculators, and the published full-domain baseline array. It then reproduces every PR #465 numerical result byte for byte and calculates the following comparison on the **same original B512 block 28, observation values and 2,009 supported channel cells**:

| Target IR105 / block-28 M0 | Original control baseline | Variant control | Variant alpha0.25 |
| --- | ---: | ---: | ---: |
| Target simulated BT, K | 285.822573426 | 286.148468954 | 285.822483468 |
| Target simulated−observed, K | +11.119694463 | +11.445589991 | +11.119604505 |
| Block M0 RMSE, K | 24.475896309 | 24.476204946 | 24.474283624 |

The target's variant-control→variant-alpha IR105 change is **−0.325985487 K**. Relative to the **original control baseline**, variant alpha changes target IR105 by only **−0.000089958 K**. Variant control itself differs from the original target by +0.325895528 K. Across block 28, 284 supported profiles have a changed BT between original baseline and variant alpha, so its block RMSE decrease of about 0.001612685 K cannot be attributed to one repaired NC value. The original full-domain M0 still loses 54 profiles / 378 channel cells in variant alpha; its total fixed-support candidate cost remains undefined.

All numbers are an offline comparison of hash-bound arrays; **this replay makes zero host, KDM6, RTTOV and optimizer calls**. The four host steps and two direct RTTOV calls belong to the historical PR #465 experiment. The model checkpoint time is 00:01:00 against an observation bundle nominally 00:00; pixel UTC remains unverified. Physical raw-NC units, a general limiter rule, an accepted analysis and another assimilation remain open.

## The 54 remaining fixed-support failures

A [source-pinned value-only producer](../../native_qnc_residual_reason_producer.py) reads the **pre-command pre-solve READY40 checkpoint** and the candidate's final 00:01:00 checkpoint. A [path-free session receipt](ready_boundary_receipt.json) binds that READY hash to the T/Q command's background, the initial input, applied-point counts and the final checkpoint. The intervening `ANALYSIS_TQ` command writes THM_2 and QVAPOR only, so it does not directly alter the four hydrometeor moment fields used by this classification; no separate post-command READY40 checkpoint was observed. The producer binds both checkpoint hashes, the published M0 and PR #465 hard-mask SHA. The [54 path-free profile records](residual_reason_rows.json) preserve raw f32 words at every failing READY/final level; replay checks their coordinate, reason and channel counts against the original M0 support.

| Final profile condition on M0 | Count |
| --- | ---: |
| QC>0 with NC≤0 | **53** |
| QI>0 with NI≤0 | **1** |
| Negative NC or NI | **0** |

Among those 54, **25 already fail at pre-command READY40** (24 liquid, one ice) and **29 become invalid by the final checkpoint** (all liquid). This is a two-checkpoint comparison across the command and the step, not an attribution to a particular transport or KDM process. The existing one-cell limiter probe leaves both classes largely unresolved.
