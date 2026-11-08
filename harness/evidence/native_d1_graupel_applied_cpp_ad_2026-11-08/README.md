# Native D1 graupel applied amount and number-factor AD (2026-11-08)

This packet keeps the saved `(203,149)` native column, 39 levels, 20 seconds, and initial QG17/BRS17 f64 directions used through [#561](../native_rain_slope_upstream_cpp_ad_2026-11-08/README.md). It observes the **signed applied graupel melt amount** `A=pgmlt_capped` as a live tensor at the existing `c3_pre_mf_d1` coordinator capture site. The D1 consumer already retains `gfac_melt`, `qr1/qr2`, `nr1/nr2`, the warm mask and the later freeze terms. The actual C++ store order is `qr2=qr1−A·warm_mask`, `nr2=nr1−gfac_melt·A`, followed separately by the freeze subtraction. `A` is an amount, not the `pgmlt=A/dt` rate; it is negative for melting in this selected branch.

## Source, native and graph binding

The only new coordinator change is an opt-in live-stage whitelist entry for `c3_pre_mf_d1`; removing it restores #561's executed source byte for byte. The runner remains the #557 C++ runner. Build/run receipts pin source, compiler flags (`-ffp-contract=off`, runner assertions enabled), parent input, private archive and executable, and saved C++ output by SHA-256. Public replay validates the retained result and earlier packets, not a private binary rebuild.

The baseline and two previously captured joint `h=10^-3` endpoints each supply 26 `c3_pre_mf_d1` stage fields, **78 raw f64 words and dtypes** matching the native capture. At those three cases, the applied amount matches the native melt producer's gated capped amount and `gfac_melt` matches its returned factor: **six producer-to-consumer raw joins**. The native producer also records `pgmlt=A/20` as a separate rate and the same interior amount before/after its selected cap and gate. All 208 older baseline stage words, 200 old stage JVPs, four VJP rows and 24 full final-state endpoints remain raw-bit equal to #561. New stage values at other FD endpoints are saved C++ value evaluations; they lack a second independent native-host capture.

## Applied values and selected directional derivatives

Across the baseline and 24 saved endpoints, the selected warm mask is one, `−QG_before<A<0`, `gfac_melt>0`, and later `pfrzdtr/nfrzdtr` and their selected tangents are zero. The smallest amount headroom from zero or the `−QG` bound is `1.22193×10^-5`. Replaying the **separate multiplication and subtraction** in the executed order reproduces QR2 and NR2 by raw f64 bits at all 25 cases. It also preserves #561's exact `qr2/nr2 → qr_after/nr_after` handoffs.

For one unit of the joint relative initial QG17+BRS17 direction, the live full graph reports `A=−1.2225833390863422×10^-5`, `gfac_melt=18,020,194.0636`, `dA=−6.5348297271×10^-6`, and `d(gfac_melt)=−11,292,516.4995`. At this selected branch, `dqr1=dnr1=d(warm_mask)=0`, so:

| Applied D1 tangent term | Joint direction |
| --- | ---: |
| `dQR2=−dA` | `+6.5348297271×10^-6` |
| `−gfac_melt·dA` in `dNR2` | `+117.7588999` |
| `−A·d(gfac_melt)` in `dNR2` | `−138.0604253` |
| **`dNR2` sum / actual C++ JVP** | **`−20.3015254`** |

The same source-order value and derivative relationships are checked for the QG-only and BRS-only directions. All 226 numeric stage tangents satisfy joint = sum of the singles under the declared term-magnitude/ULP roundoff bound. The two opposing NR terms are the product rule for **one applied update with shared upstream state**. They are not independent process-off effects, physical number conservation, or a decomposition of how the melt producer creates `A` and `gfac_melt`.

## Value differences and remaining limits

Four resolved signals—`A`, `gfac_melt`, QR2 and NR2—are checked against independent full-call high/low values using the represented f64 input gaps and baseline-anchored one-sided differences. Seven pairs with a captured non-crossing density-cap choice have maximum signal-relative error `4.449×10^-7`. Three additional `10^-6` pairs agree to `1.359×10^-8` but have no independent density-cap capture. Two large single-input pairs cross the previously captured density-900 cap and are excluded from local derivative acceptance. The signed amount and selected gate/cap headroom are checked at all endpoints; the detailed melt raw-rate and individual limiter production are independently captured only at the baseline and joint large-step endpoints.

Run `python -m unittest discover -s harness/evidence/native_d1_graupel_applied_cpp_ad_2026-11-08 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. Rehashed tests reject changes to the native applied amount, an uncaptured endpoint amount, its sign, a jointly linear but incorrect amount tangent, and missing VJP rows. The packet still contains only one native column, one selected level, two initial state directions plus their joint direction, and a conditional f64 branch. The `gfac_melt` and capped amount **producer formulas and active limiter-boundary derivatives** remain separate work, as do sedimentation interface attribution, operational f32, physical units/budgets, full host AD and GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
