# PR401 final Green review

## Disposition

The final-v2 helper, result, report, direction plan, checklist, coordinator report and wiki synthesis agree on the bounded scope and its limits. No blocking scientific or data-integrity issue remains in the preserved center K replay.

## Source, run and coordinate consistency

The final-v2 `K_RESPONSE.json` binds helper SHA-256 `03b42a5f…`, direction-plan SHA-256 `a7cad874…`, the PR399 center result and K-output paths, the final PR400 fixed-input receipt, same-run radiance/K files, and the production source-contract receipt. Its source list includes the production ASCII/K parser, KMA transform, case writer, Q conversion/channel map, local RTTOV gas-unit conversion and K code, `rttov_test.pl`, and `example_k.F90`. The canonical private source copy matches the audited helper hash; the NPZ is mode `0600` inside a mode `0700` directory.

The center run remains `(j=86,i=48)` at `2025-07-19_05:56:00`, with channel order 10–16. Saved `adk_bt`, `use_q2m`, active and reference `gas_units=2`, same-run `RADIANCE%TOTAL`/`RADIANCE%BT`/quality and every parsed K field are checked. Applying `transform_rttov_to_kma` to the saved same-run values reproduces the prior center BT exactly (maximum difference `0 K`); all seven quality flags are zero. The recomputed normalized Huber objective is dimensionless `26.59768478212186`, matching the inherited saved `Jo_huber_K_units` numeric field. Residual and sigma units remain K, with `sigma=1 K`.

The response signs and channel splits match the independent Red replay. The six unit directions produce dimensionless linear `deltaJo` totals of `+2.303124984` (skin T +1 K), `−0.141806993` (reference O3 +1%), `−0.044499622` (reference CO2 +1%), `−0.002999643` (Q2M +1%), `+0.234692915` (upper T +1 K) and `−0.0000813602` (upper Q +1%). The six-channel subtotal and IR133 term are parts of the same seven-channel objective, not an ablation. All six directions, including optional upper-reference Q, are in the frozen plan before final-v2 replay.

The 66×69 log-pressure interpolation matrix reproduces saved active O3/CO2. It records six fully endpoint-held levels and two partial weights `0.2025991255` and `0.8669217862`. The result separates held and partial K contributions before confirming their sum against the final source-node contraction. Both groups respond to one shared reference endpoint, so the response is correlated across levels.

## Boundaries and remaining evidence

This is one preserved direct observation-operator K at the reused center. It is not a fresh K or H call, KDM6AD Model_H, a model-composed derivative, a final accepted analysis, or a nonlinear perturbed forward cost. The declared directions are exploratory scales, not input-error estimates, corrections or physically approved ranges. Q2M's actual saved perturbation is +298.76367 ppmv over moist air; the two gas fixtures and all K/input matrices are retained with hashes.

The initial successful v1 audit remains in `initial_read_only_audit/` with its JSON, CSVs, report and private v1 NPZ. Its source hash is recorded there, but those earlier source bytes were not preserved; the execution-history note states this. Use final-v2 for current claims. The earlier JSON-serialization failure is recorded as a helper-output failure with no model or radiation calls.

The wiki page accurately distinguishes same-coordinate BT comparison from unresolved upstream IR133 SRF compatibility and preserves the unit-response limits. The current graph query remains incomplete for the final report and checklist; the accompanying semantic fragment records their source-grounded links and labels the direct-met_em incompatibility as inferred. External SRF identity, physical support for input-error ranges, original provider/preprocessing, independent native events and full flux closure remain open. The score remains 56/75 as a research-management score.

## Validation performed

The targeted PR401 contract tests pass (8 tests), and Ruff passes on the helper and test file. Graphify refreshed the code graph after helper edits and the resulting query exposes the helper's calls to the production parsers and transform. No H/M/model/preprocessing/acquisition or optimizer call occurred during final-v2 replay or this review.
