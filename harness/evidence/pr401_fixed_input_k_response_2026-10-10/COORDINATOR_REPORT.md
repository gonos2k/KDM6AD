# PR401: fixed-input response from preserved central RTTOV K

Basis: merged main `43cc2948` (PR400). The [checklist](../CHECKLIST_pr401_fixed_input_k_response_2026-10-10.md) records this bounded continuation and the still-missing external evidence. The research helper reads existing products; production physics, AD, solver, seven-channel support, observations, calibration, coefficients, sigma and bias are unchanged.

## The BT coordinate correction is interpretive

Current source already maps same-run total radiance and all native BT-K fields into the bundled KMA BT coordinate through `make_live_run_k(..., ami_kma_bt=True)` and `transform_rttov_to_kma`. The stored central modeled BT is in the same representation as the observation. A metadata/calibration lineage difference is not proof that the current cost subtracts unlike BT coordinates. PR400 historical receipts remain intact; the wiki synthesis now makes this distinction explicit.

The exact LA product's upstream SRF remains unverified. A shared BT coordinate does not ensure a shared spectral response, and changing a polynomial or coefficient header is not a new SRF-generated radiative transfer coefficient. [SRF_RECORD_SCOPE.md](SRF_RECORD_SCOPE.md) records the narrow official-page search and its limits without claiming institutional records do not exist.

## Local response, with actual input units

This analysis is about the original central **direct-H** state at nominal05:56, j86/i48, not the accepted T/Q analysis. Local RTTOV source references describe unit/K semantics; their hashes do not prove those sources were compiled into the saved executable, which is separately pinned. Actual `adk_bt=.TRUE.` seeds thermal BT-K; `gas_units=2` means ppmv over moist air for atmospheric gases and near-surface Q2. Parsed field matrices retain channel10–16 order, signs and the exact66-layer/67-interface layout. Both Green and Red replay same-run native BT/radiance and convert K with the existing function.

For each predeclared direction, `deltaBT = K_KMA deltaInput`. The first-order cost direction is `clip(residual/sigma, -1, 1) dot (deltaBT/sigma)` for the unchanged sigma1K, bias0, Huber-delta1 contract. The official [NWP SAF mathematical overview](https://nwp-saf.eumetsat.int/site/software/rttov/documentation/rttov-mathematical-overview/) describes the Jacobian as a linear response about its reference state; these calculations are not fresh nonlinear forward evaluations.

The directions are unit comparisons: skinT+1K; common reference O3/CO2+1% each; current delivered Q2 ppmv+1%; upper-only reference T+1K and upper-only reference Q+1%, with native T/Q unchanged. All six are declared in the final-v2 response plan before its stored-K replay. They do not estimate actual atmospheric input errors, justify B/R/bias, or identify a best correction.

## Source interpolation and the common endpoint

The log-pressure interpolation matrix maps69 common reference nodes into66 active gas layers. Its high-pressure endpoint participates fully in six held native layers and partially in two additional layers. The correct pulled-back source derivative is `K_source = K_input P`: the last-source-node contribution contains both held and partial support. Treating six held values as independent errors or replacing their coherent sum by a square sum evaluates a different problem.

The current [final-v2 response report](final_v2/REPORT.md), [structured result](final_v2/K_RESPONSE.json), [signed channel responses](final_v2/K_RESPONSE_DIRECTIONS.csv) and independent Red review separate these terms, report the same seven-channel cost direction, and split its first-six versus IR133 contributions. This split is not a six-channel optimization or a comparison of objectives with unequal channel counts.

## Evidence and remaining work

The helper, final-v2 structured result, signed channel table, meaningful validation and final team reviews accompany this packet. The [initial read-only history](initial_read_only_audit/EXECUTION_HISTORY.json) records the earlier serialization failure, incomplete artifacts removed at that stage, and the unpreserved exact first-source bytes; that superseded run is not treated as the final source-bound evidence. Its successful output and private-v1 payload remain preserved. Full raw/converted K matrices, reference mappings and directions are kept in a restricted canonical private NPZ, with public provenance hashes. No native integration, preprocessing, KDM M, radiation H, coefficient utility or optimizer is executed in this phase.

External evidence remains open: product-specific SRF history; physically supported fixed-input error ranges; original IC/BC provider and matching native inputs for other dates; independent warm-liquid cases; cloud-height/optics QA and physical boundary/external water/heat terms. Existing archive request is not repeated, and no external model/reanalysis is acquired or substituted. The February2023 met_em times are not two independent native cases.

Research-management score stays **56/75 (74.7%)**. This response quantifies the existing case's conditional local sensitivity; it adds no independent event, validated error model, corrected baseline or physical cause attribution.
