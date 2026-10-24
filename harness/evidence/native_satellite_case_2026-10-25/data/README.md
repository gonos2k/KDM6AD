# Native KO7 full-domain case evidence pack

This pack is generated only after RUN_v4/FINAL.json and all three independent audits pass. It contains path-redacted receipts, exact binary64 arrays, and one full-domain BT/quality/profile-valid array per declared trial; no values are rounded or quantized.

The packer reads saved receipts/arrays and renders diagnostics from those saved arrays; it makes no KDM, RTTOV, host, forecast, or assimilation calls.

Raw-source validity is calculated from the saved per-block DQF/QC values and is plotted separately from native profile admission and frozen RTTOV model-quality support. The primary row-reason map uses a fixed category precedence; the exact per-row reason strings and multi-label counts are also retained.

Each channel comparison map uses one shared brightness-temperature scale for observations and both model states, and one shared residual scale. All six panels use the frozen baseline support; white indicates profile/RTTOV exclusion, not missing KO data. Exact-zero final-minus-baseline panels have no colorbar. Original source summary plots are preserved byte-for-byte under history/original_summary_maps.

Native gradient and increment figures distinguish raw dJ/d-state from the scaled active-control gradient. The gradients/T-Q tangent belong to the baseline derivative pass; trial states are value-only re-evaluations, with no trial gradient. Delta θm/QV figures are accepted input-control increments relative to baseline x_b; all are zero because no candidate was accepted, and they are distinct from physical pre/post-microphysics changes and tendencies. Their vertical L2/profile summaries are state-vector diagnostics over 39 levels, not mass budgets.

The experiment is an offline full-domain T/Q control and observation-cost map using the pinned provided model and KO inputs. It is not a host timestep, forecast, or cycling result. The raw host NC/NI unit basis is uncertified; optical NC/NI uses the same live post-finish dry density as a research volume coordinate. Pixel UTC and original-provider navigation remain uncertified. The upper reference has 26 fixed complete layers plus a live partial layer at model top; trace gases remain fixed from the pinned RTTOV template. Water, energy, and number closure are not claimed.

The original chunk receipts, raw K/profile arrays, checkpoint and RTTOV cases remain in the private evidence tree. Their identifying SHA-256 values are included where relevant; their local absolute paths are intentionally omitted.
