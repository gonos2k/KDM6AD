# RED review — PR394 real T/Q RTTOV diagnostic

## Disposition

No actionable discrepancy found in the bounded diagnostic record after the latest setup/readiness corrections. The evidence supports a single cached-column integration diagnostic through the existing one-iteration dual minimizer and actual RTTOV. It does not establish a new valid native case, observation matchup, scientific acceptance, optimizer convergence, or forecast/operational result.

## Independent checks

- The separately reported baseline H is internally consistent: seven AMI physical channels 10–16, all seven model quality flags zero, baseline Jo (26.588575903055926), and exact zero difference from the saved baseline BT vector. The baseline H driver SHA differs from the later analysis driver SHA; the recorded changes are post-H receipt/readiness guards and the adapter config correction. The production source SHA maps are equal before and after analysis, and the immutable paired-case SHA maps are equal before and after.
- The returned one-iteration decomposition sums: (0.02141671856035715 + 0 + 26.45074405369286 = 26.472160772253215), matching the final trace. The final callback retains 7/7 support with the same recorded signature as the initial callback. Temperature and water-vapor increments are nonzero; all other state fields and all parameter controls are fixed. This is evidence of the returned algorithmic diagnostic state only.
- The actual adapter metadata records all-sky routing for the one observation despite its cached background condensate classifier being clear. The fixed observation support, normalized-dry mode, 20 s KDM window, native 39-level state and caller-supplied p-half are recorded. The preflight separately checks the native interface suffix; the adapter does not claim an independent native p-half identity check.
- The immutable pair q hash is the saved baseline value `8d5b00aa…`; the report distinguishes the stale/reused scratch hash and says that scratch was not used. The exact input and source hash snapshots are preserved in `RESULT.json`.
- The failed setup receipts are appropriately retained. Two attempts reached the background H probe and then failed in local result capture because the wrapper indexed `adj=None`; these produced no minimizer result. The parameters-rejected and existing-root attempts stopped before minimization. These do not undermine the separately recorded successful baseline H or final diagnostic. The reported successful callback-result count excludes failed/exceptional attempts, and raw RTTOV/KDM launch totals remain explicitly unknown because they are not instrumented.

## Limits

The initial data came from the small selected-column checkpoint of a failed 358-minute host run. No full forecast file was opened or hashed, and no WRF/native host run was launched. The target BT vector is inherited from that artifact; it is not represented here as a validated physical matchup. The final result's algorithmic state return is not scientific acceptance. No new physical prior, parameter inference, broad optimization behavior, or operational default is established.

The request's conditional P2 can therefore be assessed only for this narrow real-RTTOV path: routing, fixed support, T/Q state controls, frozen inactive parameters, and the returned cost decomposition behaved as recorded. It does not prove the proposed path is physically beneficial or resolve a broader production policy decision.

## Final metadata and persistence audit

The final report correctly qualifies `th` as potential-temperature and `qv` as an absolute dry-air mixing-ratio increment; the recorded norms do not imply physical-temperature changes or column water. The compact result does not contain the returned private state vector or the final slot QC/NC profile. It also lacks physical-temperature and relative-qv ranges, so these cannot be reconstructed from the norms and state hashes. The clear/cloudy classifier is for the cached background only; it says nothing about cloud generation in the returned analysis. No claim that a valid native analysis or accepted private state was published follows from the result.

The emitted analysis driver is independently hash-matched to the current `run_diagnostic.py` (`93359d47…`) and its emitted `accepted_state_published=true` field was ambiguous. The postprocessed RESULT now says `minimizer_returned_state=true` and `valid_native_analysis_published=false`. The accompanying `RESULT.executed_raw_reconstructed.json` hash matches the value recorded in `execution_receipt_provenance`, but it is expressly a deterministic reconstruction: the original write-stream bytes/hash were not captured before postprocessing. It must not be presented as the independently preserved original emission.

The baseline-H driver is recorded only by SHA (`52f40995…`); I found no archived copy of that source to compare against the analysis driver. The stated post-H changes therefore remain receipt/owner-attributed rather than independently source-diffed. This does not change the exact baseline H output or the equal production-source and immutable-pair hash snapshots, but it limits source-level provenance for the driver transition. No replay was performed to fill missing state/QC data, and none is needed to interpret this narrowly scoped diagnostic.

This is useful narrow-path integration evidence, but it does not change the overall review score (72) or resolve the conditional P2 beyond the scoped diagnostic.
