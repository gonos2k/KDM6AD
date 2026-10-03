# Shared-entry dry density: one KDM call through actual RTTOV

This explicitly opt-in fp64 map closes the entry-density producer/consumer
connection for one Python KDM transition followed by optics. It preserves the
existing frozen observation measure, NCCN return, 17-digit output, f32/C ABI and
DAWindow defaults. It is not a new mandatory physical policy.

## Contract and implementation

For dry mixing ratio qv and fixed moist density forcing, runtime computes
`rho_entry=rho_m/(1+qv_entry)` once. It converts all four dry-specific number
inputs to volume number, uses rho_entry as coordinator dend, then divides
number outputs by the same tensor. Output humidity can change during the step;
recomputing density from that output would rescale the internal volume result.

`model_to_rttov_tensors(..., entry_qv=x_in.qv)` now supplies that explicit
entry measure to the dry-number cloud bridge. It requires fp64, cloud and dry
number mode, and rejects simultaneous fixed cfg.rho_d. No State/config/packed
ABI field was added. The default remains fixed cfg.rho_d with its existing
no-grad guard. A direct bridge caller must explicitly select live_density;
that low-level escape must carry the actual entry measure, not an arbitrary
trial/output reinterpretation.

The density tangent is `delta rho_entry=-rho_m*delta qv_entry/(1+qv_entry)^2`.
For y=M(x), the composed optical tangent includes both
`P_y*DM(x)v` and `P_rho*D rho_entry(x)v`. Runtime and optics retain the same
entry graph. Recomputing from y.qv or detaching rho would define different maps.
The local detached-state obs_adjoint_callback and existing DAWindow do not
propagate this entry graph; neither is promoted to full dry-number DA here.

## Executed scope and results

The source is the retained native sea coordinate (73,157). Frame 20 s uses the
already input-selected C5 profile. Frame 40 s is the same coordinate's next
chronological retained frame, chosen before its new radiances. Each has 39 native
levels and 24 separately declared reference-top levels, with its own forcing,
native pressure reconstruction and surface. Static nominal satellite geometry
is shared on the fixed grid. The 20 s forcing window is an isolated Python
microphysics experiment, not a new native 40/60 s host forecast or exact-time
observation comparison.

Each evaluation runs `_kdm6_pure` with conservative sedimentation, normalized
first ice, dry_number=True, dt 20 s and volume cutoffs 10/10, then the new shared
entry optical map and actual installed RTTOV DOM32. DOM32 is a numerical
reference, not selected by observed cost or certified as physical truth.
Direction: delta qv_entry=0.01*qv_entry, other entry state and forcing fixed;
endpoint width h=1e-4. All six physical profile outputs T/Q/liquid/ice content
and Deff are contracted with actual K. The profile VJP uses the transpose K
contraction. Plus/minus rerun Python microphysics and RTTOV independently.

| Retained input | BT-vector JVP/FD relative error | Duality relative residual | Quality |
| --- | ---: | ---: | --- |
| 20 s | 2.1117988524e-8 | 3.7959456265e-16 | all 9 zero, BASE± identical |
| 40 s | 7.2086564257e-9 | 0 | all 9 zero, BASE± identical |

Both pass the unchanged 1e-5 vector FD and 1e-12 duality gates. BASE/plus/minus
CFRAC arrays are identical within each run, so the detached cloud-activity gate
is not crossed in these tested directions. This does not certify every upstream
microphysics branch, every control, a named-process coefficient derivative or
higher derivatives. No physical/observational approval is inferred.

At the 20 s input, output qv differs from entry qv by up to 3.7572867224e-6 kg/kg.
The test checks cloud content equals 1000*rho_entry*qc_out and differs from the
output-humidity recomputation. [The density-tangent comparison](ENTRY_density_tangent_comparison_2026-10-03.json)
has identical primal values for shared-entry and frozen-at-base density, but
BT tangents differ by up to 1.1859041414e-4 K in this qv direction. This isolates
an extra derivative term; it is not a physical ranking of the two operators.

[The execution receipt](ENTRY_execution_receipt_2026-10-03.json) records source,
installed engine/coefficient/table hashes, actual options and case input hashes.
Public `ENTRY_density_frame20/frame40_{base,plus,minus,derivatives,result}` files
retain arrays. [The probe source](ENTRY_density_probe_source_2026-10-03.py) is a
bounded local experiment requiring the existing licensed RTTOV fixture, not a
new product entry point. The [40s raw profile](ENTRY_density_frame40_profile_2026-10-03.npz)
and executed corrected preparation source/receipt preserve that follow-up input.

Two prototype/preparation failures are recorded: a reporting inner product used
matrix multiplication for 1×39 arrays, corrected to the Frobenius dot in a new
run; the first 40 s writer refused a stale 20 s fixture pressure grid before RTTOV.
The retry uses the original 40 s model arrays and correct 40 s native grid, with no
input or tolerance adjustment. Corrected preparation re-execution gives every
profile array exactly equal to the subsequently probed 40 s input.

## Solver policy and remaining science

[The common-support report](ENTRY_common_support_solver_report_2026-10-03.json)
retains the old optical-only NC comparison on AMI 10–16. Max BT difference is
0.312639889 K and NC tangent difference 1.6879974e-4 K. That is 15.6243% relative to
DOM32's max norm, or 14.056% relative to the larger solver norm; denominators
must be stated. Absolute channel JVP/FD errors are reported with endpoint
binary-grid resolution estimates. Those estimates are not bounds on all internal
arithmetic. Small WV073 signal does not get a uniform relative-accuracy claim.

No physical BT/gradient acceptance tolerance is invented from these samples.
Original 100/10 land/sea units/calibration remain undocumented; Registry labels
QN as #/kg but leaves threshold units blank. The known G33 row-scalar issue is
not reopened here, and equal 10/10 makes locality immaterial in these runs.
Independent optics/physical accuracy, observational covariance/cost approval,
full DAWindow routing and native/ABI re-execution remain OPEN.

Validation: 3 focused entry-contract/composition tests plus 5 existing dry-optics
tests passed; actual composed RTTOV runs and retained failure/lineage checks
are separate evidence. Green/Red and CI results are recorded at PR completion.
