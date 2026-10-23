# Native ice boundary attribution and deterministic ledger v2

This follow-up to #434 fixes the diagnostic reduction contract and captures
the executed legacy ice transfer on the same native 39-level column. The
operational physics, ABI and installation are unchanged. The physical water
budget remains unclosed; its dominant QI loss is now attributed to measured
departure/arrival mismatch at internal interfaces.

## Fixed diagnostic arithmetic

`audit_applied_budget.split_changes` previously used `weights @ row` and
NumPy sums while public replay tests demanded exact JSON equality. Those
reductions can change by one ULP with the BLAS/NumPy implementation.

Version 2 fixes the operation sequence:

1. Form each binary64 weight as `float(DEN[k]) * float(DELZ[k])`.
2. Form each binary64 contribution as `float(change[k]) * float(weight[k])`.
3. Accumulate rounded contributions with `math.fsum`, level order per species
   and species-major then level-major for totals.

The same sequence applies to KDM, cleanup, applied changes and their split
residual. Tests compare the result to an exact rational sum of rounded products;
they do not relax the numerical criteria or require a particular BLAS result.
The old #432/#434 JSON and manifests are immutable. Additive v2 ledgers and an
explicit ULP change record live in
`harness/evidence/ice_boundary_attribution_2026-10-23/`. The measured state,
forcing, surface increments and same-call total balance are unchanged.

## Executed handoff

The copied-source overlay observes two velocity checkpoints and every ice
layer update. All records use **top-first** order; `level_top0=k` maps to native
WRF level `L-k` (one-based). The runtime input has `vt_i/DELZ` and `vtn_i/DELZ`,
which select `mstep_i`. After the last main sedimentation reslope, Legacy
passes raw `vt_i/vtn_i` to the first ice substep without changing that count.
Later ice reslopes normalize by DELZ. This order is present in active Fortran,
the Python oracle and C++; it is not introduced by the instrument.

In this call `dtcld=20 s` and `mstep_i=1`. Maximum initial mass work is
`0.0004357655468327452 s-1`; maximum consumed handoff mass work is raw
`0.30616369170890134 m/s`. The missing normalization changes the numerical
depletion multiplier used by the first ice consumer. These are separate
checkpoints, not two physically interchangeable quantities.

The raw-handoff source algebra is dimensionally inconsistent with the
consumer's normalized-rate interpretation. Trace field suffixes such as
`falk_qi_stored_kg_m3_s` and `out_attempt_qi_kg_kg` name the consumer's declared
coordinate; they do **not** certify those physical units for the raw-handoff
expression. Treat those records as executed algebraic numbers. State inventory
changes remain measurable in the nominal QI coordinate with DEN×DELZ, and
applied departures/arrivals below are state-equivalent bookkeeping amounts.

## Departure/arrival identity

For each interior ice layer, the source stores the pre-update fall flux.
Its own departure is capped by its entry reservoir, while the receiver's
arrival is capped by the source layer's **already updated** reservoir.
For QI, with fixed dry density and thickness,

```
O[k] = DEN[k] * DELZ[k] * applied_departure_QI[k]
I[k+1] = DEN[k+1] * DELZ[k+1] * applied_arrival_QI[k+1]
G[k] = O[k] - I[k+1]
delta_W + actual_bottom_departure = -sum(G)
```

The top cell instead subtracts raw attempted flux and clamps to zero; its
actual depletion and positivity repair must be distinguished. The bottom
diagnostic integrates stored raw flux, so it must be compared separately
with the actual capped bottom departure. In the raw-handoff branch this is a
code-equivalent diagnostic, not a dimensionally certified physical flux.
They are both zero in this case.

Five QI arrival caps bind. The sum of measured interface gaps is
`0.0012979597722250025 kg/m2`, exactly accounting for the QI sedimentation
loss; the bottom export is zero. This establishes the defect's location and
accounting mechanism in this call. It does not isolate how much an independent
velocity-only change would recover; no counterfactual physical map is executed.
The smaller later microphysics residual identified in #434 remains separate.

For NI, the kernel volume-coordinate measure is `DELZ * NI`. Its analogous
internal-count deficit is recorded conditionally. The historical host payload
basis is still uncertified; this is not a physical host number-budget claim.

## Instrumentation and first-order scope

`make_ice_boundary_overlay.py` writes three copied translation units to a new
private directory, pins all original/generated hashes and changes only the
coordinator/sedimentation trace hooks. The runtime snapshot is byte-identical.
The private archive replaces two objects in a copy of the known research core;
source, object, archive, tool and linked-library hashes are recorded. Tracing
uses explicit value-only helper scopes and the opt-in
`KDM6_ICE_BOUNDARY_TRACE` path. It is not part of the operational ABI.

The CLI result with tracing off/on is compared byte for byte with the original.
The separate `verify_ice_trace_ad_noninterference` evaluates one fixed native
point and seeds in three fresh CPU processes. It compares kernel value, JVP,
state/forcing VJP, and the existing cleanup/applied-finish value/JVP/VJP.
All products are bit-identical; the 195 applied-finish values also equal the
accepted #433 result. Public product arrays support arithmetic replay without
private libraries. This is instrumentation noninterference, not a new independent
FD, full-host/RK, RTTOV or higher-derivative certificate.

The [experiment report](../harness/evidence/ice_boundary_attribution_2026-10-23/REPORT.md)
keeps the diagnostic fix, measured physical defect and unchanged accepted local
derivative milestones distinct. A future scientific correction must retain an
explicit physical-map/variant identity and separate acceptance evidence.
