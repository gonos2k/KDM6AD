# KDM6 Parity Harness

Reference-vector–driven regression test for the Python/libtorch oracle vs. the
authoritative Fortran `kdm62D` (`module_mp_kdm6.F`) 11-field microphysics state.
It is not a full KIM-meso wrapper reproducibility proof.

## Why this exists

After the codex review #2 fixes (codex#1-#4), the F1e mass-balance and dT
formulas are believed Fortran-faithful but **not yet verified end-to-end**.
The codex report stated: "F4/G 진행 위해 필수". This harness is the gate
between **Stage F (oracle complete)** and **Stage G (KIM-meso integration)**.

## Three-tier strategy

| Tier | Description | When to use |
|---|---|---|
| **T3 (this dir)** | Golden-vector files captured from a KIM-meso run. Python oracle runs the same input, asserts close match. | Now — no Fortran build needed in this session. |
| T2 | Extracted per-step F90 subroutines (e.g. just `ProgB_param`, just slope, ...). Driver calls each, dumps intermediate state. | After T3 establishes confidence; pinpoints which step has drift. |
| T1 | Full standalone driver that links `module_mp_kdm6.o` and KIM-meso build libs, calls `kdm62D` directly. | Final integration verification before slot-137 wiring. |

Right now we ship T3 only.

## Golden-vector format

Each `.npz` file under `golden/` represents a single Fortran call snapshot:

```
input/
  state            # dict of (B, K) tensors — qv, qc, qr, qs, qg, qi, nc, nr, ni, brs, t
  forcing          # dict — p, den, delz, dend
  scalars          # dict — dtcld, ccn0, qmin, ...
output/
  state_new        # state *after* one kdm62D call (pre-sedimentation)
  surface_accum    # rain/snow/graupel mm increments (post-sedimentation only)
metadata/
  kim_version      # KIM-meso build identifier
  fortran_commit   # module_mp_kdm6.F commit hash if known
  capture_date     # ISO-8601
  test_name        # short label (e.g. 'cold_column_warm_advect')
```

Schema is enforced by `parity/_schema.py`.

### Excluded from the current T3 schema

The current golden-vector schema intentionally excludes `NCCN`/`QNN`/`NN`.
Those fields are wrapper-level KIM-meso state in the current libtorch ABI, while
this harness compares the 11 microphysics-level `CoordinatorState` fields above.
Do not interpret a passing T3 vector as `NCCN/QNN` parity evidence; that requires
a future schema/capture extension or a separate wrapper-level test.

## How to capture a golden vector (Fortran side)

The `kdm62D` subroutine is `inout` on `t, q, qci, qrs, nci, nrs, brs` and
`out` on `rhox`. To capture a vector:

1. Pick a small `(its:ite, kts:kte) = (1:1, 1:K)` column in your KIM-meso run.
2. Just before calling `kdm62D`, snapshot the input state.
3. After the call (still before sedimentation if possible), snapshot output.
4. Write both as Fortran direct-access binary or unformatted; the
   `parity/import_fortran.py` tool converts to `.npz`.

A reference Fortran snippet is included in `parity/snippets/capture.F90.txt`
(template, not compiled here).

## How to run parity (Python side)

```bash
cd /Users/yhlee/KDM6AD/kdm6_torch
PYTHONPATH=. python ../parity/run_parity.py ../parity/golden/<name>.npz
```

Exit code 0 ⟺ all fields within `atol=1e-6, rtol=1e-5`. Field-by-field
diff dumped to stdout.

`pytest`-style integration:

```bash
PYTHONPATH=. python -m pytest ../parity/test_parity.py -v
```

`test_parity.py` discovers all `golden/*.npz` and parametrises one test
per file.

## Status

- [x] Harness scaffold (this dir)
- [x] **Pipeline operational** — `run_parity.py` runs `kdm62d_one_step_torch` end-to-end
      and produces field-by-field diffs. auxdiag is computed from `state_in + forcing`.
- [x] **Self-test verified** — `parity/build_self_test_vector.py` generates a synthetic
      golden from the Python oracle; round-trip parity is exact (atol=rtol=0). When the
      first Fortran golden lands, only the data source changes.
- [x] **`_build_aux` independently regression-tested** — `qcr`, `rslopecmu`, `rslopecd`,
      shape/dtype contract verified against public-API expected values, NOT against
      `_build_aux` itself. Prevents self-test from masking aux bugs.
- [x] **Per-field diagnostics** — `max|Δ| @ [B,K]`, RMS, in-tolerance fraction.
- [ ] First golden vector captured from KIM-meso
- [ ] Per-step breakdown (warm/cold/freeze/sed) — useful when real Fortran fails
- [ ] CI integration

## auxdiag contract (review11#1) — IMPORTANT for parity correctness

`run_parity.py` *re-derives* `CoordinatorAuxDiagnostics` from `state_in + forcing`
inside the harness using `_build_aux`. **Default scalar values** (n0r=8e6, n0i=1e6,
n0c=1e8, n0so=2e6, n0go=4e6, work1_*=1e-3, avedia_i=1e-4) are baked in.
The current schema does not consume captured operational auxdiag arrays.

When you capture a Fortran golden vector for parity comparison, **the Fortran-side
caller must use the same default values for these auxdiag inputs.** If the operational
KIM-meso wrapper diagnoses different `n0r/n0i/...` (e.g. land/sea-aware, density-aware),
running our harness against that capture will report drift that is *wrapper*
disagreement, not oracle disagreement.

Two ways to handle this:
1. **Match harness defaults**: temporarily patch the Fortran call to use the harness's
   default scalars during capture. Cleanest for first-pass 11-field parity; isolates
   oracle-vs-Fortran from wrapper-vs-harness for fields currently in the schema.
2. **Capture auxdiag explicitly**: extend the golden vector schema to carry n0r/n0i/...
   from Fortran. Requires schema bump and Fortran-side capture additions.

We currently use approach (1). When approach (2) is needed, see
`_schema.py` to add an `auxdiag` block, then thread it through `run_parity._build_aux`.

## Self-test scope (review11#3)

`pytest parity/test_parity.py::test_golden_vector_parity[self_test]` enforces
`atol=rtol=0`. This **is not** a cross-platform stability claim — same torch /
device / dtype path is assumed. CPU↔GPU runs, or torch version changes that perturb
floating-point op ordering, may need a small relaxation. The test catches:

- oracle nondeterminism (any random init or mutable global)
- `_build_aux` self-consistency (build vs verify must produce identical aux)
- chain ordering changes
- save/load schema drift

## Quick start

Generate the self-test vector and verify the pipeline:

```bash
PYTHONPATH=kdm6_torch python parity/build_self_test_vector.py
PYTHONPATH=kdm6_torch python parity/run_parity.py parity/golden/self_test
# 11/11 fields PASS with max|Δ|=0
```

Once you have a Fortran-captured vector at `parity/golden/<name>/`:

```bash
PYTHONPATH=kdm6_torch python parity/run_parity.py parity/golden/<name>
# Field-by-field diffs printed; exit 0 ⟺ all within tolerance
```

`pytest` integration also picks up every `golden/<dir>/`:

```bash
PYTHONPATH=kdm6_torch python -m pytest parity/test_parity.py -v
```

## Connections

- 7-step plan: F3'' (`wiki/procedures/kdm62d-port-decomposition.md`)
- codex review: #2 priority recommendation #5
- See also: `wiki/log.md` 2026-04-28 entry
