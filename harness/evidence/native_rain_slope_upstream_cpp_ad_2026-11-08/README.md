# Native D1→pre2 rain-slope upstream C++ AD (2026-11-08)

This packet follows the saved `(203,149)` native column's 39-level, 20-second f64 `kdm6_fn` graph from initial QG17/BRS17 through the selected native-level-16 rain number and mass state, the postfreeze `pre2` rain-slope producer, and the B2 `nracw` consumer. It extends [#559's B1/B2 input packet](../native_warm_rate_inputs_cpp_ad_2026-11-08/README.md) without changing operational `libtorch`, the Python oracle or the packed C ABI.

## Executed order and provenance

The new test-only live hook retains QR/NR at D1 before melt, after snow melt and after graupel melt; the first rain-number snap; D2–D4 before/after QR/NR; `pre2` rain-slope input QR/NR/DEND, constants and output; and the second rain-number snap. The actual `rebuild_aux` creates `rslope3_r` and `avedia_r` **before** the second NR snap, whereas warm B1/B2 consume **after-snap** NR. The replay keeps these distinct tensor nodes. The selected baseline and all 24 value endpoints happen to carry NR unchanged through both snaps; no other branch inherits that identity by assumption.

Removing the new stage-hook additions restores #559's executed coordinator byte for byte. The runner source is unchanged from #557, and the frozen slope/cloud-DSD sources match public production; the frozen runtime matches its earlier executed snapshot. Build/run receipts pin the source, flags (`-ffp-contract=off`, runner assertions enabled), parent input, private archive/executable and output by SHA-256. Hook off/on final state, all 157 old stage values, 149 old stage JVPs, four VJP rows and all 24 parent final-state endpoints remain raw-bit equal to #559. The 99 baseline/joint-endpoint D1 and snap words already present in #553's native capture match the new graph stage values and dtypes exactly. New D2–D4 QR/NR and `pre2` rain-slope internals do **not** have a separate native-host capture; their source-order values, handoffs and directional differences are verified within this isolated C++ call.

## Where the selected rain response first appears

For the joint initial QG17+BRS17 relative direction, the saved native-16 D1 QR/NR before melting and after snow melting have zero JVP. After the graupel-melt update, `dQR=+6.5348297271×10^-6` and `dNR=−20.3015254317`. At all 25 selected value cases, the resulting QR/NR words pass through the first snap, D2–D4, `pre2` rain-slope inputs, the second snap and B2's corresponding consumers without a value change. Their selected JVP words also agree across those boundaries in all three initial directions. This locates the first *captured* nonzero QR/NR response at the D1 graupel step; it is not a decomposition of the graupel applied amount or sedimentation interface fluxes across the column.

## Rain slope and the B2 cancellation

The selected rain producer has positive QR/NR/DEND, an interior lambda (`961<λ<35000`), a nonactive `rslope_r<10^-3` cap and no inactive rain mask at the baseline and 24 endpoints. Its executed path uses `α=float32(1/DMR)` widened to f64, here `α=0.3333333432674408`, in `λ=exp(log(pidnr·NR/(QR·DEND))·α)`, followed by `rslope_r=1/λ`, `rslope2_r=rslope_r²`, `rslope3_r=rslope2_r·rslope_r`. The `avedia_r` multiplier uses the source's `0.3333333` literal. Replacing α by an exact mathematical third would change the derivative contract.

Independent Python value reproduction across 25 cases differs by at most 1/2/4/2 ULP for `rslope_r`/`rslope2_r`/`rslope3_r`/`avedia_r` in the producer environment. Public cross-environment bounds are 16/16/32/16 ULP and apply only to this independent arithmetic; actual `pre2` production → B2 consumption remains raw-bit exact. The full C++ JVP agrees with the input-chain derivative

`d(rslope3_r) = −3α·rslope3_r·(dNR_pre/NR_pre − dQR/QR − dDEND/DEND)`

at each of the three initial directions. DEND is fixed in these state-only directions. The joint-direction nested B2 terms are:

| Contribution to `d(nracw)` | Value |
| --- | ---: |
| Direct after-snap NR argument | `−7608.1973175` |
| Slope response to before-snap NR | `+7608.1504398` |
| Slope response to QR | `+5134.4749860` |
| Sum / actual B2 JVP | `+5134.4281083` |

The two NR paths nearly cancel; their residual is about `−0.04688`, while the QR path supplies most of this selected B2 response. This calculation follows distinct direct arguments of one B2 call and the upstream rain-slope chain. NR and QR have shared ancestors, so the table is neither a process-off experiment nor a universal physical cause allocation.

## Finite differences and limits

Six resolved D1/pre2 QR, NR, rain-slope and mean-diameter signals are tested against independent full-call high/low values using actual represented f64 input gaps and baseline-anchored one-sided checks. Seven pairs with a previously captured non-crossing density-cap choice have maximum signal-relative error `2.148×10^-7`; three added `10^-6` pairs agree to `3.841×10^-8` but lack an independent density-cap capture. The two large single-input pairs that cross the recorded density-900 cap are excluded from local derivative acceptance. Selected rain masks, lambda limits and slope caps are checked at every endpoint; not every upstream branch is captured.

Run `python -m unittest discover -s harness/evidence/native_rain_slope_upstream_cpp_ad_2026-11-08 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. The packet recursively verifies #559, checks source restoration and the 99 native stage words, exact value/JVP handoffs, positive branch margins, bounded independent value arithmetic, input-chain tangents and selected directional differences. Rehashed tests reject false native D1 words, D2–D4 handoff changes, inactive rain constants, slope values/tangents and missing VJP rows.

The evidence remains one native column, one selected level, two initial coordinates and this conditional f64 branch. The D1 graupel melt's applied-rate derivative, other snap/cap branches, sedimentation interface attribution, operational f32, physical units/budgets, full host AD and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
