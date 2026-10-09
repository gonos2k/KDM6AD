# PR390 follow-up: measured MPI forwarding and one-profile extinction

Baseline: PR #390 `ada6fc42`. Work is local in an isolated worktree. The closed
distance P3 remains closed; no geometry or Huber-cost replay was added. Production
physics, AD, sigma/bias, channel admission and operational installations are
unchanged. No long native integration was repeated. The diagnostic phase was
local; the user subsequently requested this bounded evidence/decision PR on
2026-10-09. Private host/RTTOV source, binaries, assets and raw profiles are excluded.

## MPI control and short host path

The [minimum Fortran control](mpi_finalize_control_2026-10-08/REPORT.md) completed
`MPI_Init -> MPI_Finalize -> _Exit(0)` in four one-rank launcher arms: MPI-only
and the historical KDM6AD/PyTorch runtime, each with/without the original observer.
All launcher return codes were 0. The observer recorded finalize entry/return
and the requested C exit status. Two separate singleton launches returned
direct-child wait status 0; those use a different launch path and are not a
measurement of a rank's wait status under `mpirun`.

A [separate short host pair](host_short_exit_2026-10-08/result.json) used the
unchanged historical native executable, KDM6AD dylib and harness runner with
identical active inputs. Each fresh case ran 20 model seconds, one rank/one
thread, with a 60-second wall deadline. The observer was exported only to MPI
children. This is the isolated experimental **mp337**, normalized
`physics_variant=2`, `dry_number=1`, `value_only=1` path; it is not an
operational mp137 or host-AD verification. Both completed naturally: outer
runner status 0, harness
`experiment_valid=true`, WRF success marker, elapsed 50.95/51.37 seconds. The
observer arm recorded actual WRF finalize entry, return with `ierr=0`, and
`_Exit(0)`. These are requested rank-exit markers plus the launcher/harness
outcome, not an independent `waitpid` observation of the MPI-launched WRF rank.

The actual saved times are **2025-07-19 00:00:00 and 00:00:20** in both cases.
The unchanged strict comparator found **254/254 variables bit-identical at
each frame**, including character Times, with no unsupported/skipped variables
([state receipt](host_short_exit_2026-10-08/state_comparison.json)). This supports
observer noninterference in the saved output of this initial-time one-step pair.
It does not certify later model states or the historical 358-minute run.
Original executable/library/observer/runner before/after hashes match.

The SDK compile failure and a control's initial mismatched Python 3.9 runtime
loader failure remain recorded separately. Final successful linked controls use
the target executable's Python 3.10 runtime. Neither earlier failure explains the
historical target launcher exit 1. No system routes or security settings changed.
The MPI control's Python runner hash identifies its current, post-run
metadata-corrected source. A pre-edit orchestration-source hash was not retained;
the Fortran source, executed compile/launch commands, binaries, logs and original
input/library pins remain available. The short host pair separately has an
immutable executed Python source capture.

**The historical long-run cause and validity remain unchanged.** Its target
arrays are diagnostic-only. A successful initial-time smoke cannot validate the
05:55:40–05:58:00 target window or explain the previous shutdown failure.

## Actual RTTOV extinction from the fixed saved profile

The [single-profile derived receipt](rttov_actual_extinction_2026-10-08/actual_extinction_profile_summary.json)
uses saved `case_00`: one profile, 66 layers, requested RTTOV channels 8–16.
The unchanged original executable first reproduced all 11 retained direct/K
output files byte-for-byte. A privately isolated diagnostic source/object/library
and executable then recorded actual `ltick`, clear-sky base, total extinction
before/after clipping and warning application in the same calls. Source-derived
RTTOV code, licensed assets and raw profiles remain in ignored private scratch.
The receipt identifies source/build/input/dump hashes and caller order; this is
new diagnostic-build evidence, not recovered historical internal arrays.

Both the explicit forward call and the K call's forward pass produced the same
measured extinction arrays. For channels 8/9, actual triggering layers are:

