# G1: dynamic ice consumption contract, with a native mstep census

## What is generalized

The PR233 fixed 39-layer replayers and their assertions are unchanged. New small
experiment helpers separate raw velocity from normalized rate, bind each
consumer to a producer generation and an independently selected schedule, and
exercise the shipped `slope_kdm6_torch` and conservative ice kernel together.
There is no new transport algorithm, production default, ABI, QC or tolerance
change. This is **oracle-level dynamic ice-chain evidence**, not completion of
all G1–G4 generalization goals.

`ice_consumption_contract.py` contains the common operations; the synthetic
case specifications and report generation are in `dynamic_ice_probe.py`.
Expected consumer keys come from the external cycle/column plan, never from
received records. Producer IDs are derived from cycle/substep independently of
record-side expected IDs. Tests reject deletion plus a shortened declaration,
duplicates, matching-but-stale IDs, and a rewritten consumed substep count.
Normalization accepts a velocity packet and returns a different rate type;
passing a rate back for normalization is rejected. These are programming
contracts, not independent authentication of a producer's physical units.

Geometry is preflighted as finite/positive outside AD. The actual division and
consumer preserve tensors and their gradients. Consistent length-unit scaling
(v,dz) -> (100v,100dz) preserves rate within declared binary64 rounding. The
normalization JVP includes both dv/dz and -v*ddz/dz^2; the dynamic probe itself
keeps geometry/density/temperature fixed and varies qi/ni only.

## Dynamic synthetic cases

The probes use 1, 2 and 4 synthetic layers with two columns, repeating the ice
operator for two 20-s cycles. Thick geometry is [100,110,120,130] m; thin geometry
is [6,7,8,9] m, truncated to the requested synthetic layer count. Initial qi is
[1e-5,2e-5,4e-6,3e-5], ni [1e4,2e4,3e3,4e4], with rho=0.9, T=260 and denfac=1
prescribed. These are controlled operator inputs, not a new model profile or
certification of thermodynamic/moment consistency. **No real 39-layer data are
remapped.** Other species are inactive; their slope parameters remain defined.

Each cycle selects m once with the existing oracle value-only policy
`clamp(floor(max(rate)*dt+1),1,100)`. Each subsequent consumer recomputes velocity
from updated qi/ni and normalizes once. This composes existing slope/ice
functions, not the full coordinator's main-phase/ProgB/thermodynamic sequence.
The selected divisor is held fixed within that cycle; it is not silently
reselected when velocity changes. At the next cycle a new plan is selected.

| Synthetic layers | Cycle 1 m by column | Cycle 2 m by column | Max consumed dt*rate/m | Max FD relative difference, including velocity trace |
|---|---|---|---:|---:|
| 1 | [1,4] | [1,2] | 0.7502778407 | 1.1426e-9 |
| 2 | [1,4] | [1,2] | 0.7502778407 | 6.9541e-10 |
| 4 | [1,4] | [1,2] | 0.9325182694 | 3.5124e-10 |

There are eight active consumer events per case. Later n>=2 consumers use fresh
state-recomputed velocities. The maximum observed velocity change is about
0.2927205244 m/s (mass) and 0.07318013110 m/s (number); changes are measured
against each column's last **consumed** producer, not an unconsumed batch update.
Columns past their scheduled m keep all state and within-cycle fall arrays
byte-identical even while the other column continues. Normalization itself is
functional and does not update the state. Independent single-column runs also
agree; that cross-batch comparison allows 64 epsilon64 relative error, zero
absolute tolerance, for potentially different transcendental vector kernels.
This does not relax the legacy host raw-bit gate or the within-run byte check.

Fall outputs are accumulated across both equal-duration cycles. Conditional
mass inventory uses rho*dz, number inventory dz, and bottom export is included.
Maximum absolute closure residuals are 8.68e-19 and 1.17e-10 respectively, with
positive bottom export in these synthetic probes. Their positive-inventory
regression checks use 32 epsilon64 relative error and zero absolute tolerance;
this is a gate for these small fixtures, not a universal floating-point bound.
These are kernel-coordinate
budgets; the physical host number basis is still unresolved. They are not a
new native precipitation or number-outflow measurement.

## Differentiation and discrete boundaries

