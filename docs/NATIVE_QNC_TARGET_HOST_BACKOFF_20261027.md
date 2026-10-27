# Isolated target-QNC backoff host result — 2026-10-27

The [public packet](../harness/evidence/native_qnc_host_backoff_2026-10-27/README.md) records four actual full-domain 20-second runs of an opt-in MP137 host variant. A source-pinned overlay reduces the outgoing QNC/RK3 scale by one binary32 step at native `(221,63,6)` only. Nonadiabatic physics is active; model/ABI defaults are not changed. Trace off/on final checkpoints match raw bits in each input case.

The saved PR #463 calculation predicted the immediate RK3 result correctly: control NC `+10.699481010` and alpha0.25 NC `+1.991152167`. KDM then sends control NC to about `277,381.21875`, while the alpha value remains `+1.991152167`. The target's positive QC is retained. Historical same-input comparisons find exactly two changed checkpoint elements per case, both at the target: `QNCLOUD` and forward `RE_CLOUD`. Six internal correction faces are read with matching words from both cells. This is a target-specific finite response, not a general limiter correction or named KDM-process attribution.

## Required full-domain gate

The original $M_0$ has 53,906 supported profiles and 377,342 channel cells. This variant recovers the alpha target profile's seven channels, but **54 profiles / 378 cells still fail hard QC/NC or QI/NI moment validity**. The repaired target passes the existing per-profile validator. A source-pinned mask producer rerun on three private checkpoint hashes reproduced the public `support_masks.npz` bytes exactly. The full candidate remains inadmissible, so its $M_0$ RTTOV objective is undefined and no analysis is accepted.

## Original B512 block 28 diagnostic

The completed checkpoints were also sent directly to RTTOV on the original 512-column block containing the target. Both direct calls retain all 2,009 $M_0$ channel cells in that block. RTTOV receives 508 profiles after the usual four non-$M_0$ profile exclusions, with K disabled.

| Block 28 / target IR105 | Variant control | Variant alpha0.25 |
| --- | ---: | ---: |
| Target BT, K | 286.148468954 | 285.822483468 |
| Target simulated−observed, K | +11.445589991 | +11.119604505 |
| Block $M_0$ RMSE, K | 24.476204946 | 24.474283624 |

At RTTOV layer 61 (native level 6), actual profile temperature changes by about `+6.58×10⁻⁵ K`, moist-air humidity by about `+0.0454 ppmv`, and liquid content by about `+2.58×10⁻⁵ g/m³`. The liquid effective diameter moves **52 → 5.02 μm**. The adapter passes `NC_raw/rho_d` to the dry-number bridge, which multiplies by the same live `rho_d` before its DSD gate. The saved `AL/ALB` operands give `rho_d=1.0514361858 kg/m³`, so the gate's legacy raw-coordinate NC is `277381.21875` control and `1.991152167` alpha, against `ncmin=10`. This verifies the numerical inactive-branch comparison without assigning a physical unit to raw NC. The host `RE_CLOUD` diagnostic is not the RTTOV effective diameter. The response must be read as a finite combined T/Q/cloud optical effect, without assigning the 0.326 K IR105 improvement to one process.

This block comparison is not a full-domain success metric. The checkpoint time is 00:01:00; the observation bundle's nominal slot is 00:00, with pixel UTC unverified. Remaining work is a justified donor/receiver limiter rule, all-$M_0$ post-KDM moment validity, a full fixed-support cost, and a subsequent assimilation on an accepted state.