| RTTOV channel | Top-down layer, 1-based | `ltick`, km | Pre-limit total, km^-1 | Post-limit total, km^-1 |
| --- | --- | ---: | ---: | ---: |
| 8 | 65 | 0.067785523 | 32.839162969 | 20 |
| 8 | 66 | 0.052836564 | 38.407032752 | 20 |
| 9 | 64 | 0.086209425 | 20.147651516 | 20 |
| 9 | 65 | 0.067785523 | 21.684010584 | 20 |
| 9 | 66 | 0.052836564 | 22.595689756 | 20 |

The recorded total equals the clear-sky gas-path base in both retained categories;
the logged base is **after** RTTOV's `MAX(base,min_ext_delta_edd)` floor
(1e-10 km^-1) and before the maximum 20 km^-1 cap. Unfloored bases for all
non-triggering layers were not captured. All reported trigger values exceed
20 km^-1, so this minimum-floor qualification does not affect their attribution.
the additional hydrometeor contribution is zero. Aerosols are disabled. The
zero-content/fraction inputs include nonzero size parameters; this does not
mean all hydrometeor-related input files contain zeros. The
instrumented warning matches the retained quality vector
`[32768,32768,0,0,0,0,0,0,0]`. Channel 10's maximum is 5.987125995 km^-1,
below the limit. Individual gas species were not decomposed; this does not
identify a water-vapor, ozone or CO2 error. The clipping operation remains the
original `MIN(total,20)` and is distinct from the separate OD30 calculation.

The diagnostic executable's same 11 output files are byte-identical to the
original rerun and historical saved output, including radiance, transmission
and `profiles_k`. This demonstrates output noninterference for these two calls
on this one input, not all profiles, internal arithmetic or higher derivatives.
The old hydrostatic proxies remain historical estimates, superseded here only
for this diagnostic profile by actual array measurements. No layer merge,
coarsening, solver change or warning-channel readmission was applied.

## Fixed-candidate meteorology and remaining work

The [physical-questions note](PR390_selected_candidate_physical_questions_2026-10-08.md)
keeps warning attribution, common-cloud sampling and model clear-sky causation
separate. The candidate stays fixed. Cloud QA, actual pixel UTC, parallax datum
and common footprint remain open. The modeled zero condensate versus retrieved
liquid category is still unexplained; the short initial-time smoke does not
reproduce that target state. No NC-only, ozone-cause or calibrated-error claim
follows from these diagnostics. Sigma 1 K/bias 0 remain exploratory settings.

| Review question | Result in this follow-up |
| --- | --- |
| Minimum Fortran MPI observer forwarding | Demonstrated in the attributed controls |
| Short host startup/finalize/normal exit | Demonstrated for the paired initial-time 20-second cases |
| Saved-output observer noninterference | Raw-bit equality at the two saved smoke times |
| One saved profile's actual warning layers/components | Demonstrated in the separate instrumented RTTOV build |
| Historical 358-minute exit-1 cause | OPEN; not reproduced or explained |
| Valid target-time native run / first independent case | OPEN; R2 remains OPEN |
| Common physical observation sampling / model cloud cause | OPEN |

Full oracle/harness pytest, native CI and legacy mp37/mp137 parity campaigns were
not run: no production arithmetic changed. The two executed smoke-output frame
comparisons and single-input RTTOV comparisons are the relevant new checks.
[Green](GREEN_review_pr390_small_diagnostics_2026-10-08.md) and
[Red](RED_review_pr390_small_diagnostics_2026-10-08.md) cross-reviews checked
consistency, counterexamples and demonstrated coverage. Configure-hash and
host-receipt-list omissions were corrected as metadata-only changes, preserving
executed source captures and failure logs. No new required production P1/P2
finding was identified within this bounded review.

## Knowledge coverage

The initial canonical graph query did not cover these private MPI/RTTOV paths.
The isolated worktree's public code graph was rebuilt with `graphify update .`;
bounded document semantics connect measured controls/arrays to their explicit
historical-run and observation limits. The private host and licensed RTTOV
source/build trees remain excluded from the structural graph, so their executed
paths continue to rely on source/build receipts. Raw graph output stays in
`graphify-out/`; the wiki contains a synthesized source note and evidence links.
