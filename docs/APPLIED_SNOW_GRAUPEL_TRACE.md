# Applied snow/graupel-to-vapor transfer trace

This observer retains the executed fp64 actual-QR/norm_actual map and the
original B512 blocks34/40. It records only native(140,76) bottom0 layers17/18
and(139,89) layer17. No physical equation, installed library, runtime default
or acceptance threshold changes. Coordinator states are native bottom-first.

For a selected signed rate r, the source convention is
`delta_QV=-dt*r`, `delta_QS=+dt*r` for snow, and the corresponding QG pair
for graupel. Negative psdep/pgdep (cold arm) or psevp/pgevp (warm arm) therefore
consume frozen mass and supply vapor. In real arithmetic each pair sums to0.
Actual updates sum all rates in source order, multiply the sum by dt once,
and add the reservoir with the existing two-rounding contract. Individual
rate×dt terms describe selected transfers; they do not partition floating
roundoff of the actual aggregate state update into named processes.

The branch is `supcol>=0` for cold state-update/group budgets, `supcol<0` for
warm. The phase-local calculation can have stricter gates; group-pre rates
are **already phase-capped outputs**, not uncapped physical attempts. Each
sequential group limiter records its actual source/value/gate/factor and the
four selected rate fields before/after scaling. The state_update raw sums and
pre-clamp moisture outputs are recorded directly, and the returned clamped
state is recorded at the outer call boundary. QV is not clamped by state_update; its later pcact branch has a
conditional QV clamp. Other moisture fields are clamped by state_update. All actual sum/rate values remain live AD tensors;
serialization is helper-local NoGrad value-only work with no result feeding
back into arithmetic. The unchanged map must retain its JVP/VJP products.

State checkpoints span micro entry, the working state before group limiters,
post-state-update, both reclassifications, post-satadj, actual internal
threshold cleanup and final DSD limiters. Their six-water inventory increments
on fixed entry `rho_d*DELZ` telescope independently of the selected rate pair
ledger. Inline D1-D4/homogeneous changes before group-pre remain an aggregate
endpoint segment; no uncapped local-kernel limiter attribution is claimed.

Cleanup changes are observed from the actual before/after state. They must
not be replaced by the earlier offline hypothetical host-cleanup array.
Internal paired cleanup thresholds are1e-15 for QC/QI and1e-9 for QR/QS/QG.
A measured cleanup sink and a conservative rate-pair relation have different
meanings. No closed full-host/energy/number budget or new derivative/RTTOV
certificate follows from this value observer. Same-variant value and selected
first-order trace off/on comparisons are required; previous milestones remain
closed in their previously demonstrated scope.
