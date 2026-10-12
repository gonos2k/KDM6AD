# Historical06/07 native snapshots: two actual all-sky H calls

Exactly two value-only real RTTOV H evaluations returned successfully on the
already saved PR416 historical06/07 Jul19 ocean-column snapshots. No05 call,
forecast reopen, native/KDM integration, optimizer, new L1B or other date was
added. Both evaluations preserve all seven physical AMI channels10–16 with
model quality0.

| Channel | H06 BT K | H07 BT K | 07−06 K |
|---|---:|---:|---:|
| WV073 | 260.993295 | 261.064118 | +0.070823 |
| IR087 | 291.239087 | 292.096637 | +0.857550 |
| IR096 | 268.863387 | 269.404783 | +0.541396 |
| IR105 | 293.726288 | 294.495789 | +0.769501 |
| IR112 | 293.526337 | 294.268335 | +0.741998 |
| IR123 | 290.810611 | 291.473704 | +0.663093 |
| IR133 | 275.516182 | 275.891629 | +0.375447 |

The historical snapshot change therefore gives a nonzero AMI observation-space
response under the declared H family. It is a **joint** response to changed
T/Q/hydrometeors, pressure/interface grids, layer metrics/density and surface;
no channel's delta is attributed solely to cloud disappearance, latent heat,
transport or any named routine. Nonzero state differences need not always give
nonzero H differences; here the actual two evaluations establish the values.

This is a one-hour historical MP137 four-rank diagnostic, not PR415's same
initialization/variant/forcing comparison, not a20-minute matched magnitude
comparison, an observed temporal fit or independent-date/forecast-skill result.
No AMI observation target/residual/cost is used. The y=zeros[1,7] placeholder
exists only for the existing forward interface; mask ones requests/checks all
seven channels and its returned dummy cost is discarded. No adjoint is
requested (`grad=False`); the unchanged wrapper may still generate K internally.
Count is **2 logical H callbacks**; internal direct/K/process counts are
unmeasured, not asserted equal to2.

## Consistent per-time H inputs

Saved native39centers/40Python-P8W interfaces and dry potential-temperature,
water/hydrometeor/number coordinates are retained. Correct physicalT is
`theta_dry*PII`, withdrytheta=(THM+300)/(1+Rv/Rd*qv). Each snapshot supplies its
own p/Exner, thickness, moist/dry density and skin/near-surface state. Optical
rho_d is frozen **within each call from that snapshot**, not silently shared
from06 to07 and not made a live control. This differs explicitly from the
fixed-background-density PR415 inner problem.

Both H configurations use the same declared channels, coefficient/hydro-table
assets, KMA BT coordinate, dry_number policy, AMI GEOS/pixel geometry rule,
zero native/reference blend and reference gas/upper-atmosphere source files.
Reference extension/discretization follows the same existing rule on each
snapshot's native pressure grid (27reference+39native layers;67interfaces).
Geometry donor is the original AMI pixel row289/col49; state/HGT is native
j103/i48 about425.9m away. This fixes a preparation-only coordinate mix-up
before output creation; no observation target is borrowed or invented.

H surface U10/V10 retains the existing raw V4 convention; rotation/basis is not
independently verified. Historical number dry/moist basis remains a declared
raw-coordinate assumption. Old executable/input-byte and chainp date-attribute
limits persist; current H assets are newly bound, not proof of the historical
producer's binaries. Parent forecast is not substituted for the run-specific
child. Pressure-based auxiliary changes are recorded as part of the joint H
comparison, not isolated microphysics effects or a same-H-input causal test.

## Measure and layer interpretation correction

The PR416 QC path is **sum(qc*rho_d*delz)**, an EOS/geometric dry-layer measure,
not its separately stored WRF eta mass or PR415's fixed eta analysis measure.
The old phrase “host dry-mass weights” must not be read as equivalence of those
metrics. [Measure/layer clarification](MEASURE_AND_LAYER_CLARIFICATION.md)
provides the formula and saved-value context without changing old execution
bytes or re-extracting profiles.

Only k3 around259m has cloud at05/06. It warms +0.18098K then+0.41317K while
qc decreases and qv/total-water mixing ratio increases. The full-profile max
cooling −2.52244K is k37 around20km; it is not cloud-layer evaporation cooling.
These snapshots do not identify individual process rates or closed water/heat
flux budgets, and do not supply06:06/06:16 host hydrometeor states by interpolation.

## Validation and completion

Both prepared contexts and private TIME_INPUTS are source/hash bound. Original
33H external assets,23source/input bindings and23fixture hashes are checked
before/after evaluations. Fresh fixtures/output paths and exclusive marker
prevent overwrite/retry; no private NPZ is published. Green/Red review the
saved inputs/results separately. Preparation API/coordinate errors were fixed
before either actual H call; no production physics/AD/solver was changed.
Ruff passes; portable CI is separate from these actual private RTTOV calls.

The minimum requested forward comparison is now complete. This supports
considering a separately declared time-varying-input/tendency study; it does
not establish that varying thermo forcing alone supplies missing host dynamics,
transport/PBL/radiation/surface processes or that a new model change is required.
No extraH05, four-H/optimizer comparison, new solver or automatic budget follows.
Jul20/21 native analyses remain pending; historical management79 is not rescored.

[Plan](PLAN.json), [actual result](RESULT.json), [channel table](CHANNEL_RESPONSE.csv),
[measure/layer clarification](MEASURE_AND_LAYER_CLARIFICATION.md).
