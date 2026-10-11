# Green postrun review: two value-only missing-initial H diagnostics

I independently checked the one diagnostic execution and recomputed its same-pair BT differences and Huber observation-cost contrasts from the saved result. Green made no new H, M, optimizer, native-model, backward, or residual-call execution.

The coordinator-attested [DIAGNOSTIC_EXIT.json](DIAGNOSTIC_EXIT.json) records tool completion with exit 0, two additional logical H calls, zero M/optimizer/state-backward replay, and no retry. It binds the predeclared plan, source, response result, and log hashes. This is coordinator-observed tool completion, not an independent OS/PID trace. The private diagnostic directory is mode `0700`; it contains the one-time marker and empty successful-call directories only, with no retained RTTOV direct/K files. The public packet contains no NPZ. The source plan's 79 bound inputs/sources and all 33 external asset path/size/SHA records still match. The prior CAPTURE/checkpoint pair is unchanged; the checkpoint remains mode `0600` in its mode-`0700` directory.

Both new seven-channel H vectors are finite and have model radiative quality zero. Their outputs used the same observation vector, seven-channel mask, forcing, geometry, surface, reference profile, pressure coordinates, and frozen optical density as the saved V4 run. The two stored slot endpoints used in the differences also match their saved endpoint identity, support, BT, and quality receipts. I recomputed `R_M(background)=H(M(xb))-H(xb)`, `R_M(analysis)=H(M(xa))-H(xa)`, and `I_M=R_M(analysis)-R_M(background)`; every component matches the response JSON. Costs recomputed from these saved vectors with the declared seven-channel sigma-1, bias-0, dimensionless Huber-delta-1 formula match the response values to floating-point precision:

| AMI channel | `R_M(background)` K | `R_M(analysis)` K | `I_M` K |
|---|---:|---:|---:|
| 10 / wv073 | −1.2453e−9 | 2.3417e−6 | 2.3429e−6 |
| 11 / ir087 | −0.0004114440 | 0.8321036323 | 0.8325150763 |
| 12 / ir096 | −0.0002799099 | 0.5176393520 | 0.5179192619 |
| 13 / ir105 | −0.0003893113 | 0.6890203635 | 0.6894096748 |
| 14 / ir112 | −0.0003100742 | 0.5604754499 | 0.5607855241 |
| 15 / ir123 | −0.0001822447 | 0.3915441455 | 0.3917263902 |
| 16 / ir133 | −5.9520e−5 | 0.1390130782 | 0.1390725982 |

The cost contrasts are `G_M=2.1404157250`, `G_0=0.2054073862`, and `G_M−G_0=1.9350083389`, where each gain is the background-minus-analysis observation cost for the fixed endpoint pair. These values describe this selected column under its one saved forcing and fixed H context. They do not identify a named process, quantify a process rate, close a water/heat budget, define a no-M optimum, or compare a later saved host state at the same valid time.

Checkpoint State summaries independently match the reported values. Background-initial and returned-analysis-initial QC each have one positive level with maximum `3.4602016967e−5 kg/kg dry`; the saved background-slot QC maximum is `3.4634193137e−5`, and final-slot QC is zero over 39 levels. Final-slot NC is zero. The reported fixed-host-dry-mass water measure is `38.3765209050 kg/m²` for the background pair and `38.2615440837 kg/m²` for the analysis pair; the analysis-initial minus background-initial measure is `−0.1149768213 kg/m²`. Those are checkpoint state summaries using a fixed mass field, not closed external-flux budgets. The NC value is labeled only in its recorded model coordinate; native QN dry-versus-moist mass basis was not independently revalidated.

The actual V4 run remains `RETURNED_CASE_DIAGNOSTIC`, not strict convergence: two optimizer iterations, four function evaluations, final gradient L∞ `0.3041588433` versus tolerance `1e−10`, and termination `UNKNOWN`. All seven channels retained support and the final audit was crosschecked. No new native integration or observation date was added, no old-center result was rerun, and science acceptance and pixel UTC remain unverified. RTTOV internal direct/K call counts remain uninstrumented even though the diagnostic calls were value-only at the `sharded_allsky` interface.

**Disposition:** the two-call response, costs, checkpoint summaries, and provenance are internally consistent. This is a selected-column joint M-endpoint observation-space response; it is not a named-process attribution, forecast result, cloud truth, or science-acceptance claim.
