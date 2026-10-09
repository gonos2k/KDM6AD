# PR391 review resolution: saturation, active controls and a local cloud-cost path

Baseline: merged PR391 `a85b39eb`. This investigation follows the supplied
2026-10-09 review and [the item-by-item checklist](CHECKLIST_pr391_review_resolution_2026-10-09.md).
The team used `gpt-6-luna` with high reasoning: independent thermodynamics/CVT,
local KDM response, observation scope, and composed RTTOV cost. Production
physics, CVT defaults, operational installs and native inputs are unchanged.
No optimizer, host increment, new long native integration or external model/
reanalysis profile was introduced. The original target run remains invalid.

PR391 is merged at the stated baseline. Its PR-head harness/oracle checks and
path detection succeeded; native jobs were skipped. Those dated checks do not
certify this new uncommitted diagnostic work or a changed native executable.

## 1. Instantaneous clear-state diagnosis

[Green's diagnostic](pr391_clear_state_2026-10-09/GREEN_review.md) reads the
archived 66-layer profile, verifies its final 39 native P/T/Q values against
the public retained receipt, and compares the selected native NetCDF column.
The moist-air ppmv inverse uses the optical conversion's molecular masses;
the saturation calculation uses the oracle's own `Rd/Rv` and f32-stepwise
coefficient defaults. NumPy and executed Torch results agree within recorded
floating-point roundoff; this is not a bitwise host thermodynamic replay.

Maximum liquid mixing-ratio saturation is **95.5344063%** at native bottom-up
`k=3` zero-based / Fortran level 4 / RTTOV top-down layer 63. There:

| Quantity | Value |
| --- | ---: |
| Native pressure | 977.101802979 hPa |
| Native temperature | 296.748823747 K |
| Dry-air water-vapor mixing ratio | 0.0181945748627 kg/kg |
| Liquid saturation mixing ratio | 0.0190450493824 kg/kg |
| Fixed-p,q temperature gap to saturation | 0.735416085 K cooling |
| Fixed-p,T qv increase to saturation | 4.674330266% |

All 39 layers are below the liquid saturation test. On the actual `T<ttp`
ice branch, the maximum ratio is 43.2902358%, so this saved column also has
no cold-branch supersaturation under these diagnosed equations. `q/qs` is
not `e/es`; the result records separate molecular-mass and thermo-ep2 vapor
pressure conventions. The algebraic gaps are not recommended analysis
increments or an actual ascending trajectory.

This supports **instantaneous subsaturation as consistent with the clear
state**. It does not identify which earlier advection, mixing, surface flux,
subgrid variability or initialization created it. A snapshot is not a
native-process tendency attribution or independent atmospheric truth.

## 2. What can be adjusted here?

Applying the existing default CVT to the actual saved column gives **51 active
components: 39 potential-temperature controls and the lowest 12 qv controls**.
Hydrometeor masses and their direct number controls are inactive on the zero
background; stored NCCN is positive but its default sigma is zero. The
recorded all-level-qv/conserving-mask alternative gives 78 projected components;
it is not a CVT/optimizer run on this target or a new default.

With epsilon zero, multiplying a zero mass background cannot directly create
cloud water. Physical temperature perturbations are mapped by
`delta_theta=delta_T/pii`; no THM/physical-T/potential-theta conflation is made.
The model-profile cloud fraction is a detached binary content gate with value
0 or 0.999999 and bounded diameters. This is a selected-branch derivative, not
a smooth differentiated cloud occurrence probability.

Installed RTTOV guide v14, document revision 1.1.1, explains the specialized
MW/two-column/Delta-Eddington scope of `zero_hydro_tlad`; it is not enabled here
as an AMI IR cloud-creation switch. The actual current builder/RTTOV boundary
is unchanged. Nonzero indirect T/Q-to-condensate paths are tested below.

## 3. Predeclared finite T/Q reactions

[Red's response packet](pr391_tq_response_2026-10-09/REPORT.md) uses the actual
39-level selected state at `(j=86,i=48)` zero-based (`87,49` one-based), stored
NCCN, selector-2 normalized dry-number f64 policy, sea mask and number floors
10/10. Native p/pii/rho_m/delz forcing is held constant. Runtime dry density
is still computed from each call's entry qv; optical density is a separately
fixed background reference. The before/after 2.54 GB forecast hashes agree.
Subsequent small experiments reuse private checkpoints rather than full-file
replays. The gravity reconstruction difference from the public frame reader
is quantified; native pressure centers/interfaces are not remapped.

The first five cases were declared before inspecting their BT fit. Only layer
4 changes; every other initial State field, including NCCN, remains unchanged.

| Local initial perturbation | Entry qv/qs, % | qc after 20 s, kg/kg dry | Cloud gate |
| --- | ---: | ---: | --- |
| Baseline | 95.5344 | 0 | clear |
| T −0.5 K | 98.5461 | 0 | clear |
| T −1.0 K | 101.6621 | 8.249522585e-5 | cloudy |
| qv ×1.02 | 97.4451 | 0 | clear |
| qv ×1.06 | 101.2665 | 6.436213238e-5 | cloudy |

All 12 outputs are finite. The temporary coordinator observer is a separate
value-only measurement in labeled kernel units and preserves all returned
outputs raw-bit in every captured case. It is restored in `finally`; the
existing unsupported dry-number trace/budget guards remain intact. AD/FD uses
the uninstrumented map.

Local applied qv↔qc transfer closes within 3.47e-18 kg/kg and its recorded
latent-temperature update within 3.81e-14 K. The NCCN lower-reservoir clip
adds about **1e8 m^-3** to summed stage number in the strong wet cases. This
is an explicit numerical departure, not hidden conservation or an observed
external source. [The stage contract](pr391_satadj_budget_contract_2026-10-09.md)
separates activation, applied condensation/evaporation, number transfer and
clips. Initial analysis-like changes, integration departures and missing
external/heat/work/flux terms are kept distinct; full S17 remains open.

## 4. Local derivative and timestep evidence

At clear and fresh T−1 K points, the whole 20-second runtime is differentiated,
but FD comparisons cover only selected-layer **qv/qc/physical T/nc/nccn** and
the VJP dot check seeds selected qc. They are not full-state/full-column
Jacobian coverage. T differences are at most 2.51e-10 absolute; the wet-q
mixed-output scaled infinity error is 1.69e-9. The raw NC FD discrepancy 0.149
is exactly one output ULP divided by the difference interval. NCCN's 0.0830
exceeds its 0.0745 one-ULP estimate and is not explained solely by that estimate.
Physical qv/qc/T component errors are separately reported. Stage activation
pairs remain on the same gate; a full internal whole-map mask census is not
claimed. Exact local derivatives do not differentiate a finite clear-to-cloud
crossing or establish physical parameter identifiability.

For the same T−1 K initial state and constant physical-time forcing, final
qc for partitions 20, 10+10 and 5+5+5+5 seconds is respectively
8.24952e-5, 8.05243e-5 and 8.05648e-5 kg/kg. Activation histories differ.
This establishes a **local partition-dependence diagnostic**, not a convergence
order, host dynamics accuracy or a physical analysis. Full host timestep,
native multicolumn and unused-validation work remain separate.

## 5. Actual cloud → RTTOV cost and its support boundary

[The new cost packet](pr391_tq_cost_2026-10-09/RESULT.json) executes RTTOV on
the local KDM endpoints while retaining native center/interface pressures,
the original 27 reference-top layers, gases, geometry, surface and thermal
configuration. Seven requested channels 10–16, sigma 1 K, bias 0 and Huber
delta 1 are unchanged. No artificial cloud seed or pseudo-RH is used.

The original strong cloud reactions generate **new 32768 flags**: T−1 K in
channels 10/11/16, qv×1.06 in channel 10. Their masked costs therefore cannot
be compared as the original common-seven metric. All seven BTs/residuals/raw
contributions and the actual flags remain available. The intersection of
channels 12–15 is an explicitly secondary diagnostic, not a new support policy.

After this support loss, one supplemental **T−0.8 K** point was declared from
the independently confirmed saturation boundary before looking at its BT.
It tests a weak-cloud derivative witness; it is not a residual search or an
independent validation case. The five original cases remain in the record.

| Case | Seven-channel diagnostic comparison |
| --- | --- |
| Baseline | full 7/7 support; J=26.588575903 |
| T−0.5 K | full 7/7 support; J=26.492680186 |
| qv×1.02 | full 7/7 support; J=26.573211293 |
| T−1 K | ineligible for common-seven comparison; three requested flags |
| qv×1.06 | ineligible for common-seven comparison; one requested flag |
| Supplemental T−0.8 K | full 7/7 support; qc=2.005882014e-5 kg/kg; J=22.616033127 |

At that supplemental point the fresh KDM endpoint matches the cached endpoint
raw-bit in all 12 fields. The full **H composed with M** cost check includes
the KDM step, nonlinear native cloud/profile mapping, actual RTTOV K and Huber
covector. Independent FD reruns M and RTTOV. Relative directional errors are
**1.61e-7 for physical T** and **4.67e-8 for qv**, with identical seven-channel
quality and cloud masks at base/plus/minus. The qv direction is 0.01 kg/kg per
scalar perturbation unit; h=1e-5 thus gives physical ±1e-7 kg/kg. These are
local first-order cost directions, not NC identifiability or higher derivatives.

The lower J is a conditional finite what-if result, not optimization descent,
calibrated R/B/bias, forecast improvement or an approved host increment. Source
pins and [M's lineage sidecar](pr391_tq_cost_2026-10-09/M_source_identity.json)
are explicit; the sidecar is after-run inspection, not a fabricated pre-launch
capture. No new original-RTTOV source-to-binary build attestation is claimed.
An [execution-path reconciliation](pr391_tq_cost_2026-10-09/ExecutionPathIdentity.json)
records that the old baseline scratch path was later reused by profile-H finite
differences. Its current q file is the last perturbation, not the baseline main
input. The recorded baseline digest matches the immutable paired baseline;
saved numbers and the exact hash-matched executed runner are preserved. The
current runner isolates future FD paths and is not relabeled as the runner
that generated these saved values. No numerical rerun was used to hide this limit.
The observation and auxiliary case remain frozen for this local operator test;
its 20-second endpoint is not a certified pixel-time/native-forecast matchup.
The fixed source snapshot is ti=0 at 2025-07-19 05:55:40, the local M endpoint
is nominally 05:56:00, and the AMI row320/col48 receipt is unchanged. This
fixed-time what-if does not establish VIIRS/AMI pixel-time collocation.

## 6. Observation scope and outstanding decisions

[The observation summary](pr391_observation_scope_2026-10-09/summary.md) separates
measured coordinates/scan anchors, retrieved heights/phase, assumptions and
unverified pixel UTC/QA/parallax/footprint. Its scenarios are declared from
metadata rather than BT residuals. No version-matched new source closed the
CloudPhase/DCOMP QA or AMI clock questions. Receipt integrity and source-record
identity are verified within their scope; they do not approve a physical matchup.

The selected saved column is clear under the diagnosed saturation tests; T/Q directions
can create cloud in this local map. Earlier process causes, subgrid occurrence,
valid target-time execution and independently corresponding observation remain
unresolved. R2 is OPEN. R1's physical regime/threshold/moment-pair and
runtime/optical/inventory density-role admission also remains OPEN; a declared
conditional local map is not that physical approval. Existing PR370–371 and A1/A2/A3 retain their original
bounded closures; operational 37/137 defaults and cold/mixed-phase paths remain.

The user's local-review direction is implemented: saturation/control and
observation-scope diagnostics proceeded together, with local timestep work
independent of complete observational QA. A new long target execution remains
a separate decision. Full host timestep dependence, complete physical budgets,
native multicolumn and unused validation are not relabeled complete here.

## 7. Verification fixes and final audit boundary

Green/Red checked source/array identities, selected-only perturbations, units,
observer noninterference, local derivative scopes and actual six-case written
RTTOV inputs/logs. New evidence-tool P2 issues were fixed: existing-output
overwriting, mixed archive/public/forecast pairing, and ambiguous selected-five
derivative wording. The existing receipt is preserved; guards reject a copied
mismatched input before forecast access. One-based j/i metadata is corrected.
No new production P1/P2 defect was demonstrated by this bounded work.

Final reviews: [Green consistency](pr391_clear_state_2026-10-09/GREEN_final_review.md),
[Green response counterchecks](pr391_clear_state_2026-10-09/GREEN_response_review.md),
[Red composed-cost review](pr391_tq_response_2026-10-09/RED_cost_review.md), and
[cost scope check](pr391_tq_cost_2026-10-09/COST_review.md).
Submission omission audits:
[Green](pr391_clear_state_2026-10-09/GREEN_submission_omission_review.md),
[Red](pr391_tq_response_2026-10-09/RED_submission_omission_review.md),
[observation scope](pr391_observation_scope_2026-10-09/OBS_submission_omission_review.md).

Submission-independent focused checks: the two receipt-preservation/paired-source
regressions pass; undefined-name lint, Python syntax compilation and whitespace
checks pass. No full pytest/native-build/legacy campaign was repeated. Recorded
scientific executions are the new source-bound local diagnostics above, not
those omitted campaigns or a merge/CI certification.
The current guarded saturation source was also run into a fresh output; all
thermodynamic results/control projections exactly match the preserved prior
receipt ([guard verification](pr391_clear_state_2026-10-09/guarded_source_verification.json)).

Raw profiles, full native State/Forcing arrays, temporary RTTOV cases and licensed material
remain in ignored local scratch. The evidence work concluded locally; the user
requested a PR at 2026-10-09 12:13 JST and a further team omission audit at
12:14 JST. This submission makes no merge or science/operational approval claim.
Graph code and document
semantics are refreshed with explicit private-path coverage limits; the wiki
contains synthesized findings and evidence links, not raw graph reports.
The public-facing diagnostic receipts include saturation ratios derived solely
from the previously public 39-layer P/T/Q and selected seven-channel BT values
already present in the public observation packet. Those small derived/channel
records are distinct from newly publishing private checkpoints, native NetCDF,
licensed coefficients or complete RTTOV input/output assets.
