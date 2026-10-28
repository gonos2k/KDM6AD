# Saved-face QNC residual and local scale probe, 2026-10-28

This is an **offline calculation** on the immutable PR #469 raw QNC producer
trace and PR #468 RK3 state trace at native `(i,j,k)=(113,70,12)`. It makes
zero host, KDM, RTTOV and optimizer calls. The original packet files and
their source pins are left unchanged. `manifest.json` fixes the source and
input hashes for this companion replay.

The analyzer first confirms that all six target correction faces are outgoing,
each recorded post-limit word equals a binary32 multiplication of its
pre-limit word by the recorded target scale, and every low-order face keeps
the same word. Both cases took the limiter branch with
`SCALE=3C54898F` (`0.012972249649465084`). The calculation then reads
the same saved RK `SCALAR_OLD`, mass factors, `MSFTY`, `DT_RK` and zero
`SCALAR_TEND` used in PR #469.
It also checks that the recorded scale is compatible with the source's
binary32 `max(0, PH_LOW/(FLUX_OUT+1e-20))` operation sequence.

## Exact real arithmetic on the saved binary32 words

For the selected numerical coordinate, let `D_low` and `D_corr` be the
Z→X→Y face-divergence contributions made from the stored low-order and
post-limit correction faces. Then

\[
A=a_{old}q_{old}+\Delta t\,MSFTY\,D_{low},\qquad
O=-\Delta t\,MSFTY\,D_{corr},\qquad R=A-O.
\]

The analyzer stores exact `Fraction` values and their decimal display values.
It divides `R` by the positive saved-input new mass factor to report the
corresponding exact-real QNC coordinate.

| Frozen saved-face calculation | Control | α=0.25 |
| --- | ---: | ---: |
| Available amount `A` | 4,237,102,030.521587 | 4,237,098,504.170056 |
| Applied correction outflow `O` | 4,237,101,865.984564 | 4,237,098,913.951257 |
| **Residual `A−O`** | **+164.537023** | **−409.781200** |
| Exact-real saved-face QNC | +0.001727296861 | **−0.004301851181** |
| Recorded full-host binary32 QNC | +0.001692894381 | **−0.006369509734** |

The α residual is negative even when the **already rounded saved faces** are
combined without further arithmetic rounding. This identifies a limit of a
fix applied only to the final RK subtraction, division or storage. It does
not predict a whole-host rerun at different precision.

The limiter's own stored `PH_LOW` and `FLUX_OUT` are a **different numerical
pair** from `A` and `O` above. Evaluating `PH_LOW−FLUX_OUT×SCALE` exactly from
those stored words gives **−44.020629883** for control and **+28.576782227**
for α. Thus even a positive stored-input threshold margin does not imply a
positive residual after the actual rounded faces are applied to the RK state.
The replay reports both definitions separately.

## One binary32 ULP lower target scale

The counterfactual changes the scale word from `3C54898F` to `3C54898E`.
It recomputes only the six target correction-face words using binary32
multiplication. It keeps low-order faces, previous state and RK operands
frozen. Six control face words and five α face words change after rounding.

| α=0.25 local counterfactual | Result |
| --- | ---: |
| Exact-real residual from changed stored faces | **−111.694128672** |
| Exact-real saved-face QNC | **−0.001172556278** |
| QNC from the four original-compatible directional modes and original-compatible RK mode | **+0.001692894381** in every mode |

The binary32 output is positive while the exact-real residual of those same
stored faces remains negative. A final-state sign alone is therefore an
insufficient acceptance test for a general limiter correction. This probe
does **not** apply changed faces to their six neighboring cells, run the
host, or test the fixed full-domain observation support. It makes no
physical particle-number or conservation claim: the raw NC unit and
mass/volume mapping remain uncertified.

## Replay

```bash
python3 -m harness.evidence.native_qnc_saved_face_probe_2026-10-28.replay
```

The versioned replay checks parent manifests and frozen inputs, this
packet's source and asset hashes, original face multiplication and low-face
invariants, source-compatible RK3 modes, exact fractions and the published
`analysis.json` bytes. All calculations are local and value-only. The α
candidate still loses **54 M0 profiles / 378 channel cells** in its unchanged
full-host checkpoint, so its full-support RTTOV cost remains undefined and
there is no accepted second assimilation.
