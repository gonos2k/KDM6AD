# Adopt the bounded fp64 dry-number NCCN return

The supported native case selected before outputs passes both mixed and
NCCN-only 12-field FD/duality checks, strict input/output pairs and actual
39-level return-mask locality (PR #354 evidence). The previous arbitrary 50%
choice is absent. On that bounded evidence, Python and C++ now use zero-only
live-delta arithmetic together in the opt-in dry-number fp64 path.

```
N_in = rho_d * n_in              # capture the exact live conversion once
Delta = N_out - N_in
return where(Delta == 0, n_in + Delta/rho_d, N_out/rho_d)
```

At zero value the Delta term must remain live: its derivative may be nonzero.
The formal derivative equals the direct expression's real-arithmetic derivative;
quantized machine operations and new process branch crossings still need their
own interpretation. No custom gradient, detach or value-based tangent erasure
is introduced. Other QN fields retain direct return. C++ explicitly gates the
change on fp64 entry dtype; f32 return and all physical/default/ABI policies stay
unchanged. Python mirrors that dtype gate. No logger is installed in main.

## Rebuilt and clean checks

[Acceptance receipt](main_nccn_zero_return_acceptance_2026-10-03.json) records the
fresh local library, source `4f3fbf0`, fixed command configuration/input hashes
and two clean-worktree executions. The unchanged command on retained zero-based
(3,272), frame 1 passes graph/value equality, JVP/VJP duality and all 12 field
FD criteria. Both metadata records and all 14 saved arrays are identical.
The second client uses the same new library, not an independent second build.
No column, direction, h=1e-4 or threshold is changed to pass. The
[actual command arrays](main_nccn_zero_return_column_2026-10-03.npz) are preserved.
The original direct library/input failure remains in the existing archive.

Using the exact supported native trace input, the new uninstrumented library
also reproduces the base, both JVP/VJP arrays and four value-only endpoints
**bit-for-bit** (nine arrays) from the isolated native evidence. This is an
independent C ABI replay, not another host trajectory. The prior real OFF/ON
forecast and return-mask measurements are not relabeled as new main-host runs.

Local validation: 22 focused Python runtime/boundary checks and one fresh C ABI
test. A new runtime guard feeds both original plus/minus states and the base
through the actual oracle, requiring exact no-op NCCN identity. No production
f32 change is inferred from a mock; source dtype gating and prior native
forecast identity distinguish the precision contracts.

## Remaining boundaries

This closes selected NCCN return arithmetic adoption and the rebuilt diagnostic
execution, not S2/S8's full physical/DA/observation gates. Number units/threshold
physics, upstream process branches, Jacobian generality, budgets, MPI/restart
and operational approval remain unresolved. The exact-zero machine selector
has documented neighboring ULP effects. Successful diagnostic output keeps all
physical/operational/observation approval flags false.

The supported workflow and success/failure interpretation are in
[the existing command guide](../../docs/NORMALIZED_DRY_COLUMN.md). Deployment,
release publication and new generalization prerequisites are deferred.
