# ORACLE KDM6 GUIDE

Scope: Python f64 reference implementation and oracle tests for KDM6/KDM6AD.

## Overview

`oracle/` is not in the WRF runtime. It is the Python/PyTorch reference used to
explain the scheme, verify C++ behavior, and protect AD graph contracts.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Main step | `kdm6/runtime.py` | `_kdm6_pure`, `kdm6_step`, handle logic |
| Phase coordination | `kdm6/coordinator.py` | warm/cold/melt-freeze orchestration |
| State layout | `kdm6/state.py` | `State`, `Forcing`, tensor cloning |
| Process modules | `kdm6/{warm,cold,satadj,sedimentation,...}.py` | phase kernels |
| Windowed AD | `kdm6/da_window.py` | detached checkpoints and VJP loop |
| RTTOV/obs path | `kdm6/obs/` | observation operator and profile builder |
| C++ parity | `tests/test_cpp_parity.py` | compares live C++ dumps against Python |
| AD regression | `tests/test_da_window.py`, `tests/test_handle_vjp_jvp.py` | graph integrity |

## Conventions

- Treat Python as the semantic oracle, not the operational runtime.
- Preserve f64 reference behavior unless a change is explicitly about f32
  Fortran parity emulation.
- Keep comments that describe Fortran line classes, f32 stepwise constants, and
  branch order; they are regression evidence.
- `detach`, `.item()`, and `torch.no_grad()` are allowed only in explicit
  value-only gates, checkpoint boundaries, or test setup.
- A `None` gradient in cloud/obs paths can mean structural severance; investigate
  before accepting it.

## Anti-Patterns

- Do not rewrite oracle code to match C++ convenience if it loses explanatory
  parity with Fortran.
- Do not hide graph breaks behind `no_grad` or detached numpy conversions.
- Do not weaken pytest expectations to pass around a C++ parity failure.
- Do not treat old planning text in `README.md` as more authoritative than the
  current tests and source files.

## Commands

```bash
cd /Users/yhlee/KDM6AD-k/oracle
python3 -m pytest
python3 -m pytest tests/test_cpp_parity.py
python3 -m pytest tests/test_da_window.py tests/test_handle_vjp_jvp.py
```