True `torch.func.jvp`, VJP and independent centered differences use nonuniform
relative qi/ni directions and h=1e-3. The same composed slope-to-transport map is
used in all three evaluations: the velocity/rate paths are not frozen or
replaced by hand-coded tangents. Both velocity-change tangents are nonzero.
The maximum normalized dual residual is 2.36e-16. Public results retain the
per-output FD errors, velocity/rate records and input/output states.

The plus/minus states independently reselect the same discrete plans. Observed
ice active/size-limit signatures match, and all three evaluations stay below
outflow-cap activation. This is one direction per case within these checked
branches, not the full Jacobian, all branch crossings or a normalized native
AD/ABI run. Density/geometry directions are tested only for the normalization
identity, not promoted into a full model control.

A separate prescribed-speed counterexample keeps dt=20, dz=25 and initial v=1:
m=1 is selected. Consuming v=3 under that frozen plan gives C=2.4, while a new
selection would give m=3. The result explicitly reports insufficient selected
budget; it does not change scheduling policy to make the case pass. This is a
synthetic diagnostic, not an observed native main-phase speed change.

Integer selection follows executed arithmetic: in binary64, the immediate
predecessor of C=1 rounds to 2 when 1 is added, so the selector returns m=2.
The test distinguishes that from the next lower representable input, which
returns 1. Real-arithmetic floor boundaries must not be substituted for this
executed policy. No derivative across an integer schedule change is claimed.

## Native census: no natural multistep case in the retained window

One additional read-only normalized-mp237 run used the retained 5-km grid,
39 mass layers, dt=20 s and 40-s window, one rank/thread. It recorded selected
initial `mstep_i` for every KDM-owned column at steps 1 and 2. The expected
ownership set was independently defined from the active bounds:

    step in {1,2}, latitude index 2..281, i index 2..233

All **129,920 unique records** (64,960 per step) are present, with no duplicate,
missing or unexpected key. Every selected mstep is 1. This is negative evidence
for this window only: **native n>=2 consumption remains unmeasured**. The census
records selection counts, not every column's raw/consumed velocity or global
Courant bound. The selected input census is not a parallel/halo ownership test.

The complete history matches the retained normalized control, SHA-256
`a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`, at 0,20,40 s.
The capture source strips to the exact normalized source. One initial compile
failed on instrumentation placement and was corrected before the sole native
execution; it is not an additional scientific run. Installed/canonical physics
and historical source pins were not changed.

The full four-integer-per-line census is published as
`native_mstep_census_2026-09-24.txt.gz`, with raw and compressed hashes plus
build/run provenance in the paired JSON. For example, independent completeness
checking does not derive expected keys from the received file:

```python
import gzip
from itertools import product
rows = [tuple(map(int, line.split())) for line in
        gzip.open("harness/evidence/native_mstep_census_2026-09-24.txt.gz", "rt")]
keys = [r[:3] for r in rows]  # step, latitude, i
expected = set(product((1, 2), range(2, 282), range(2, 234)))
assert len(keys) == len(set(keys)) and set(keys) == expected
assert all(r[3] == 1 for r in rows)
```

## Reproduce and remaining scope

Use Python 3.12 with Torch 2.8.0 (matching the oracle CI pin) and NumPy 2.4.6:

```
PYTHONPATH=oracle:harness python3.12 harness/dynamic_ice_probe.py --out /tmp/dynamic-ice.json
python3.12 -m pytest oracle/tests/test_ice_consumption_contract.py oracle/tests/test_dynamic_ice_probe.py -q
```

New focused tests: **15 passed**. The unchanged PR233 normalization and negative
trace tests also pass (**15 existing tests**); the combined local run is 30.
These are distinct from the one native census execution and from the user's
independent generalization-review tests. No new RTTOV run is performed.
The existing liquid-observation approval remains 0/9; no new 0/9 measurement is
claimed for these synthetic or normalized inputs.

G1 now has common contract and dynamic oracle-level evidence. Native n>=2,
full main/reslope coupling, changing geometry, restart/MPI behavior and full
normalized AD/ABI remain open. G2 upstream flux/limiter budgets and generalized
negative-event discovery, G3 physical units/moment contracts, and G4 held-out
meteorological/parallel cases are not completed by this change. Operational P1,
source-pin recertification and independent radiation accuracy remain open.
