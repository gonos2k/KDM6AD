# Conditional C++ pre2→C2c→NC process AD (2026-11-07)

This packet starts at the **post-D2–D4 pre2 entry** of the saved `(203,149, native level 16)` f64 call. Its two leaf inputs are the captured pre2 QG and BRS. The actual C++/libtorch archive from [the postfreeze pre2 packet](../native_c2c_pre2_upstream_2026-11-07/README.md) executes `progb_param_torch → slope_kdm6_torch → cloud_water_riming_torch`, followed by the captured-source-order NC budget with the **other rates and inline amounts fixed**. BRS enters ProgB and affects C2c through derived parameters; it is not a `CloudWaterRimingInputs` argument. This is a selected local process graph, not a new host, RTTOV, full C ABI call or full model Jacobian.

## Baseline and graph provenance

The 12 reported outputs are ProgB density/returned BRS/`avtg`/`bvtg`/`g3pbg`/`pidn0g`, graupel `rslope3_g`/`rslopeb_g`, C2c `nsacw`/`ngacw`/`naacw`, and **pre-activation conditional NC after the budget**. All 12 baseline values are raw f64-bit equal to the separate #553, #551 and #549 captures. The NC budget uses the captured baseline `nraut`, `nccol`, `nracw`, `niacw`, cold mask, freeze/melt inline amounts, NC before and 20-second interval. It applies `naacw` twice in the executed order, with no shared cloud-number limiter rerun. The selected parent factor is one and every tested endpoint remains in the no-rescale domain.

Other-species slope and ice-C2c operands that do not feed these reported graupel/number outputs are fixed to finite placeholders in the runner. The selected graupel/C2c outputs are checked against the archived native-state baseline by raw bits; the placeholder species' outputs are neither reported nor validated as native values. The C++ runner does not use scalar extraction, detach or `no_grad` to feed its derivative graph. JVP uses reverse-over-reverse autograd, while VJP computes both input sensitivities for each of the 12 one-hot output seeds. Build/run receipts pin the source, flags (`-ffp-contract=off`, no `NDEBUG`), selected native capture, linked static archive, executable and archived output. The archive/executable bytes remain private; public CI checks their hashes and the retained C++ result, not a public rebuild.

## Local sensitivities and independent value differences

The directions are relative perturbations **at the pre2 QG/BRS input**, (v_Q=(QG_0,0)), (v_B=(0,BRS_0)) and (v_{QB}=(QG_0,BRS_0)). They are different from the earlier **native-17 initial-state** joint perturbation in #546–#553; its final NC difference is not a derivative reference for this conditional map. The principal C++ JVPs (per unit relative direction) are:

| Output | QG only | BRS only | QG+BRS |
| --- | ---: | ---: | ---: |
| postfreeze density | `+899.9209324` | `−899.9209324` | rounding scale |
| `ngacw` | `+821.9522902` | `+116.0111072` | `+937.9633974` |
| `naacw` | `−34795.6857747` | `+8.3713669` | `−34787.3144078` |
| conditional NC budget | `+1391827.4310` | `−334.8547` | `+1391492.5763` |

The full 12-output JVPs and 12 two-input VJP rows are in `raw/cpp_result.json`. Each JVP agrees with its VJP contraction within a fixed, term-magnitude/output-ULP rounding bound. Nearly cancelled joint density, `avtg`, `bvtg`, `g3pbg` and `pidn0g` tangents are recorded as rounding-scale responses, not resolved physical signals. Same-graph transpose consistency alone is not independent derivative evidence.

The C++ runner also evaluates independent **value-only** high/low endpoints. The replay uses the actual represented two-input gap and checks the observed output gap against VJP·gap. QG and BRS single directions use half-steps `10^-5`, `10^-6`, `10^-7` for local comparison; their `10^-4` pairs are kept as separate crossings because the QG-positive or BRS-negative endpoint selects the density upper cap 900. Joint directions also retain `10^-3` as a finite change with the recorded density interval unchanged. At `h=10^-5`, every output whose gap exceeds 32 output ULP is tested with signal-relative error at most `10^-6`; outputs below that resolution are listed separately, never accepted as a measured zero derivative. For stable steps, the maximum `|observed−predicted|/max(1,|predicted|)` is `5.53×10^-7`; the largest resolved signal-relative residual at `h=10^-5` is about `7.54×10^-7` (BRS→conditional NC). The large-step cap crossings are reported, not used as fixed-branch AD acceptance.

The replay checks recorded density-clamp/table branch and the selected C2c species/number/qsum gates, interior Wilt ratios, inactive individual NC/dt caps, positive conditional NC and no-rescale margin at every tested endpoint. It does not enumerate every branch elsewhere in the full runtime. The fixed non-graupel operands, upstream production of QG/BRS, later NC activation and NCCN floor, inactive ProgB retention, operational f32, process physical units/budgets and GK2A–RTTOV cost sensitivity remain outside this local experiment. `scientific_status` and `physical_unit_status` stay `INCONCLUSIVE`.

## Public verification

`manifest.json` pins the runner source, receipts and archived C++ output. Public replay recursively verifies the #553 native-state evidence, exact 12-output baseline words, fixed seeds, finite JVP/VJP arrays, represented endpoint inputs, selected branch decisions, transpose contraction and independent directional gaps. Rehashed tests reject a baseline word change, a coordinated bvtg JVP/VJP zeroing that would otherwise pass a max-one FD check, a false cap endpoint and a wrong input seed. A coordinated rewrite of every dependent input and output could remain internally consistent under an override; default CLI hashes pin the original execution record.

Run `python -m unittest discover -s harness/evidence/native_pre2_c2c_cpp_ad_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
