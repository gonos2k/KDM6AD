# S15 face-cause replay preparation

**Disposition: NOT CAPTURE-READY. S15 remains OPEN.** This candidate adds a
synthetic face-to-RK arithmetic contract for the six previously selected owner-5
step-2 identities. It does not add native Fortran instrumentation or attribute
the observed QIB transitions to advection.

The validator pins the existing six-coordinate projection and QIB witness
digests separately from its six-row schedule. It requires one producer and one
RK-consumer record for every complete stage/tile/cell key. Synthetic replay
checks oriented face differences, ordinary Y/X/Z and RK3 POSITIVEDEF Z/X/Y
prefix order, conditional PD limiter operands, the separate
`advect_tend * msfty` then `sc_tend` tendency, and the RK store. These tests
validate the declared record and arithmetic contract; they do not show that a
native executable emitted those operands.

`prepare_pinned_source_recipe` only verifies the three private source hashes,
copies those files unchanged to a new shadow directory, and writes a data-only
anchor recipe. It does not generate an executable overlay. The source-copy
byte comparison is not a preprocessor or compiler macro-off check.

The missing implementation is explicit: `module_em.F` has the timestep, RK
stage, dispatch branch, and scalar-update call context, while
`advect_scalar` and `advect_scalar_pd` in `module_advect_em.F` do not receive the
owner/tile/stage identity. A real capture must add macro-gated context
propagation from `module_em` through `rk_update_scalar` into both advection
procedures, retain the selected directional face and prefix operands at the
source loops, and link those producer rows to the RK consumer rows. It then
needs compile-only validation that the macro-off preprocessing is exactly
unchanged and that macro-on source compiles before any native run is planned.

The source paths, SHA-256 pins, and ranges used to frame that work are in the
[upstream attribution plan](S15_UPSTREAM_ATTRIBUTION_PLAN.md). No private source
text or raw native event data is included here. The historical
`g33_s15_probe.py` and its hash remain untouched. No host configure, build, or
run was performed. A passing synthetic test is preparatory contract evidence
only; it does not establish conservation, a physical cause, or S15 completion.
