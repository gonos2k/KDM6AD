# Actual C4 and final DSD operands around ice saturation

The [replay](replay.py) extends PR #507's idealized **f64 public runtime** at `263.15 K`, `80 kPa`, `dt=1 s`, using the same initial qv offsets `-1e-12`, `0`, `+1e-12` around ice saturation. It scopes an observer around the actual `dep_sub_torch()` call while the PR #506 C3 observer records its own call. Each observer returns the **unmodified original output**. Every final `State` field is raw-bit equal to an unobserved run. It is a synthetic public calculation, not a private host or RTTOV run.

The replay retains C3 `pinud/ifsat`, all actual C4 ice inputs and output, its signed raw rate, four candidate bounds and all equal winning candidates. It reconstructs the **entire C4 `pidep` array** in the source's operation order and requires raw-bit equality with the producer. Producer `pidep` is compared separately to the cold rate and the **limited** cold rate; equality is observed in these cases, not presumed as a general rule. PR #505's state-update rate accounting checks the subsequent QI and NI application. The existing final DSD trace supplies its pre/post QI/NI, ice masks, slope and back-derived number boundaries; the replay checks the selected bound against the actual post-state.

| Initial qv excess over ice saturation | C3 outer / ifsat | Actual C4 raw `pidep` | C4 applied `pidep` and selection | Final DSD NI before → after | Final QI |
| --- | --- | ---: | --- | --- | ---: |
| `-1e-12` | false / false | `-9.70342656885e-22` | `+5.90511398498e-9`, **remaining-supply maximum** | `26.86839730 → 26.86839730` | `5.90511599351e-9` |
| `0` | false / false | `0` | `0`, **raw and half-saturation tie** | **`26.86839730 → 8.15540970`** | `2.00852730813e-15` |
| `+1e-12` | true / true | `+9.70342439827e-22` | `0`, **C4 ice `pidep` branch inactive due to C3 ifsat** | `27.12096929 → 27.12096929` | `5.02008525310e-13` |

Below saturation, C4 chooses a **maximum** because its raw rate is negative; the positive remaining-supply candidate reverses the selected sign. At exact saturation the nonnegative branch has an exact zero tie. The final DSD trace then marks ice `too_large` with the final number gate active, and its back-derived maximum-bound NI is exactly `8.15540970156244`; QI is unchanged at that step. Above saturation C4 is still called, but the C3 saturation-exhaustion flag disables its ice `pidep` branch. The three endpoint differences reflect **multiple executed branches**, so no single central derivative or global discontinuity is inferred from them.

The replay also runs the full public runtime at **253.15 K, 80 kPa** with initial ice-supersaturation offsets `1e-10` and `1e-9`. Both choose the C3 **half-saturation cap** strictly in all first-column levels with automatic `[1,1]` substeps. At `1e-9`, top-level C3 candidates are half `4.9999999811e-10`, deficit `4.1065941131e-9`, and remaining `6.8794435283e-9`. `qs_ice=7.9492014192e-4`; one binary32 qv spacing is `5.8207660913e-11`, so the offset spans about **17.18 spacings**. This remains an **f64 runtime result**: saturation, density and all upstream operands also round in operational f32, whose branch has not been run or certified.

Source SHA checks are bundled with this packet and parent replays. The manifest is a co-versioned consistency check, not independent authentication of a modified checkout or of a private executable. The scoped observers are single-thread diagnostics; the returned forward tensors retain their original graph. No new physical control or default microphysics formula is introduced.

```bash
python3 -m harness.evidence.ice_c4_dsd_boundary_2026-11-01.replay
python3 -m unittest discover -s harness/evidence/ice_c4_dsd_boundary_2026-11-01 -v
python3 -O -m unittest discover -s harness/evidence/ice_c4_dsd_boundary_2026-11-01 -v
```

**Scientific status: INCONCLUSIVE.** This packet does not certify f32 C++/Fortran branch equivalence, actual native QNICE units, a private host number budget, an RTTOV response, or analysis acceptance.
