# NCCN return: direct, zero-only and hybrid comparison

Baseline main: PR #350, `f9493de`. Main's runtime and user command are unchanged.
The [N4–N6 follow-up](CHECKLIST_pr349_followup_2026-10-01.md) continues the existing
checklist without new system gates or deployment work.

## Selected next experiment

Prefer the **exact-zero-only, live-delta** candidate for the next isolated native
probe. It preserves the observed identity and uses direct division at every
representably nonzero change. The 50% switch is removed. This is not a production
selection or a claim of a smooth floating map; N5 native evidence remains open.

```
N_in = rho_d * n_in              # captured live before kernel updates
Delta = N_out - N_in
n_out = where(Delta == 0, n_in + Delta/rho_d, N_out/rho_d)
```

The `Delta/rho_d` term in the zero branch is essential: if Delta is zero by value
but its directional derivative is nonzero, selecting bare `n_in` erases that
process sensitivity. No detach, scalar extraction or special custom gradient is
used. The [isolated patch](../nccn_zero_return_candidate.patch) changes only the
opt-in dry-number fp64 NCCN return in Python/C++; f32 and NC/NI/NR are unchanged.
The candidate source is a clean local commit `915c5b9`, reproduced by applying
the patch to `f9493de`; it is not adopted main source.

## Observed comparison

All comparisons keep the retained input-selected column `(3,272)`, frame 1,
39 levels, selector 2/dry-number 1, existing direction, h=1e-4 and thresholds.
They do not reinterpret the production baseline failure as a pass.

| Return | Retained identity case | Synthetic nonzero CCN kernel FD relative | Extra arithmetic selection |
| --- | --- | --- | --- |
| Direct | FAIL, NCCN 1-ULP endpoint difference | 5.1727954596456055e-11 | none |
| 50% hybrid | bounded PASS | 7.706421323359222e-11 | abs(Delta) <= 0.5 abs(N_in) |
| Zero-only live delta | bounded PASS | 5.1727954596456055e-11 | Delta == 0 |

The [three-way active probe](nccn_return_three_way_active_2026-10-02.json) uses the
same declared synthetic warm-column inputs and real C ABI kernel updates. The
zero-only case's nonzero output changes, FD and duality match the direct case.
The ratio 1.4898 between the hybrid/direct FD errors is not a general accuracy
ranking; both errors are small in that one case.

The [actual zero-only run](nccn_zero_return_runs_2026-10-02.json) passes all 12
field gates, graph/value equality and duality 1.7898e-16. NCCN FD and JVP are
zero; the other 11 forward arrays are raw-identical to the preserved baseline.
The [saved NPZ](nccn_zero_return_passed_2026-10-02.npz) contains the actual
snapshot inputs, direction, endpoints and AD outputs. Existing PR #350 baseline
failure and hybrid pass artifacts remain preserved.

## Limits that remain

Value equality is not structural inactivity. In the actual cloud satadj
consumer, qc=0 and pcond=0 trigger the bare complete-evaporation gate. At NC=0
the transferred value is zero, yet the selected nonnegative-clamp tangent to
NCCN is live. A focused Python-oracle consumer test verifies JVP/VJP and a
one-sided consumer clamp-direction check; the zero-only return preserves it and a bare
identity bypass returns an incorrect zero tangent. This boundary-direction test
is not certification of an arbitrary NC-only full atmospheric/DSD state.
The C++ candidate has source parity and the bounded full-kernel probes, but
this structural-zero NC boundary is not yet an executed C ABI test.

Zero-only return also retains floating quantization at neighboring nonzero
amounts. A declared scalar case returns n at Delta=0, n minus 1 ULP at the lower
neighbor, and n plus 2 ULP at the upper neighbor. This is recorded explicitly;
the case is a scalar boundary example, not an admitted native CCN state. The
candidate therefore removes the arbitrary half-change threshold, **not all
floating discontinuity or FD noise**. It is not a measured structural-zero
process ledger. Unresolved process branches/clamp behavior remain separate.

Complete/near removal arithmetic stays exactly direct when Delta != 0. Those
raw boundary tests are not claims that the full kernel bypasses its NCCN minimum
reservoir clamp. No return change is generalized to NC, NI or NR.

## Executed checks and reproduction

Local: 17 return/consumer tests, 9 existing patched-oracle/runtime/runner tests,
and 1 fresh C ABI test. This is bounded algorithm verification, not a new full
host or RTTOV experiment. Graphify's original cached graph lacked this return
path; source was checked directly, then changed code/doc links were refreshed.

```sh
PYTHONPATH=oracle python3 -m pytest -q \
  oracle/tests/test_nccn_return_candidate.py \
  oracle/tests/test_nccn_zero_process_return.py
```

Build the patch only in a separate checkout/build directory with the existing
Torch CMake setup, then use the unchanged
[external-path column command](../../docs/NORMALIZED_DRY_COLUMN.md). Identify the
candidate by patch/library hashes; selector and dry-number options alone do not
identify its return arithmetic. The local build uses AppleClang 21, Release,
`-ffp-contract=off`; local Python/Torch are 3.10.11/2.13.0. No deployment or
operational install is changed. N5 will record the actual native-staged probe
and its own independent FD result; that result is not inferred from this pass.
