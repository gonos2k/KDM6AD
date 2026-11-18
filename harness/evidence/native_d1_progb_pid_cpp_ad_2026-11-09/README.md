# Full-call native D1-entry ProgB number-intercept tangents (2026-11-09)

This packet continues the selected `(203,149)` native column, 39 levels, 20-second f64 call and initial QG17/BRS17 directions from [#564](../native_d1_entry_slope_cpp_ad_2026-11-09/README.md). At the entry `pre=preamble(...)` before D1, a test-only hook retains the actual merged ProgB `rhox`, `cmg`, `pidn0g` tensors and the scalar parameters `n0g`, `g1pdgmg`, `g1pmg`, with the active and midpoint choices. This is the entry preamble consumed by the D1 slope, not the later `pre1` or `pre2` rebuild.

## Active source-order value and tangent

The executed capture-only ProgB source computes `cmg_raw=(PI*rhox)/6`, selects `cmg` by the produced gate, then computes `pidn0g=((cmg*n0g)*g1pdgmg)/g1pmg`. The public replay checks the selected active branch, stored f64 operands, exact source-order values, and the chain tangents from `rhox` through `cmg` to `pidn0g`. It keeps each actual parameter value and its zero tangent separate; replacing the product with a rounded combined constant would change the floating-point contract. The captured `pidn0g` and `rhox` are bound by raw bits and JVP to the earlier entry-slope stage, which already connects `pidn0g` to `rslope_g` and `gfac_melt`.

These are input-chain terms of one common graph. They do not measure the effect of independently disabling a physical process, establish particle-number conservation, or explain the separate melt applied amount `A`.

At baseline, the actual factors are `n0g=4,000,000`, `g1pdgmg=6.000000000000001`, and `g1pmg=1`. Replacing the recorded gamma factor by the mathematical integer `6` changes the baseline `pidn0g` by one f64 ULP. The recorded values are `rhox=899.9209324078313`, `cmg=471.19749834401995`, and `pidn0g=11308739960.256481`. The joint initial QG17+BRS17 relative direction gives `d(rhox)=-0.0233937476`, `d(cmg)=-0.0122489376`, and `d(pidn0g)=-293974.5027`; the large opposing single-direction `pidn0g` tangents nearly cancel in the joint direction.

## Provenance, differences, and limits

The isolated C++ build uses the #553 capture-only ProgB source snapshot; source, parameters, flags, input, private archive/executable and result are SHA-pinned. The public replay verifies the archived execution and parent evidence; public CI does not rebuild the private binary. The previously captured baseline and joint `h=10^-3` endpoints anchor entry QG/BRS and density words, while the newly retained `cmg` and `pidn0g` have no separate native-host producer tap. Existing #564 stage values/JVPs/VJPs and 24 full final-state endpoints remain raw-equal.

Represented f64 input gaps and output ULPs are used for independent high/low values. Earlier **native-17** density-cap crossing pairs are excluded from full-call same-branch derivative acceptance; the **native-16 entry** density boundary is diagnosed separately. Additional small-step pairs have no independent native cap capture. Inactive ProgB retention, active limiter/tie derivatives, the upstream D1 melt amount producer, operational f32, physical units/budgets, full host AD and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` are `INCONCLUSIVE`.

The ten accepted high/low pairs add **ten independent `cmg` value-difference checks**. Their smallest observed change is over 430,000 `cmg` output ULPs. Nine satisfy `10^-6` signal-relative error directly; the joint `h=10^-6` pair has `2.868e-6` relative residual but only `1.24` output ULP absolute residual, accepted by a declared four-ULP floor. Two baseline-anchored one-sided `cmg` comparisons likewise require the floor, with at most `2.27` output ULP residual. The earlier `rhox` and `pidn0g` finite differences remain checked by the parent packet; their duplicated live values and JVPs are linked here by raw bits rather than counted as new independent signals.

Run `python -m unittest discover -s harness/evidence/native_d1_progb_pid_cpp_ad_2026-11-09 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
