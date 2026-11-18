# Expanded native NC16 directional differences (2026-11-06)

This packet extends the [NC16 one-hot C ABI VJP](../native_nc16_vjp_branch_window_2026-11-06/README.md) with **prespecified value-only f64 C ABI endpoints** for six input directions. It uses the same captured native `(203,149)` column, 39 levels, 20-second call, fixed forcing, xland and experimental `norm_actual` variant. The #544 isolated DSO is reused; no new host run, C++ AD run, physics change or operational install is involved. Each of the **37 calls** retains a 13,611-row full-column capture and a 12×39 output. The baseline capture is row-for-row identical to #544's baseline; its output is raw-f64-equal to #545's saved output.

## Prespecified directions and steps

The directions were fixed in the [producer source](producer/run_fd.py.txt) before endpoint execution. `relative` means `x(ε)=x₀(1+ε)`; `absolute` TH16 means `TH(ε)=TH₀+ε K`. All perturbed components have positive endpoints. BRS is the graupel volume state coordinate; its physical unit contract is not established here.

| Input direction | Nominal `VJP·direction` for NC16 | Three half-steps | Recorded cap crossing |
| --- | ---: | --- | --- |
| NC16 relative | `+154141743.06856754` | `10⁻³,10⁻⁴,10⁻⁵` | none recorded |
| QC16 relative | `+38546328.10015923` | `10⁻³,10⁻⁴,10⁻⁵` | none recorded |
| TH16 absolute | `+6295931.286601372 K⁻¹` | `10⁻²,10⁻³,10⁻⁴ K` | positive `10⁻²`: activation fraction cap |
| QG17 relative | `+1786497.345303899` | `10⁻³,10⁻⁴,10⁻⁵` | positive `10⁻³`: entry ProgB density 900 |
| BRS17 relative | `−604032.7570000846` | `10⁻³,10⁻⁴,10⁻⁵` | negative `10⁻³`: entry ProgB density 900 |
| QG17+BRS17 together, same relative change | `+1182464.588303814` | `10⁻³,10⁻⁴,10⁻⁵` | none recorded |

The replay recomputes every endpoint input from the pinned baseline, compares it with the actual capture in raw bits, and checks that forcing, xland, call controls and the recorded boolean masks/substep schedule are unchanged. It recomputes the native-16 activation fraction from captured QV/qs1 and the native-17 entry ProgB BRS from captured QG/BRS. The top-first `fd_main` capture row for native 17 is `k_zero=16`; runtime input uses `k_zero=22`.

## Central and one-sided comparisons

For each ± pair the primary prediction is `gᵀ(x₊−x₋)`, using **each actually represented input difference**. This matters for the coupled QG/BRS direction: its two operands need not have exactly the same represented relative gap. The replay compares the prediction with `NC16(x₊)−NC16(x₋)`, computes the input midpoint exactly from the stored f64 words, records each one-sided output and VJP-predicted gap, and expresses the residual both as `|observed−predicted|/max(1,|predicted|)` and in NC16 output f64 ULP. Some input midpoint offsets are exactly ±0.5 input ULP even though a rounded f64 midpoint equals the baseline; their VJP-weighted output effect is recorded. Every tested output difference exceeds 100,000 output ULP.

**Fifteen** step pairs retain all recorded cap selections and meet the existing parent-packet normalized `5×10⁻⁶` bound. The largest accepted normalized residual is QC16 at `h=10⁻³`, about `2.01×10⁻⁶`, consistent with a larger finite step; QC16 errors fall by about two powers of ten as `h` is reduced tenfold. **Three** pairs cross a captured cap and remain separate finite-change diagnostics: TH16 `h=0.01 K` crosses the activation-fraction cap on the positive side; QG17 `h=10⁻³` crosses the entry density-900 cap on the positive side; BRS17 `h=10⁻³` crosses it on the negative side. Their normalized central residuals are about `126`, `0.149` and `0.441`, respectively. Recorded boolean masks and local substep schedules do not change in these pairs, showing why those fingerprints alone are insufficient. Unrecorded internal branches remain unverified.

At `h=10⁻³`, QG17 alone and BRS17 alone cross the density cap on opposite sides. Moving both together keeps their entry `QG/BRS` within two f64 ULP of the baseline ratio `899.8929353897046` and below 900. Its observed NC16 central difference is `2364.92908`, versus VJP-predicted `2364.92918` (normalized gap `3.98×10⁻⁸`). This comparison exposes the two separate contributions and their combined response; it does not establish a physically admissible graupel mass/volume perturbation without the unit contract.

## Provenance and limits

`manifest.json` pins the 37 compressed captures, NPZ inputs/outputs, process logs, producer source and run receipt. The receipt binds every call to the #544 DSO/archive/source hash, the #545 baseline NPZ, fixed thread/variant settings and the complete step plan. Public replay validates the parent #545/#544 packets first, checks the new baseline capture and output, and then verifies every saved case and arithmetic relation. Rehashed mutation tests reject inconsistent output arrays and altered **selected native-17 entry ProgB BRS or native-16 activation `sw_percent`** values. Other captured intermediate rows are hash-, dtype- and call-ID-checked, but not all are independently reproduced arithmetically; an override that changes only an unused intermediate row can pass these selected semantic checks, as a regression test documents. The default CLI still pins every original capture byte through the manifest.

The evidence is a **selected-column conditional f64 state sensitivity** for one NC16 output. The 15 accepted comparisons maintain the *recorded* cap decisions and masks; they do not prove all internal branches fixed. No new reverse-mode derivative was calculated here—the VJP is the #545 value. Operational f32 AD, the full host Jacobian, QNICE physical units, process budgets and GK2A–RTTOV cost sensitivity remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_nc16_fd_expanded_2026-11-06 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
