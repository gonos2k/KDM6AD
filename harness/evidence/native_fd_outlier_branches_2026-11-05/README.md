# Selected native-column finite-step branch trace (2026-11-05)

This packet traces three finite-difference discrepancies retained by the [parent 39-level state-AD packet](../skipped_substep_ad_2026-11-05/README.md). The input is the same captured native `(203,149)` column and 20-second call. A newly isolated, value-only f64 C ABI DSO evaluates one-column baseline and ten QV/QG endpoints. It is **not** a new perturbed host run or a new C++ AD calculation. The parent packet supplies the previously verified JVPs. The operational f32 path, QNICE physical units and GK2A–RTTOV derivative remain outside this evidence; `scientific_status` and `physical_unit_status` are `INCONCLUSIVE`.

## Execution and raw-value continuity

The new coordinator source is the parent executed source plus **56 value-only `capture_native_tensor("fd_...")` calls**. Removing those calls recovers the parent source byte for byte. The isolated build used Torch 2.13.0, AppleClang, `-ffp-contract=off`, native capture ON and test hooks OFF. [Build receipt](raw/build_receipt.json) pins the private DSO, archive, coordinator object and source hashes. [Run receipt](raw/run_receipt.json) binds that DSO to the baseline and all ten calls, their inputs, logs, 13,455-row captures and NPZ outputs. The DSO/archive bytes are private; the public replay checks their recorded hash chain and the published source/build inputs, not an independent binary rebuild.

Each new capture retains the parent's **11,271 rows in the same order, dtype and raw word** and adds 56 fields × 39 levels = 2,184 rows. Every new value-only output is raw-f64-equal to the parent C ABI endpoint: **11 calls × 12 states × 39 levels = 5,148 words**. The baseline also matches the earlier native host exit. Full-K fields inside `sedimentation_chain` use top-first tensors; `capture_native_tensor` flips them on writing. Therefore the `fd_main` row `k_zero=15` refers to native level 16, while runtime and D1 rows use `k_zero=23`. The replay checks this mapping against QG and BRS handoffs rather than assuming equal CSV indices. It also requires `fd_main` to have `(one_step_call,runtime_call,substep)=(0,1,0)` and the later `fd_*` stages to have `(1,1,0)`; rehashed call-ID mutations are rejected.

## QV: activation-fraction cap at the large negative endpoint

The warm-cloud activation code computes `sw_percent=(qv/qs1-1)×100`, then `activated_fraction=min(1, (max(sw_percent/0.48,0))^ACTK)`. The QV `h=10^-3` negative endpoint selects the interior fraction; the baseline and positive endpoint select the cap:

| QV relative endpoint | `sw_percent` | activated fraction | `ncact` rate | NC after activation |
| --- | ---: | ---: | ---: | ---: |
| `-10^-3` | `0.39161041560900056` | `0.8850499829878339` | `3539669.6619642465` | `224874319.1918568` |
| baseline | `0.4904546956316258` | `1` | `5000000` | `254080925.8395777` |
| `+10^-3` | `0.5892971376236344` | `1` | `5000000` | `254080925.72658485` |

All three have `sw_percent>0` and cloud-complete-evaporation false. The branch change is at the **fraction cap `sw_percent=0.48`**, not the positive-supersaturation gate. The saved NC state entering activation plus `20×ncact` reproduces the activated NC. At native level 16, the captured NC then carries raw-equal through satadj completion, cleanup, final DSD limiting and the output. QV `h=10^-4` keeps its negative endpoint just above the fraction cap (`0.48057035034152484`) and remains a selected local FD check.

For QV `h=10^-5`, both endpoints retain fraction 1. The parent FD–JVP residual in final NC converts to **1.6311 output f64 ULP** at the represented input gap. That is a roundoff-scale observation, not proof that all unrecorded branches stayed fixed or that a specific reduction caused the residual.

## QG: entry ProgB density cap at the large negative endpoint

The initially captured graupel input has an uncapped `QG/BRS` ratio **`900.0012493236287`**. Entry ProgB clamps it to 900. With QG relative `h=10^-5`, the negative endpoint has ratio **`899.9922493111354`**, so it enters the interior branch; the positive endpoint has **`900.010249336122`** and remains capped. The `h=10^-6` endpoints both remain above 900. The conditional crossing is at approximately **`-1.388135438262772×10^-6`** relative QG change when the input BRS is held fixed.

The independently recomputed `QG/clamp(QG/BRS,100,900)` matches each recorded entry BRS in raw f64 bits. The captured input NR and D1 `nr_before` are unchanged across QG endpoints; the first recorded NR state split is D1's sequential `nr2` store. For the final NR16, the `h=10^-5` positive one-sided secant is **`-8.5372693774`**, close to the parent JVP **`-8.5372854227`**, while the negative one-sided secant is **`-41.4858007386`**. This demonstrates a cap crossing inside the central difference. The new trace does not prove that this crossing alone accounts for every downstream contribution to the final NR residual; D1 and D5 rate production also respond to the changed entry state.

## Reproduce and limits

Run `python -m unittest discover -s harness/evidence/native_fd_outlier_branches_2026-11-05 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. `replay.py` validates the parent packet, source-only capture additions, build/run hash links, raw parent-row and NPZ equality, QV activation arithmetic, QG entry ProgB arithmetic and finite one-sided secants. The replay recomputes `sw_percent` from the captured QV and water-saturation mixing ratio before checking the fraction; a correlated rehash of both diagnostic fields is also rejected. Rehashed mutation tests additionally reject a changed fraction, entry BRS or parent output row.

These are finite endpoint evaluations of a selected f64 state-only C ABI call with forcing and controls fixed. They localize two observed branch crossings and put the small QV residual on an output-ULP scale. They do not establish a full host Jacobian, other output seeds, physical number conservation, operational f32 AD or a cost sensitivity.
