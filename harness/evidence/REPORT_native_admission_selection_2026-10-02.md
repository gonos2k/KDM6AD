# Native admission axes and deterministic input-only selection

Baseline: `292b52ff`, PR #352. Production runtime, numerical thresholds and the
strict user-command admission rule are unchanged. This PR closes N5.1/N5.2;
branch/direct-NCCN native checks and adoption remain separate.

## Three different assessments

The runner now reports `numerical_input_checks_passed`,
`strict_pair_state_admitted` and `observational_admission=False`. Surface checks
are finite/nonnegative state, positive theta, forcing and valid XLAND. They are
the command's preconditions, not the complete KDM numerical domain: legacy KDM
also defines some negative-prognostic entry clamps/fallback states excluded by
this command. Executed finite outputs and derivative accuracy are separate
checks available only after running the operator.

PR #352's recorded first-call input passes the surface preconditions and its
executed numerical gate, yet fails the strict pair rule. [Axis receipt](native_admission_axes_2026-10-02.json)
keeps that distinction. `validate_state` still rejects the same invalid state
before user-command ABI calls; no unsupported state is newly accepted. The
historical native replay keeps its rejection/exit 1 and exposes the three axes.

Mathematically, positive same-population mass and number allow mean mass C/N;
zero mass/zero number is an inactive pair. This necessary condition does not
certify an entire physical DSD, unit basis, equilibrium or observation Jacobian.
For graupel, BG is a volume moment, not a number. Snow has no packed number field.
Observation admission means not approved/evaluated here, not a new RTTOV test.

## Selection declared before outputs

At each microphysics call, scan staged inputs before the normal C ABI forecast
call, with AD/FD probes disabled. Keep the entire native 39-level profile. A
candidate must pass unchanged strict full-profile sign/zero-pair checks and have
an interior active ice level: qi>1e-14 and rho_dry*ni>ncmin(XLAND). Here
rho_dry=double(rho)/(1+double(qv)), and configured volume ncmin is 10 for land
and sea. NCCN must have a nonempty positive input seed. This is an active ice
hydrometeor criterion, not proof that a particular rate fires.

Source anchors: `oracle/kdm6/cloud_dsd.py` inactive qc<=EPS/nc<=ncmin;
`oracle/kdm6/coordinator.py` ice n0i gate qi>=1e-14 and final number snap;
`oracle/kdm6/runtime.py` / `libtorch/src/runtime.cpp` dry-number entry conversion.
The strict selector stays above the ni=0 Picons boundary where a standalone
oracle helper and the C++ gate differ. That discrepancy is not certified by this
case; it is not resolved or silently generalized here.

Predeclared coverage follows namelist e_we=235, e_sn=283, spec_zone=1,
numtiles=2 and the private microphysics driver's tile clipping. Owned rectangle:
i=2..233, j=2..281 (64,960 columns per call). Expected disjoint tiles are
(2..233,2..142) and (2..233,143..281), at calls 1 and 2. The
[fixed collector](../select_native_admission.py) requires all four tile/call
packets, independent of what arrived. Missing/duplicate tiles cannot become a
smaller accepted domain.

Selection rule: earliest complete call containing eligible input; then maximum
native sequential sum(qi); equal scores retain ascending global (j,i). Each
native tile scans every owned input and retains its input-only local maximum;
the collector combines both maxima. Its independent checks verify completeness,
criterion and saved score/profile; the local maxima/counts themselves are
measured by the source-audited native loop, not independently reconstructed
from every discarded profile. No output/rate/FD/cost informed selection.

| Call | Runner nonnegative preconditions | Strict pair profiles | Eligible active ice |
| --- | ---: | ---: | ---: |
| 1 | 45,086 / 64,960 | 14,356 | 0 |
| 2 | 28,646 / 64,960 | 7,122 | 2 |

The chosen input is call 2, Fortran/global (142,50), XLAND=2, with
sum(qi)=7.0181845816762345e-6. Four levels satisfy the active ice criterion;
cloud/rain/graupel mass and paired moments are zero, while ice and snow are
present. The existing mixed direction retains its zero NC component; a separate
NCCN-only direction is still required. NCCN entry/final clamp behavior must be
reported; this selection does not certify its unconstrained physical process.

[Four raw packets](native_admission_census_2026-10-02),
[frozen selection](native_input_selection_frozen_2026-10-02.json) and
[exact selected input](native_selected_input_2026-10-02.npz) preserve this choice.
The selected arrays match the frozen NPZ bit-for-bit. No numbers were synthesized
and no model levels/remapping or external data were used.

## Executed evidence and next step

[Native receipt](native_input_admission_census_result_2026-10-02.json): two 40 s
local MPI rank-1/thread-1 OFF/ON runs with active en0 pinned, same executable and
zero-only candidate library. S8 probes are disabled in both. ON generates only
input packets. Full forecast SHA is identical; 254 variables at 0/20/40 s and
five energy variables at 0/20 s match raw bits. Existing host archives are reused
with fresh wrapper/ISO objects; this is not a full host rebuild or source-pin
reapproval. [Input census overlay](../native_input_admission_census.patch) is
private-host experiment wiring, not operational adoption.

Focused tests: seven runner tests, four fixed-selection tests and six preserved
native-replay tests. Tests cover unchanged rejection, missing/duplicate domain
packets, invalid moments and a changed native input score. No new framework,
physics default, release, RTTOV or observation approval is introduced.

Next, keep this frozen input and apply both directions with raw NCCN return
masks measured inside the runtime. Do not infer return branches from rounded
returned dry values. N5.3/N5.4 and the overall S8/physical/observation gates stay
open until their own criteria are met.
