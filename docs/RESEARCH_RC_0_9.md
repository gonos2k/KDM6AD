# 0.9 research/regression candidate

**Status: candidate, not a published release.** This first supported path is the
public Python fp64 oracle on CPU: one fixed, mixed-phase, two-cell KDM6 step at
`dt=20 s`, followed by branch-local state JVP/VJP and a central directional
difference. Its purpose is to give a clean checkout one repeatable calculation
and one JSON result. The fixed case is a numerical regression, not a sampled
weather forecast.

Use Python 3.10.11 with PyTorch 2.13.0 on macOS arm64 for this candidate. From
a **clean checkout of the commit being assessed**, create an output directory
outside the checkout and run:

```sh
mkdir -p ../kdm6ad-rc09-result
PYTHONPATH=oracle OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 oracle/scripts/rc09_regression.py \
  --output ../kdm6ad-rc09-result/result.json
```

The output path must be new. The command exits 0 only when all 12 forward
fields agree with the pinned [reference](../oracle/scripts/rc09_reference.json)
within its declared `atol`/`rtol`, the state and derivatives are finite,
JVP–VJP duality has relative error below `1e-12`, and the selected
smooth-direction central difference has relative error below `1e-6`. The JSON
records the source commit, entrypoint/runtime/reference hashes, environment
versions, 12 output state fields, and measured residuals. A failed calculation
exits nonzero and writes `status: FAIL` with provenance; an existing output
path also fails rather than being overwritten. A dirty checkout or a different
Python/PyTorch/OS/architecture is rejected.

For a candidate commit, run its existing focused regression suite in that same
checkout and environment:

```sh
PYTHONPATH=oracle python3 -m pytest -q \
  oracle/tests/test_handle_vjp_jvp.py oracle/tests/test_runtime_validation.py \
  oracle/tests/test_rc09_regression.py
```

These are **numerical implementation checks**. The candidate does not run a
private host, RTTOV, a GK2A observation, a forecast cycle, or a C++ ABI build.
`observation: NOT_EVALUATED` in the JSON is intentional; it is not a zero-cost
observation validation. The branch-local fp64 derivative is not the literal
adjoint of operational f32, and neither unit consistency nor physical accuracy
across unsupported states is approved by this example. See
[capability status](STATUS.md), [science status](../harness/evidence/SCIENCE_STATUS.md),
and [operational readiness](OPERATIONAL_READINESS.md) for those separate gates.

Before publishing a 0.9 release, a second clean checkout must reproduce the
command and focused suite at the **same commit**, with the JSON and test log
retained. Packaging and redistribution also require an owner-approved license:
the repository currently has no `LICENSE`, and `CITATION.cff` marks licensing
as pending. No GitHub release or operating-host approval is implied here.
