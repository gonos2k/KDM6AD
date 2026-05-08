# KDM6 AD — Differentiable KDM6 Microphysics

**Goal**: KIM-meso v1.0의 KDM6 cloud microphysics를 PyTorch/libtorch comp-graph AD로
재구현하고, 현재 KIM-meso 통합 경로에서는 canonical `mp_physics==137` KDM6AD slot으로
호출한다. Jacobian/JVP/VJP 및 4D-Var 결합은 G4 이후 범위다.

원본 Fortran: `/Users/yhlee/KIM-meso1/KIM-meso_v1.0/phys/module_mp_kdm6.F`
(~4281 라인, `kdm62D` 본체 2630 라인).

## Status (2026-04-29)

| Track | State |
|---|---|
| **Python oracle** | 215/215 PASS — codex review #10 GREEN; F1e (Fortran 2680-3082) closure |
| **Parity harness** | 6/6 PASS — local/synthetic 11-field self-test exact round-trip; excludes NCCN/QNN |
| **C++ libtorch** | 10/10 ctest — codex review #12 GREEN; post-update + state_update mirrored |
| Open: KIM-meso golden vector capture | user-side; harness ready |
| Open: full source>value rate limiter (Task #67) | deferred until golden vector |
| Open: pcact/ncact + nccn prognostic (Task #74) | KIM-meso wrapper scope |
| Open: C++ per-phase orchestration | optional convenience |

## Layout

```text
KDM6AD/
├── kdm6_torch/         # Python oracle (reference implementation)
│   ├── kdm6/           # microphysics modules + coordinator
│   └── tests/          # 215 regression tests
├── kdm6_libtorch/      # C++ libtorch port
│   ├── include/kdm6/   # public headers
│   ├── src/            # implementations
│   ├── tests/          # ctest binaries
│   └── build/          # cmake out-of-source
├── parity/             # Fortran parity harness
│   ├── _schema.py      # golden-vector schema
│   ├── run_parity.py   # CLI: oracle vs golden diff
│   ├── build_self_test_vector.py
│   ├── golden/<name>/  # golden-vector store
│   └── snippets/capture.F90.txt
└── KIM-meso_v1.0/      # host model integration tree
```

## Run all test suites

```bash
# Python oracle
cd kdm6_torch && PYTHONPATH=. python -m pytest tests/ -q

# Parity harness
PYTHONPATH=kdm6_torch python -m pytest parity/ -q

# C++ libtorch
cd kdm6_libtorch/build && ctest

# Self-test golden vector
PYTHONPATH=kdm6_torch python parity/build_self_test_vector.py
PYTHONPATH=kdm6_torch python parity/run_parity.py parity/golden/self_test
```

Expected: schema fields for the synthetic self-test should round-trip exactly. This is not NCCN/QNN parity and not KIM-meso slot 37↔137 operational forward parity.

## Capture a golden vector from KIM-meso

When ready to verify Python-vs-Fortran parity, drop the snippet at
`parity/snippets/capture.F90.txt` into `module_mp_kdm6.F` around a representative
`kdm62D` call. Then:

```bash
PYTHONPATH=kdm6_torch python parity/import_fortran.py \
    kdm6_parity_in.bin kdm6_parity_out.bin \
    --out parity/golden/<name> \
    --test-name "<descriptive label>" \
    --kim-version <build id>

PYTHONPATH=kdm6_torch python parity/run_parity.py parity/golden/<name>
```

The auxdiag contract currently re-derives diagnostic fields from `state_in + forcing` using scalar defaults. A Fortran capture must either match these defaults or extend the schema with explicit auxdiag fields.
