# Native NC16/NCCN16 full-call process graph (2026-11-08)

This packet follows the saved native `(203,149)` column, 39 levels, 20 seconds and f64 input through the actual frozen C++ `kdm6_fn` graph. The derivative inputs are initial native-level-17 QG and BRS (packed state indices `(6,16)` and `(11,16)`); the selected final outputs are native-level-16 NC and NCCN (packed `(8,15)` and `(7,15)`). The graph includes sedimentation, postfreeze `pre2`, C2c, the ordered shared limiter, `state_update`, reclassification, activation, the NCCN reservoir clamp, cleanup and final DSD. It is an isolated C++ column call, not a new host or RTTOV execution.

## Executed graph and source linkage

The #556 test-only hook already retains live `pre2` QG/BRS. This packet adds a gated map that retains selected live tensors at the existing native capture call sites **before** the capture's value-only detach branch. The added map observes 127 stage/field values at native level 16, 119 of them f64 numeric; it changes no production process calculation or packed C ABI. Removing the map and its single record call restores the #556 executed coordinator byte for byte. Hook off/on complete final states match by raw f64 bits.

The baseline stage values match 127 #553 captured native words and dtypes. Both endpoints of the previously captured joint `h=10^-3` direction match another 254 stage words. The complete final state and represented inputs at all 24 retained value endpoints match #556's C++ result; #556 independently links 18 of those endpoints to earlier #546 C ABI value captures. The new full NC16 468-component VJP is **raw-bit equal** to #545's C ABI NC16 VJP. The selected `pre2` VJP rows and all three `pre2` JVPs are raw-bit equal to #556. Private archive/executable bytes are identified by build/run SHA-256 receipts; public replay verifies the saved records and parent evidence, not a rebuild of those private binaries.

## What closes the conditional NC16 tangent

At the selected baseline, the warm cloud-number limiter is active as a gate but applies factor one; the cold gate is off. Across the baseline and 24 value endpoints, `nracw` and `naacw` are unchanged across both recorded limiter handoffs, and the source sum has positive NC margin. The NC budget uses the actual source order `-nraut - nccol - nracw - niacw*cold_mask - naacw - naacw`, with the `naacw` rate appearing twice. The value calculation, NC clamp, limiter-to-budget operands, activation transfer, NCCN clamp and final packed outputs are checked at all 25 selected cases.

The table gives **per unit relative initial-state direction** in saved numerical coordinates. Each number comes from one live C++ graph; the terms are budget contributions of the total rate tangents at this baseline, not independent process-off counterfactuals.

For all 119 numeric stage outputs, public replay also checks that the stored **joint-direction JVP equals the sum of the two single-direction JVPs** within the existing term-magnitude/ULP roundoff bound. This binds the individual `nracw` and `nraut` joint tangents to independently checked single-direction tangents; the budget sum alone would allow equal-and-opposite errors in these two terms.

| Initial direction | `-40 d(naacw)` | `-20 d(nracw)` | `-20 d(nraut)` | final `d(NC16)` |
| --- | ---: | ---: | ---: | ---: |
| QG17 | `+1,861,054.2766` | `-74,557.5240` | `+0.5928` | `+1,786,497.3453` |
| BRS17 | `-575,901.2599` | `-28,131.0381` | `-0.4589` | `-604,032.7570` |
| QG17+BRS17 | `+1,285,153.0166` | `-102,688.5622` | `+0.1338` | `+1,182,464.5883` |

For these three directions, the tangents of NC before `state_update`, the inline NC amount, `nccol` and masked `niacw` are zero. The source-order budget sum agrees with the full NC16 JVP within floating-point roundoff. The NC tangent is then raw-bit identical through state update, reclassification, activation, cleanup and DSD. Thus the **`102,688.4283` gap** between #556's joint QG/BRS-mediated conditional NC term and the full final NC16 tangent is accounted for here by `nracw` and `nraut` budget terms. This is a selected directional arithmetic decomposition, not a universal causal attribution of those rates.

The only C2c input tangents that are nonzero at native level 16 for these directions are QG, `avtg`, `g3pbg`, `rslope3_g` and `rslopeb_g`. The full graph's `ngacw` and `naacw` JVPs agree with #556's separately composed `pre2`-mediated tangents within roundoff. This identifies why #556's partial C2c term itself did not account for the entire NC tangent: the two warm rates also change.

## Activation, NCCN and directional differences

The selected baseline and all 24 endpoints retain activation fraction 1, `ncact=5,000,000`, no cloud complete evaporation, an active NCCN lower bound, and no NCCN upper bound. Activation adds `100,000,000` to NC; the lower bound restores NCCN to `100,000,000`. At this branch, the full NC16 tangent passes through these later steps unchanged. The final NCCN16 JVP for the three directions and all 468 components of its one-hot VJP are zero; all saved endpoints also finish at the same NCCN16 word. This is a **local numerical reservoir rule**, not a physical number-conservation finding or a derivative claim at the clamp boundary.

The runner evaluates independent high/low values at four relative half-steps per direction, using the actual represented input gaps. Six resolved process/NC signals are tested at each non-crossing pair with signal-relative error below `10^-6`; each endpoint is also compared to its baseline with an `O(h)` one-sided bound. Of the 12 pairs, seven have a previously captured non-crossing density-cap choice (maximum signal-relative residual `3.677×10^-7`), three additional `10^-6` pairs have no independent cap capture (maximum `7.544×10^-7`), and the QG/BRS single `10^-3` pairs cross the recorded density-900 cap and remain separate finite changes. The captured cap, limiter and activation conditions do not enumerate every branch in the complete runtime.

## Public replay and remaining limits

Run `python -m unittest discover -s harness/evidence/native_nc_process_graph_cpp_ad_2026-11-08 -v`, then `PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_nc_process_graph_cpp_ad_2026-11-08 -v`. Public replay calls the pinned #556 parent replay, validates source restoration and core/bridge/runner flags, checks captured baseline and joint endpoints, verifies the raw parent states and VJPs, reconstructs the selected value budget and branch choices, and tests the selected tangents and differences. Rehashed regression cases target source words, parent captures, individual and cancelling joint rate tangent changes, a shared intermediate endpoint offset, reservoir gating and the NC VJP.

Only six selected stage signals have independent directional-difference checks, and only the two chosen initial coordinates have been independently perturbed. Other numeric stage tangents are recorded and compared where a parent or source-order identity exists, without claiming an independent FD test for every one. Most intermediate endpoints lack a second independent capture. This single-column f64 result does not certify all state/forcing coordinates, operational f32 AD, physical units or process budgets, the full host adjoint, or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
