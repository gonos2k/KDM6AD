# Isolated target-QNC host backoff — 2026-10-27

This packet follows the saved one-ULP counterfactual in PR #463. It records **four actual full-domain 20-second MP137 host steps** from the same READY40 checkpoint: control and historical alpha0.25 T/Q input, each with the moment/face/state traces off and on. The host retained nonadiabatic physics (`NO_MP_HEATING=0`), one MPI rank, one thread and two tiles. The run used an isolated executable; the operational install, physical KDM process and ABI were not changed.

The opt-in [overlay](../../native_qnc_target_backoff_overlay.py) changes one outgoing limiter `scale` only when the already pinned QNC scalar context selects RK3 and native `(i,j,k)=(221,63,6)`. It uses Fortran `NEAREST(scale,-1.)` before the six shared face multiplications. This is a **target-specific diagnostic variant**, not a general one-ULP limiter rule. [Source/build lineage](SOURCE_RESOLUTION.md) separates the public producer from the private compiled source and executable.

## Executed response

| Target raw NC coordinate | Control | Alpha0.25 |
| --- | ---: | ---: |
| Original saved scale word | `3F4C9A4E` | `3F4C9A3C` |
| Variant scale word | `3F4C9A4D` | `3F4C9A3B` |
| Variant RK3 / KDM input NC | +10.699481010 | +1.991152167 |
| Variant KDM output / checkpoint NC | **+277,381.21875** | **+1.991152167** |

Both same-input trace off/on pairs have identical ACK and raw-bit final checkpoints across **652 variables / 322,426,586 numeric elements**. Six target–neighbor correction faces have identical words at both incidences. Relative to each historical same-input checkpoint, the variant changes only target-layer `QNCLOUD` and the forward diagnostic `RE_CLOUD`: one numeric element in each variable. `QCLOUD` and every other checkpoint value remain bitwise equal. The alpha target's `QCLOUD>0, NC=0` mismatch is removed; the control's small positive RK input instead triggers a large KDM NC response. The recorded KDM input/output boundary, rather than the RK output alone, defines the checkpoint result.

## Admissibility and observation response

On the original full-domain fixed observation support $M_0$, the historical alpha0.25 output lost **55 profiles / 385 channel cells** to hard moment conditions. The variant recovers only flat index **14728** (`i=221,j=63`), leaving **54 profiles / 378 channel cells** inadmissible. The [mask producer](../../native_qnc_support_mask_producer.py) was rerun on the three hash-pinned private checkpoints and reproduced [support_masks.npz](support_masks.npz) **byte for byte**; its [path-free receipt](support_mask_producer_receipt.json) binds source, inputs, M0 and output. That target passes the shared checkpoint profile validator. **No full-domain candidate RTTOV cost or accepted analysis is claimed.**

Two direct-only RTTOV calls evaluated the original **B512 block 28** from the variant control and alpha checkpoints. Both retain all **2,009** baseline-supported channel cells in this block; each RTTOV call received 508 of the 512 profiles after ordinary profile preflight, with K disabled. The target is full-block row 392 (0-based), compact RTTOV input row 390 (0-based), and profile directory 391 (1-based). At the target, IR105 simulated-minus-observed BT goes **+11.445589991 → +11.119604505 K** (0.325985487 K closer). Block-28 fixed-support RMSE is **24.476204946 → 24.474283624 K**. The other six target channels also reduce absolute residual, as recorded in [analysis.json](analysis.json). These are **local block diagnostics** at host time 00:01:00 against an observation bundle nominally 00:00; pixel UTC is unverified.

At native level 6 (RTTOV top-first layer 61), control and alpha have nearly identical actual profile T/Q and positive QC. The target's RTTOV liquid effective diameter changes **52 → 5.02 μm**. The observation adapter divides host raw NC by the checkpoint's live dry density `rho_d=1.0514361858 kg/m³`; the dry-number bridge multiplies by the **same** density before the DSD slope gate. [Saved operands](target_state.json) replay that conversion: the gate receives control `277381.21875` and alpha `1.991152167` in the legacy raw numerical coordinate. Alpha is below the executed `ncmin=10` gate while control is above it. This numerical gate comparison does not certify raw NC's physical particle-number unit. The host `RE_CLOUD` diagnostic and RTTOV `HYDRO_DEFF6` are distinct quantities; do not substitute one for the other. This optical branch difference makes the local BT response a finite model result, not a linear or named-process attribution.

## Offline reproduction

```sh
python3 -m harness.evidence.native_qnc_host_backoff_2026-10-27.replay
```

The replay checks packet files and source pins, binds four [path-free run plans](receipts/plans) to source plans, build, executable, DSO, READY40 and endpoints, compares **all six scaled correction faces and seven immediate RK states** with the saved PR #463 prediction, parses the KDM boundary trace, verifies the hard-mask producer receipt, recomputes fixed-support losses and the two block-28 BT comparisons from the published arrays, and reproduces `analysis.json` byte for byte. **The replay makes zero host/KDM/RTTOV/optimizer calls.** Full private checkpoints, generated Fortran, build objects, run directories and RTTOV executables are excluded. Their hashes and executed path are attributed in the receipts; the public replay cannot independently recompute the 652-variable checkpoint comparisons without those private artifacts.

The experiment shows one local moment repair and one local observation improvement. It does not certify raw NC physical units, whole-domain number conservation, a general positivity rule, valid post-KDM moments on all $M_0$, forecast skill or a second assimilation.
