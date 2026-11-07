# Applied NC state-update terms before activation (2026-11-07)

This packet narrows the #548 [NC–NCCN ledger](../native_nc_nccn_applied_2026-11-07/README.md) for the captured `(203,149)` native column. In the joint QG17+BRS17 `±10^-3` endpoints, NC16 differs by `2364.9290825128555` at the first **captured** `fd_state_update.nc_after` store, while `nc_before` is raw-equal. The difference is already present before the subsequent activation. Three f64 C ABI **value** calls—baseline and those two endpoints—were re-executed twice each with capture off/on. No private host/RTTOV or new AD run is included.

## Executed source, inputs and noninterference

The isolated source is the #548 coordinator with **20 value-only capture calls** added: 16 at the NC budget consumer in `state_update` and four immediately after `scale_rates_for_conservation` returns. Removing those calls recovers the #548 coordinator byte for byte; runtime and CMake source are also byte-identical. The private DSO and archive are connected to this source, compile flags, input NPZ, execution logs and output through build/run SHA-256 receipts. The DSO, object and archive bytes remain private, so public CI replays their recorded outputs rather than rebuilding the private execution.

Each of the three cases has paired capture-off/on `state`, `forcing`, `xland` and `output` NPZ arrays that are raw-equal to one another and to the corresponding #548 case. The capture-on CSV has **14,781 rows**. Dropping the 20 new fields × 39 levels leaves the #548 **14,001 rows** in the same order, datatype and raw words. The replay runs the parent #548 verifier before checking the new rows.

## Applied NC budget at the selected layer

The executed source forms the NC rate sum in this order:

```text
dnc_rate_sum = -nraut - nccol - nracw - niacw*cold_mask - naacw - naacw
dnc_amount = -ninuc - nfrzdtc + pimlt_ni
NC_raw = (NC_before + dnc_amount) + dnc_rate_sum*dtcld
NC_after = max(NC_raw, 0)
```

The two `naacw` subtractions are the two occurrences in the executed budget expression; they are **not two independently measured processes**. All terms are the **post-limiter values supplied to `state_update`**. `nraut` is raw-linked to the earlier `fd_d5.nraut_applied` capture; `nccol`, `nracw`, `niacw` and `naacw` are raw-linked to separate captures immediately after the limiter returns. This verifies producer-to-consumer forwarding, not the upstream rate formulas or every preceding limiter choice. For all **3×39=117** level-calls, the ordered sum, inline amount, pre-clamp and clamped NC store reproduce the captured f64 words exactly. The #548 `fd_state_update` before/after rows are checked independently. None of the 117 pre-clamp NC values is negative; selected native 16 is strictly positive on both endpoints.

At native 16 (`k_zero=23` in top-first capture), both endpoints have `NC_before=184716859.43634674`, `cold_mask=0`, `dnc_amount=0` and `dtcld=20`. The table gives **plus minus minus endpoint differences in the final NC numeric coordinate**, using exact-rational differences of the stored f64 terms before display rounding.

| Applied rate term | Contribution to NC16 endpoint difference |
| --- | ---: |
| `−nraut` | `+0.0002676741216622869` |
| `−nccol` | `0` |
| `−nracw` | `−205.37712793331593` |
| `−niacw*cold_mask` | `0` |
| `−naacw−naacw` | `+2570.3059427789412` |
| Stored f64 rounding residual after those terms | `−6.891443637968564e−9` |
| **Observed NC16 difference** | **`+2364.9290825128555`** |

The selected difference is first visible at the captured `fd_state_update.nc_after` row and is unchanged at reclassification, the activation input and final NC output. The table is an **algebraic decomposition of the two observed endpoint stores**. It does not isolate a counterfactual causal effect of each physical producer. In particular, shared rates may have been changed by earlier sequential limiters, and QG17+BRS17 is a coupled numerical input direction. Capturing a rate at both the limiter return and the state-update input checks the forwarding, but an override that changes both copies consistently can remain arithmetically self-consistent; default CLI hashes pin the original evidence bytes.

## Verification boundary

The default replay pins all new raw/producer/executed-source assets; test overrides rehash a selected CSV or receipt and retain parent, output, ordered-sum and producer-to-consumer checks. Regression cases reject a compensating `nraut`/`nccol` mutation, a one-ULP `naacw` consumer mutation that leaves the rounded sum unchanged, a changed NC store, datatype and run-step claim. The independent source and parent receipt checks do not establish that all raw rates follow their upstream producer equations.

No NC budget JVP/VJP was added. NR generation/sink terms, upstream rate production and limiter factors, operational f32 AD, particle-number units/budgets and GK2A–RTTOV cost sensitivity remain outside this packet. `scientific_status` and `physical_unit_status` stay `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_nc_budget_terms_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
