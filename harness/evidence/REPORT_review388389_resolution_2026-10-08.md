# PR388–389 local resolution

Baseline `ac3a4ec7`. See the [item-by-item checklist](CHECKLIST_review388389_resolution_2026-10-08.md)
and [supplied review identity](REVIEW_REQUEST_PR388_389_2026-10-08.md). The investigation was performed locally and the user requested its PR at
18:37 JST. This submission contains bounded correction/source/metadata evidence;
no account change, raw private-data publication, long native rerun, canonical
source edit or operational install replacement was performed.

## Resolved metadata and interpretation

The historical AMI–native field incorrectly copied AMI–VIIRS distance. A
[hash-linked sidecar](NATIVE_geometry_correction_result_2026-10-08.json) now gives
679.550498963 m and 686.643622876 m respectively; native–VIIRS is 7.367358701 m.
A [next-producer patch](NATIVE_geometry_next_producer_2026-10-08.patch) computes
three explicit endpoint pairs. It was applied to a new source copy and its syntax
and metadata routing checked; the historical executed source/result stayed intact.
Five focused tests pass, including source immutability, independent chord geometry,
mismatch rejection and exclusive output creation. The full producer was not rerun.

The previous table now declares **KMA v3.0 BT-coordinate** values formed from RTTOV
TOTAL radiance, not native RTTOV BT or approved sensor SRF compatibility. The
acquisition checklist now distinguishes saved target states from a valid native run.

[Retained-result arithmetic](NATIVE_review_interpretation_result_2026-10-08.json)
confirms conditional scan-time separation 45.398366–107.029631 s. Actual pixel UTC
and common footprint remain unknown. All 56 common residuals lie in the linear
Huber region, making MAE/cost algebraically related. Within eight saved times,
IR105 varies only 0.0097643664 K while its residual is about 4.93 K. The selected
model has zero condensate, while VIIRS supplies a liquid retrieval category; this
is a cloud-presence disagreement, not an NC-only experiment. IR096 contributes
24.4063% of the first cost and uses reference ozone; no ozone-cause claim follows.

## Native termination remains open

WRF's success message occurs before shutdown. The source-defined non-coupled DM
path would subsequently call MPI_FINALIZE and the C `_Exit(0)` helper, but the
historical run has no terminal call/return or separate rank-exit/signal trace.
Some finalization objects predate the final link and lack preserved build-time
hash pins; current source/object comparisons do not fill that historical gap.
The generic PRRTE message cannot establish an exact cause.

A new process-only observer was compiled locally and tested on a tiny C `_Exit`
control. A separate fresh 40-second case used the original native executable,
library, runner and allowlisted input files, one rank/one thread, with the observer
exported only to MPI children. Its **60-second wall deadline expired without a WRF-start marker**. The observer-load marker exists; MPI finalize entry/return and WRF success markers
do not. Our own SIGTERM gave the outer harness wait status -15; this is neither the
historical exit 1 nor a separately observed rank signal. Marker absence does
not prove that model initialization never began. No signal handler or system route/security
setting was changed. All pinned original files are unchanged and no native process
remains. [Bounded receipt](NATIVE_exit_observer_probe_result_2026-10-08.json).

This tests observer loading and the C control only. Fortran finalize forwarding
and numerical instrumentation noninterference were not demonstrated, and the
historical native validity remains false. Do not promote the probe or blindly
repeat a long case. Target-specific runtime evidence is still needed.

## RTTOV warning diagnosis is partial

[Installed-source audit](NATIVE_warning_source_audit_result_2026-10-08.json) identifies
bit15/value32768: any total layer extinction above 20 km⁻¹ triggers clipping.
Gas extinction participates; this is distinct from the separate OD30 constant
and a total-column-transmission threshold. Zero hydro content is consistent with
the warning.

Delegated inspection of the saved eight transmissions shows strong gas absorption
in thin lower native layers. Hydrostatic-thickness proxies identify top-down
indices 63–65 as candidates, with channel8/9 proxy maxima above 20 km⁻¹ and
channel10 about 6.1. These are **not** RTTOV's actual ext/ltick values; cumulative
transmission near limits may also lose OD information. The exact triggering layer
requires a separately attributed instrumented RTTOV diagnostic. Installed source
inspection is not source-to-executable build attestation. No RTTOV rerun, solver
change, channel readmission, sigma/bias adjustment or new physics approval occurred.

Existing A1/A2/A3 and prior limited numerical closures remain closed. R2, normal
native termination, physical cloud QA/footprint and exact warning attribution
remain open. Raw graph output stays under graphify-out; private call-graph coverage
is incomplete and investigations use source/artifacts directly.
