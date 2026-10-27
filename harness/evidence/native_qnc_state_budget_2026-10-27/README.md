# Saved seven-cell QNC state budget — 2026-10-27

This companion uses the immutable [PR461 state7 packet](../native_qnc_state7_2026-10-27/README.md). It adds **no host, KDM6, RTTOV or optimizer run**. The historical manifest, its 25 packet assets and its published analysis are checked before the current analyzer is used. The original packet's source pins are not rewritten.

## What changed

The aggregate PR461 analyzer now requires both the ordinary RK3 QNC output and the preserved `SCALAR_OLD` buffer to match a source-compatible arithmetic candidate. A one-ULP change in `RKSCALAR_AFTER.SCALAR_OLD` is rejected for both control and alpha0.25. The unmodified cases retain their previous analysis fields and values.

The new exact-rational calculation treats each saved binary32 word as a rational number. It separates the target QNC result into an exact saved-face/PD baseline, the stored PD old-buffer effect, the recorded-versus-face advection arithmetic effect, and the final RK calculation/store effect. It then applies `beta=-1/(MSFTX*MSFTY*RDZW)` to all seven cells. Twelve internal correction/low-order face pairs cancel exactly; the state ledger includes the 30 outer face incidences, PD source, and the three arithmetic differences. The unexplained seven-cell residual is exactly zero **after those differences are included**.

| Target raw QNC contribution | Control | Alpha0.25 |
| --- | ---: | ---: |
| Exact saved-face/PD baseline | +2.060925420 | −0.062541972 |
| PD old-buffer storage | −1.775498619 | −1.775498533 |
| Recorded advection minus exact face expression | +1.804024046 | −3.214212457 |
| Final RK arithmetic and storage | +1.353089799 | +1.237853719 |
| Actual RK3 QNC | **+3.442540646** | **−3.814399242** |

The same saved packet locates the alpha0.25 target's NC transition between **KDM FP64 input −3.8143992424 and FP64 output 0**, while output QC is positive (`6.38586157×10⁻⁵ kg/kg dry`). Host `MOMENTS_POST` retains NC 0 and positive QC. This identifies a call boundary; it does not identify a named internal KDM process.

## Replay

From the repository root:

```sh
python3 -m harness.evidence.native_qnc_state_budget_2026-10-27.replay
```

The replay verifies the old and new packet hashes, checks the unchanged historical producer/source pins, verifies a [snapshot of the original PR461 analyzer](source_snapshots/pr461_analyze_native_qnc_state7_trace.py.txt) against its historical pin, compares the hardened analyzer with the historical analysis, then reproduces [analysis.json](analysis.json) byte for byte. The new packet pins the current source separately. The target KDM records are joined to the sole wrapper call whose tile bounds contain `(221,63,6)`.

The prior PR459 source-grouped face/tendency checks remain in that historical packet; this companion reuses its saved face records and the PR460 exact weighted ledger without rerunning the 21 directional source-order checks. The old state7 trace has **728 typed records: 686 f32 and 42 bool**, as clarified here without editing its historical README.

These are raw numerical-coordinate budgets conditional on the saved f32 operands. They do not certify NC's physical unit, actual emitted FMA instructions, whole-step or domain particle-number conservation, a changed full-host forward, candidate RTTOV cost, or an accepted analysis.
