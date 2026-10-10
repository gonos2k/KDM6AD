# PR400 follow-up: stored fixed-input K response

Basis: merged main `43cc2948`. This continues the [PR400 checklist](CHECKLIST_pr400_input_compatibility_2026-10-10.md) without reopening the completed native, optimization, vertical or neighbor-H diagnostics.

## Scope and completed source checks

- [x] Read `ami_bt_coordinate.py` and the executed `make_live_run_k(..., ami_kma_bt=True)` producer-to-consumer path. Model BT and every K row are converted with the same bundled KMA coordinate used by observations. The IR133 calibration/SRF lineage difference is not, by itself, a code error subtracting unlike BT coordinates.
- [x] Fix the scope to the preserved central native direct-H case at 05:56, j86/i48, seven channels10–16. This is not a new evaluation of the accepted T/Q analysis.
- [x] Retain the existing observation, quality/support, 1 K sigma, zero bias, prior, coefficient and operational defaults. No coefficient header, FILTER_FUNCTIONS or calibration replacement.

## Response calculation and validation

- [x] Read full saved K matrices and same-run radiance/native BT, validate row identities, lengths, actual options/units and pinned assets, and reproduce the old central KMA BT without invoking radiation.
- [x] Convert every K field using the existing production function; preserve raw and converted matrices locally with their signs, channel/level order and hashes.
- [x] Predeclare unit directions: skinT +1 K; reference O3/CO2 +1% each; Q2 +1% in the actual delivered RTTOV unit; upper-reference T +1 K and upper-reference Q +1%, both with native layers unchanged. The six directions are fixed in the final-v2 direction plan before that stored-K replay.
- [x] Form the log-pressure interpolation matrix, including endpoint holding, verify reconstructed gases, and pull K back to the common source profile. Six held layers respond together to one reference endpoint.
- [x] Report channel deltaBT and first-order Huber deltaJo in the common KMA coordinate, plus separate six-channel and held-out IR133 contributions. These are unit responses, not measured input errors, exact nonlinear forward changes or a six-channel optimization.
- [x] Complete meaningful matrix-alignment/endpoint/unit checks: eight targeted tests pass; preserve initial serialization/source-provenance limitations separately. No new M/H/native run.
- [x] Complete final Green consistency and Red counterexample reviews against final-v2 source-bound results; actionable source/unit/provenance findings are resolved.

## Still open after this bounded calculation

- [ ] Actual upstream SRF/calibration history for the specific July19 05:56 LA020GE IR133 product. A common BT representation does not establish common spectral response. A justified new coefficient/product pairing needs a separately identified baseline.
- [ ] Physically supported case-specific gas/surface/reference-atmosphere error ranges. The unit directions above do not estimate these ranges or calibrate B/R/bias.
- [ ] Original meteorological provider and matching native IC/BC for other dates. Existing archive-path request remains pending; no repeated same-directory inventory or substituted external model/reanalysis.
- [ ] Two independently selected warm-liquid events and their same-setting native analyses, once original inputs and observations are available. The two February2023 met_em times are not two independent cases.
- [ ] Cloud height/optical QA and full water/heat boundary/external terms remain as previously scoped.

Research-management score remains **56/75 (74.7%)**. Completed investigations and unavailable external evidence remain distinct.
