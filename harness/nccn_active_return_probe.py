"""Focused synthetic warm-column probe for the isolated NCCN return patch.

This exercises real kernel updates on declared synthetic inputs; it is not a
native weather case or an observation test. Call probe(library) from Python.
"""
import ctypes
import importlib.util
from pathlib import Path

import numpy as np

_RUNNER = Path(__file__).resolve().parents[1] / "oracle/scripts/run_normalized_dry_column.py"
_spec = importlib.util.spec_from_file_location("column_runner", _RUNNER)
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)


def probe(library):
    state = np.repeat(np.array([
        290., .004, .001, .0001, 0., 0., 0., 1e9, 1e8, 0., 1e4, 0.
    ], dtype=np.float64)[:, None], 3, axis=1)
    forcing = np.repeat(np.array([1., .97, 9e4, 500.])[:, None], 3, axis=1)
    direction = np.zeros_like(state)
    direction[1] = .01 * state[1]
    direction[7] = .01 * state[7]
    direction[8] = .01 * state[8]
    lib = _runner.load_library(library)
    output, handle = _runner.step(lib, state, forcing, 2., False)
    pointer = ctypes.POINTER(ctypes.c_double)
    seed = np.zeros_like(state)
    seed[7] = (1., -2., 3.)
    jvp, vjp = np.empty_like(state), np.empty_like(state)
    try:
        _runner.check_call(lib.kdm6_handle_jvp_c(handle,
            direction.ctypes.data_as(pointer), jvp.ctypes.data_as(pointer)), "JVP")
        _runner.check_call(lib.kdm6_handle_vjp_c(handle,
            seed.ctypes.data_as(pointer), vjp.ctypes.data_as(pointer)), "VJP")
    finally:
        _runner.check_call(lib.kdm6_handle_closep_c(ctypes.byref(handle)), "close")
    h = _runner.CONFIG["finite_difference_width"]
    plus, _ = _runner.step(lib, state + h * direction, forcing, 2., True)
    minus, _ = _runner.step(lib, state - h * direction, forcing, 2., True)
    fd = (plus - minus) / (2 * h)
    error = np.max(abs(jvp[7] - fd[7])) / max(np.max(abs(jvp[7])), np.max(abs(fd[7])))
    lhs, rhs = np.sum(seed * jvp), np.sum(direction * vjp)
    duality = abs(lhs - rhs) / max(abs(lhs), abs(rhs))
    finite = all(np.isfinite(a).all() for a in (
        state, forcing, direction, seed, output, jvp, vjp, plus, minus, fd,
        np.array([error, lhs, rhs, duality]),
    ))
    changed = bool(np.all(output[7] != state[7]))
    return dict(input_kind="synthetic warm three-layer column", library_sha256=_runner.sha256(library),
        configuration=_runner.CONFIG, state=state.tolist(), forcing=forcing.tolist(),
        direction=direction.tolist(), covector=seed.tolist(), nccn_output=output[7].tolist(),
        nccn_applied_dry_change=(output[7] - state[7]).tolist(),
        nccn_jvp=jvp[7].tolist(), nccn_fd=fd[7].tolist(),
        finite=finite, nonzero_applied_change=changed, fd_relative=float(error),
        duality_relative=float(duality),
        passed=bool(finite and changed and error <= 1e-5 and duality <= 1e-12))
