# First ice velocity handoff (2026-09-30)

The C++ and Python runtimes select `mstep_i` from the pre-sedimentation
`vt_i/delz` and `vtn_i/delz`. After the main sedimentation loop, the
historical Fortran-compatible handoff supplies raw `vt_i` and `vtn_i` to
ice substep 1; later ice substeps use velocity divided by `delz`. This is
true for both legacy selector 0 and historical conservative selector 1.
The retained S1 mp337 face trace therefore measures conservative transfer
with a raw first ice handoff, even though its dry-number basis conversion
was enabled.

Selector 2 is a separate opt-in map: it keeps the conservative interface
transfer and divides the first ice velocity by layer thickness. Existing
selector meanings and default physics remain unchanged. A selected
single-subcycle cross-tree value check and local AD duality check pass;
the mixed-phase multi-subcycle fixture crosses a `prevp/psdep` branch after
small first-step differences and remains outside this approval. S1 still
needs a native selector-2 multi-substep departure/arrival and nonzero bottom
number-export witness. Physical number units remain unresolved under S2.

An isolated native mp337 selector-2 run now confirms the first-ice rate
changes by approximately `1/delz` at two layers with the same pre-ice mass.
The selected column has 14 paired positive number faces in the second call;
both calls still use `mstep_i=1` and export no ice number at the bottom.
Logging OFF/ON output is raw-bit identical at 0, 20 and 40 s. A same-executable
selector-1 comparison changes 22 variables at 20 s and 75 at 40 s, which
establishes trajectory impact but not which path is more accurate. S1 stays
OPEN. See the [native measurement](../../harness/evidence/REPORT_S1_normalized_ice_native_2026-09-30.md).

Evidence: [S1 first-ice report](../../harness/evidence/REPORT_S1_normalized_first_ice_2026-09-30.md).
Related: [[KDM6AD]] and [[KDM6AD Differentiability Audit]].
