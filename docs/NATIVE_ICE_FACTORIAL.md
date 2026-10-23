# Ice-only 2x2 comparison and full-domain preparation

The four-arm native-column experiment is complete. The full-domain input
packet, batch executable and dry-run plan are prepared; **the full-domain
KDM experiment has not started**. This is an offline split-physics study,
not host integration, data assimilation, RTTOV evaluation or map adoption.

## Independent factors

| Mode | First ice handoff | Ice arrival |
| --- | --- | --- |
| `raw_cap` | Legacy raw VT/Vtn | Stored flux capped by source post-update reservoir |
| `norm_cap` | VT/DELZ, Vtn/DELZ | Same Legacy cap |
| `raw_actual` | Legacy raw VT/Vtn | Source's actual departure mapped to receiver |
| `norm_actual` | VT/DELZ, Vtn/DELZ | Source's actual departure mapped to receiver |

Every arm keeps the **main rain/snow/graupel chain Legacy**. Existing full
conservative variants would change that chain too, so they are not used as
the factorial arms. Only the first ice handoff and ice recurrence pointer
change in a generated, private source copy. Subsequent ice reslopes and the
initial normalized substep selection are unchanged. The selected native case
has one ice substep and frozen forcing in every arm.

The actual-arrival recurrence reuses the existing conservative ice function:

```
departure_u = min(attempt_u, entry_u)
arrival_l = departure_u * (DEN_u * DELZ_u) / (DEN_l * DELZ_l)
```

For the kernel's volume-number coordinate, use `DELZ_u/DELZ_l` instead.
Bottom fall diagnostics in this recurrence accumulate actual capped departure.
The Legacy attempted-rate diagnostic and its raw-velocity dimensional caveat
remain separate. Actual bottom departure is `DEN*DELZ*out_applied_QI`;
`DEN*DELZ*(QI_before-QI_after)` is net bottom-layer depletion and equals
departure only when arrival is zero. Nonuniform-measure tests exercise nonzero
bottom arrival and departure explicitly.

## Same-column experiment

The request is the admitted #435 39-level column, SHA-256
`4867805f5318f1ad28b05101ffc583d50000309ed80b81c4379fb9c9e77082e2`.
Nine separate value-only calls cover an unset-mode baseline and trace off/on
for each arm. Each arm's traced/untraced full response matches bitwise; the
baseline and `raw_cap` also match the original #435 response. Non-ice mass
fields match bitwise across arms immediately after sedimentation. Later
microphysics is allowed to respond to the changed ice state.

| Mode | QI change + actual bottom departure, kg/m2 | Raw total-water change, kg/m2 | Applied total-water change, kg/m2 |
| --- | ---: | ---: | ---: |
| raw_cap | -1.297959772225e-3 | -1.298549204766e-3 | -1.299094197389e-3 |
| norm_cap | -4.26049e-20 | -8.285370684791e-7 | -2.632990853830e-6 |
| raw_actual | -1.19962e-19 | -5.894325409405e-7 | -6.698501538210e-7 |
| norm_actual | -4.25784e-20 | -8.285370684791e-7 | -2.632990853830e-6 |

Bottom QI departure and arrival are zero in this native case. The three
counterfactuals remove its large ice-transfer deficit down to numerical
roundoff, but the later microphysics and cleanup residuals remain. In this
case `norm_cap` and `norm_actual` return identical full kernel states; this
does not establish equivalence on other columns or regimes.

The QI two-factor interaction is approximately -1.29795977e-3 kg/m2: the two
individual recoveries cannot be added as independent gains. Raw conservative
transfer can preserve inventory while retaining the wrong velocity scale, so
inventory closure alone cannot select a meteorologically valid map. Changed
H/QV/QC tendency profiles are recorded in the public result; they are not a
forecast-skill or observation-fit result.

## Derivative contract for a later selected candidate

This experiment is value-only and selects no candidate. Existing accepted
Legacy AD milestones remain closed. A selected alternate map needs its own
JVP/VJP and branch-preserving independent FD checks.

With inactive denominator floors, `a_l=R*d_u` and
`R=(rho_u*dz_u)/(rho_l*dz_l)`, its tangent is

```
da_l = R*dd_u + a_l*(drho_u/rho_u + ddz_u/dz_u
                     - drho_l/rho_l - ddz_l/dz_l)
```

Its pullback adds `R*bar_a` to departure, and adds/subtracts
`a_l*bar_a / metric` to source/receiver metric inputs. NI omits the density
terms. First-handoff normalization has `dr=dv/dz-v*ddz/dz**2`. The capped
departure, actual state update, finish's old-state direct term and any live
forcing chain also belong in that selected-map derivative. No derivative
of the alternate arms or higher derivative is certified here.

## Full native-grid preparation

There is no full-domain pre-MP capture corresponding to the selected-column
request. The available genuine MP137 restart is the **00:00:40 endpoint**.
The prepared full-domain study therefore initializes a separate offline
physics experiment from that endpoint, preserving all 234x282 native columns
and 39 mass levels. It is not the actual next host MP call, not a forecast
time advance, and not a tiling of the original pre-MP column request.

The producer reads THM_2/QV/MU_2/PH_2 and native geometry, recomputes the
continuous fp64 prep map, then stores 12 state fields, four forcing fields
and XLAND in binary64. All 129 files are reread for dtype, exact stored-value,
index and hash checks. There are 65,988 unique columns, zero gaps/duplicates,
and 387 sampled comparisons against the public one-column prep function.
The 330,922,260-byte packet stays private; only its inventory/hashes are public.
Namelist flags, restart attributes, native dimensions and actual Times were
also independently checked after preparation.

Raw negative NC=1, NI=6 and BG=2 values are preserved and counted; no hidden
repair or number-unit migration is applied by preparation. The existing kernel
entry clamps remain part of the experimental map. Historical host number
units are not admitted as physical volume/dry-number coordinates. The old
MP37 KO input packet is not relabeled or used as MP137 input.

The [batch protocol](ICE_FACTORIAL_BATCH_PROTOCOL.md) supports B-column calls.
The fixed plan is 512 columns per batch, final batch 452, 129 batches per arm.
It proposes 10 workers with one CPU thread each, running arms sequentially;
the CLI defaults to dry-run and one worker, so execution requires explicit
`--execute --workers 10`. Batch composition affects global substep maxima and
is part of this experiment identity. A duplicated-column B=1/B=2 smoke is not
proof of invariance under arbitrary batching.

The prepared run configuration pins `dt=20 s`, `ncmin_land=10` and
`ncmin_sea=10` to the saved namelist. It supplies these explicitly for every
arm; no implicit batch-runner scalar defaults are used. A private configuration
has executable local paths; the public view uses private-artifact identifiers
and hashes. The four-arm request/response payloads need about 3.63 GB in
addition to the prepared input packet, before optional postprocessing output.

Full-domain preparation includes native edge cells but does not emulate host
boundary cleanup, dynamics/RK, radiation or retained-memory consumption. The
batch plan evaluates KDM states and precipitation; it must not be described as
a full-host timestep or regional DA cycle. Runtime and peak memory for the
full-domain candidate experiment have not been benchmarked.
