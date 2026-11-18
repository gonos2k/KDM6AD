# Host-selected column through the f64 DA ABI (2026-11-12)

This packet takes the **624 saved f32 input words** for the native `(203,149)` column from the [full host-column packet](../native_host_column_f32_2026-11-11/README.md), decodes each as IEEE f32, then widens it exactly to an f64 value. It preserves the 12 state and four forcing field orders, all 39 native levels, XLAND=2, `dt=20 s`, `ncmin_land=ncmin_sea=10`, and B=1 dimensions `(1,39,1)`. The source f32 word of every widened value is recovered by a round trip. These calls use the installed `kdm6_step_ad_c` **Legacy f64 state-AD ABI** with forcing held fixed. The runtime still stages its subcycle `dtcld` in f32; the graph's state and forcing arithmetic is f64. These are separate C ABI calls on an actual host-captured input, not perturbed WRF host-tile executions.

The f64 forward is a **different numerical map** from operational `kdm6_step_c` f32. At the baseline, 101 of 468 f64 output words, after rounding to f32, differ from the operational f32 output words. Within each f64 call, value-only and graph forwards produce the same 468 raw f64 output words. No f32 output parity or transfer of the [f32 boundary](../native_host_column_f32_boundary_2026-11-12/README.md) is claimed.

## f64 TH16 activation boundary and interior derivatives

The [private-run sweep](raw/boundary.json.gz) records 60 distinct TH16 inputs. Value-only calls through the captured DSO retain 33 f64 activation-stage operands and masks at native level 16. Searches for `sw_percent >= 0.48` and the recorded selected fraction `>= 1` independently terminate on the same **adjacent f64 input words**:

| Initial TH16 word | Lower `4074005089907cc6` | Upper `4074005089907cc7` |
| --- | ---: | ---: |
| Potential temperature | 320.01966244163884 K | 320.0196624416389 K |
| `sw_percent` | 0.4800000000002136% | 0.4799999999997473% |
| Pre-minimum pow | 1.000000000000267 | 0.9999999999996841 |
| Selected fraction | 1 | 0.9999999999996841 |
| Raw activation rate / NCCN cap | 5,000,000 / 5,000,000 | 4,999,999.9999984205 / 5,000,000 |
| Final NC16 | 100,000,000 | 99,999,999.99996841 |

The input gap is **5.684341886080802×10⁻¹⁴ K**. The NC16 upper−lower change is **−3.159046173095703×10⁻⁵**, or **2,120 f64 output ULP**. Seven of the 468 state words change; the recorded precipitation and RHOG diagnostics do not belong to the f64 packed AD output. These are discrete endpoint differences, not a boundary derivative or a uniqueness proof. The f64 boundary location differs from the f32 location because the maps differ.

Two strict interior TH16 centers are 0.01 K from the transition. At each center, the selected activation comparison masks stay fixed for both ends of the 10⁻³, 10⁻⁴ and 10⁻⁵ K central differences. This is a check of **captured activation masks**, not all microphysics branches. The installed f64 graph uses a unit TH16 direction and an NC16 output cotangent; full 468-word JVP and VJP buffers are retained.

| Interior side | NC16 JVP | NC16-seeded VJP at TH16 | Smallest-step central difference | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Fraction = 1 | 0 | 0 | 0 | All three NC16 endpoint pairs have identical output words; a nonzero derivative is unresolved. |
| Fraction < 1 | −788,214,669.5459847 | −788,214,669.545985 | −788,214,671.7987962 | Relative residual **2.8582×10⁻⁹** at represented h≈10⁻⁵ K. |

On the fraction-below-one side, the larger 10⁻³ K step has relative residual 1.8696×10⁻⁵; the 10⁻⁴ K step has 1.8734×10⁻⁷. This convergence supports the selected local NC16 state sensitivity. It does not assign that sensitivity to an independent physical process. The lower-side zero signal is reported as unresolved rather than counted as relative-accuracy evidence.

## Separate rate-cap tie operator test

The active research coordinator uses `torch::minimum(ncact_raw, NCCN_rate_cap)`. An [isolated two-input f64 C++ test](operator/main.cpp) varies these operands independently, unlike a whole-column TH perturbation. With raw below cap it gives JVP/VJP weights `(1,0)`; above cap `(0,1)`; at exact equality `(0.5,0.5)` for the observed Torch build. At the tie, one-sided value differences depend on the direction and generally differ from the AD tangent. This identifies the **operator's observed first-order convention** in that build, not the whole-column tie derivative or a physically admissible independent rate intervention. The receipt's coordinator SHA identifies the local source copy inspected when the standalone test was prepared; it differs from the research branch's whole-file SHA, although the minimum expression agrees. It is **not** a source pin for the installed DSO. The test's Torch loader paths and library hashes are recorded; its locally built executable is unavailable in public CI, and its build cache does not establish the installed KDM6 DSO's exact compiler provenance.

The [archived research coordinator](reviewed_source/coordinator.cpp.gz) pins the expression used for this source comparison, so future edits to the live coordinator cannot change the historical replay result. Its SHA is distinct from the local review-source SHA in the operator receipt; neither authenticates the installed DSO's build source.

## Evidence and limits

The [manifest](manifest.json) pins compressed byte-exact private results, source scripts, representative raw calls and complete endpoint/center capture CSVs, operator source/build receipts and their hashes. Public replay verifies the original JSON bytes after decompression, parent f32→f64 input mapping, f64 stage arithmetic and masks, boundary predicates, raw output links, AD/VJP buffers, represented finite differences, and the isolated operator result. The independent Python f64 pow calculation is a **16-ULP diagnostic**; captured C++ operands and their minimum handoff use recorded raw words. The private run reports identical installed/capture value and graph outputs at all 60 sampled points; public raw-array comparison is available at the baseline, two boundary endpoints and two interior centers. The remaining 55 parity entries are receipt checks, not independently re-executed public calls.

The underlying full host tile, installed/capture DSOs, binary execution and loader logs cannot be authenticated from public files alone. The capture-on f64 call is value-only because the instrumented capture path rejects graph capture; installed and capture-off graph values are separately compared to it. `cloud_complete_evap` is a recorded downstream mask with no reconstructed upstream producer here. Whole-host AD, forcing sensitivity, named-process applied budgets, native pressure/profile transfer, GK2A–RTTOV brightness-temperature and cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_host_column_f64_da_2026-11-12 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. This public suite replays saved evidence; it does not rebuild or rerun private binaries.
