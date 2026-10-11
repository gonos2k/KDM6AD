# PR412 Red optional H diagnostic post-run review

The separate two-call diagnostic returned exit 0 as `RETURNED_TWO_VALUE_ONLY_H_DIAGNOSTICS`. I did not rerun H, M, KDM6, or the optimizer. I independently verified the diagnostic plan/source, response, log and coordinator-observed exit hashes, all 33 declared H execution assets, all plan-bound source/input hashes, and the checkpoint/capture endpoint links. The output records exactly two additional logical H calls, no M/optimizer/state-backward replay, and no retry. Combined with the six H callbacks in the separate V4 analysis, the evidence contains eight logical H callbacks total; this is not an internal RTTOV direct/K launch count. The wrapper may generate K internally, and no PID inventory is claimed.

Both new H values use the same seven BT targets, unit errors, zero bias, unit Huber delta, all-one support, forcing and H configuration as the saved analysis. I recalculated the endpoint vectors and Huber contrasts from the recorded BT values and verified the first and final stored slot BT, quality, mask, and State hashes against the original capture/checkpoint. The recomputed values match:

| Quantity | wv073 | ir087 | ir096 | ir105 | ir112 | ir123 | ir133 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `R_M(x_b)` (K) | −1.25e−9 | −0.000411 | −0.000280 | −0.000389 | −0.000310 | −0.000182 | −0.000060 |
| `R_M(x_a)` (K) | 0.000002 | 0.832104 | 0.517639 | 0.689020 | 0.560475 | 0.391544 | 0.139013 |
| `I_M = R_M(x_a) − R_M(x_b)` (K) | 0.000002 | 0.832515 | 0.517919 | 0.689410 | 0.560786 | 0.391726 | 0.139073 |

For these two saved states, the fixed-input costs give `G_M=2.1404157250`, `G_0=0.2054073862`, and `G_M−G_0=1.9350083389`. These are endpoint contrasts under the one declared T/Q analysis; they are not a no-M reoptimization or a named-process rate attribution.

The saved-state table also matches the checkpoint. The native background and returned analysis-initial state both retain `QC max=3.4602017e-5 kg/kg dry`; the first local M slot has `QC max=3.4634193e-5`, an increase of `3.2176170e-8` at one level. The final local slot has QC and NC zero. The fixed-host-mass water measure changes by `0 kg/m²` across each captured local M endpoint pair. The analysis-initial water measure is `0.1149768213 kg/m²` below the native background. These fixed-mass endpoint measures do not close an external-flux budget. NC is reported only as its recorded model scalar; its independent physical unit basis was not established here.

The recovered native candidate remains a same-date Jul19 model-state selection, with the actual selected AMI pixel bound to it. Pixel UTC is unverified and science acceptance remains false. No same-valid-time host comparison, process-rate attribution, new date, forecast-skill claim, or overall science-acceptance result follows. The optional diagnostic does not change the main run's nonconvergence result (`UNKNOWN` termination, final gradient L-infinity `0.30415884` versus tolerance `1e-10`).
