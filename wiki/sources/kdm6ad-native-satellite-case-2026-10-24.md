# Native-domain satellite case: fixed support and explicit ABI graph mode

The [case protocol](../../docs/NATIVE_SATELLITE_CASE.md) defines one offline
MP137 endpoint → local microphysics → KO7 objective experiment on all 65,988
native columns. The original 129 partitions include the B452 tail. Profile
qualification changes observation support, never the full KDM batch.

The objective accumulates per-block numerators and divides once by the global
frozen support weight. Bounded T/Q trials originate at the same background;
losing baseline support invalidates a trial. A complete input inventory or a
pilot does not establish completion of the case, a forecast, or host cycling.

A real B512 wiring smoke exposed a gap that the NumPy-only affine mock did
not: Torch custom autograd forward/backward contexts disable GradMode, and
the called libtorch C ABI shares that thread-local state. Marking its input
leaves `requires_grad` did not restore the graph. The batch boundary now
enables its independent internal graph for recorded forward/JVP/VJP calls.
A Torch-backed affine checkpoint regression exercises that boundary, including
same-handle products and closure. The actual B512 smoke subsequently produced
finite T/Q gradients and a moist-theta-output dot error of 2.31e-14.

The first actual B512 K/RTTOV observation pilot completed in approximately
311 seconds with matching saved JVP/VJP dot sums. An earlier 180-second
RTTOV timeout is preserved as a failed attempt; the next source version has
a finite 900-second limit and a K-only copied template. These are execution
settings, not changes to derivative or cost acceptance tolerances.

Execution uses immutable private Python source snapshots and source/input
receipts. Private evidence is under
`host/research_evidence/native_satellite_case_20261024/`; raw host files and
RTTOV assets remain private. Global case completion is pending its required
129-block, derivative, trial and assembled-output gates. KO pixel UTC and
historical host number-unit migration remain unverified qualifications.
