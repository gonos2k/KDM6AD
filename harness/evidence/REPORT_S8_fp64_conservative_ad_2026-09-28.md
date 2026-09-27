# S8: explicit fp64 conservative-interface DA entry

The existing `kdm6_step_ad_c` remains Legacy. The additive
`kdm6_step_ad_variant_c` takes the same packed fp64 state and forcing plus an
explicit physics selector: 0 selects Legacy, 1 selects the existing
conservative-interface substeps. It returns the existing fp64 JVP/VJP handle;
at the C boundary, unknown selectors fail before tensor work with a null
handle and untouched output. The Fortran ISO wrapper exposes the same call;
Fortran callers must discard its `intent(out)` result on error. The production
mp337 wrapper, operational f32 default, physical unit interpretation, and
deployment path are unchanged.

The focused C++ and Fortran ABI tests passed. They check variant-0 equality
with the old fp64 symbol, variant-1 graph/value-only equality, finite
directions and cotangents, JVP–VJP duality, pointer-nulling close, and invalid
selector rejection. The macOS dylib exports exactly the declared 10 C symbols;
the fresh-process OpenMP environment/ABI check also passed. Ubuntu/macOS CI
results for this change are not yet available.

For an additional **local ABI call**, one 39-level column was selected from
the retained mp337 host-entry capture by the largest input `qi` sum among
columns with nonnegative hydrometeors. Its capture-local zero-based index is
`(i,j)=(198,9)`, with `xland=2` and `dt=20 s`. The captured f32 values were
promoted exactly to fp64; forcing was held at that captured call. The private
capture SHA-256 is
`ac543e94c6c9b9e5b3a099f6854c487a300dc3d6e568c3b5948599454d7801a6`.
The isolated library SHA-256 is
`e644effe5c109988755502597c0b35a28dd42e74a6219882f70bb839d195a028`.

On this column, the old fp64 symbol and new selector 0 produced raw-bit-equal
forward arrays. Selector 1 returned finite forward, JVP, and VJP arrays and a
live handle that closed to null. With the input `qi` profile as direction and
`u=Jv` as covector, the two dual products both printed
`3360522944.490746`. Centered finite differences of the selected fp64 map
had maximum state-array relative differences from its JVP of
`7.51e-9`, `1.92e-8`, and `6.78e-8` for widths `0.1`, `0.03`, and `0.01`.
Those widths were not independently branch-certified; this is one selected
column, not a general derivative bound.

This is **actual host-state input through the isolated C ABI**, not an
in-host derivative run. The production mp337 wrapper still requests
`value_only=1`; fixed forcing and the existing discrete `mstep` selection are
not differentiated. Full host handle routing, normalized fp64 branch coverage,
physical number units, and observation-cost acceptance remain OPEN under S8
and their separate gates.
