# Native initial-state → postfreeze `pre2` input C++ AD (2026-11-08)

This packet measures how two **initial packed state coordinates** of the saved native `(203,149)` column affect the **native-level-16 post-D2–D4 `pre2` QG and BRS inputs** after the complete 20-second f64 `kdm6_fn` call. The initial coordinates are QG at packed `(6,16)` and BRS at `(11,16)`, both native level 17. The output level is packed index 15 (native level 16, capture `k_zero=23`). These are different input and output positions; the map includes sedimentation and intervening state updates.

## Executed map and provenance

The isolated C++ runner calls the actual frozen C++ `kdm6_fn` with the saved 12×39 state, four 39-level forcing fields, land flag 2, 20-second interval and legacy physics options. An opt-in hook retains live `working.qg` and `working.brs` tensors immediately before the second `rebuild_aux` call. Its code uses neither `detach` nor scalar extraction on the derivative path. Removing the three hook insertions restores the #553 executed coordinator byte for byte. The runner's hook-off and hook-on complete state outputs are also raw-bit equal to one another.

The base input binary is reconstructed byte for byte from the #545 C ABI NPZ. Its 468 hook-off and hook-on final state values match that packet's value and graph outputs by raw f64 bits. All 39 QG and 39 BRS hook values match the #553 producer's `pre2` input capture, accounting for reversed packed/capture vertical order. The 18 endpoints already present in #546 (three directions, three half-steps, two signs) match that packet's **complete 468-component final state** and perturbed input by raw bits. The #553 joint `h=10^-3` pre2 hook outputs also match its original endpoint captures. This links the added derivative hook to the prior native execution evidence without claiming a new host or RTTOV run.

`raw/build_receipt.json` and `raw/run_receipt.json` identify the runner, input, output, frozen source, static archive, executable, compiler flags and environment by SHA-256. The runner is built with `-ffp-contract=off` and assertions enabled. The frozen library build retains `-ffp-contract=off`; its private archive, DSO, object and executable are **not public binaries**. Public replay verifies the retained records and their cross-packet bitwise relations. It does not independently rebuild the private archive.

## Derivatives and directional differences

The full C++ graph supplies two 468-component VJP rows, one for each `pre2` output. Reverse-over-reverse autograd supplies JVPs for relative initial QG17, BRS17, and their joint direction. The reported numbers are derivatives with respect to the relative parameter at zero:

| Initial relative direction | `pre2` QG16 JVP | `pre2` BRS16 JVP |
| --- | ---: | ---: |
| QG17 | `+5.591441853878974e-5` | `+2.782177340696114e-8` |
| BRS17 | `-1.7297525833058086e-5` | `+1.5090862845999102e-8` |
| QG17+BRS17 | `+3.861689270573165e-5` | `+4.291263625296025e-8` |

Each JVP agrees with the corresponding VJP contraction under the stated floating-point rounding bound. Independent high/low **value evaluations** at half-steps `10^-3`, `10^-4`, `10^-5` and `10^-6` are compared with VJP times the actual represented input gap. Each non-crossing end is also checked separately against its anchored baseline with an `O(h)` one-sided bound; this prevents a shared offset of both saved intermediate endpoints from hiding in the central gap. The seven pairs with a previously captured **non-crossing density-cap choice** have maximum signal-relative residual `2.518×10^-8`. The three extra `10^-6` pairs also agree to at most `9.66×10^-10`, but their cap choice was not independently captured. The other two `10^-3` single-input pairs cross the previously recorded density-900 cap (QG positive, BRS negative); they remain as finite changes and are excluded from local derivative acceptance. Captured cap choices do not enumerate every full-call branch.

## Link to the #555 local process graph

The selected `pre2` QG/BRS baseline words are exactly the two leaf inputs of #555. Applying its separately validated two-input local VJP rows to this packet's `pre2` JVPs yields the **partial contribution mediated by these two inputs**:

| Initial relative direction | mediated `ngacw` | mediated `naacw` | mediated conditional NC budget |
| --- | ---: | ---: | ---: |
| QG17 | `+1168.6436076` | `-46526.3569139` | `+1861054.2766` |
| BRS17 | `-302.3574953` | `+14397.5314981` | `-575901.2599` |
| QG17+BRS17 | `+866.2861123` | `-32128.8254158` | `+1285153.0166` |

This composition is a calculation from **two separately executed graphs**. It does not include the changes in NC, QR/NR, rain slope, other C2c operands or other rates that accompany an initial-state perturbation. Nor does #555's conditional NC budget include the later activation, NCCN floor or final state. These mediated numbers therefore are **not** the full-call NC16 JVP, a process attribution of the entire NC16 response or a physical number budget. The full-call NC16 evidence remains in #545–#546.

## Public replay and limits

Run `python -m unittest discover -s harness/evidence/native_pre2_input_cpp_ad_2026-11-08 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. The replay invokes the pinned #546, #553 and #555 parent replays, then checks this packet's source restoration, core/bridge/runner build flags, run receipt, baseline, archived endpoints, selected coordinates and represented-input finite differences. Rehashed mutation tests reject a baseline hook word change, wrong input seed, jointly altered selected-coordinate JVP/VJP, parent endpoint state change and a shared intermediate-endpoint offset.

The archived VJP rows each contain 468 finite components. Public arithmetic checks their **two selected initial-state coordinates** through JVP and independent differences; the other 466 coordinates are an archived C++ result under the default file hash, without an independent coordinate sweep or FD check. A rehashed rewrite of an off-direction component can pass the arithmetic override, and a regression test records that limit. Individual intermediate endpoints outside the #553 joint pair also lack an independent pre2 capture; baseline anchoring and the one-sided bounds constrain them, while the original hashes and matched parent final states pin the retained run.

The result is a selected-column, selected-direction **conditional f64 upstream derivative**. The complete `pre2 → C2c → final NC` derivative in one graph, perturbations of other state or forcing coordinates, named-process attribution, operational f32, physical units and budgets, and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
