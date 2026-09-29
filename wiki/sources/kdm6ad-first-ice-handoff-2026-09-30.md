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

Evidence: [S1 first-ice report](../../harness/evidence/REPORT_S1_normalized_first_ice_2026-09-30.md).
Related: [[KDM6AD]] and [[KDM6AD Differentiability Audit]].
