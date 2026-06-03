"""C++ kdm6_fn  ↔  Python _kdm6_pure  numeric parity (the project's load-bearing invariant).

Previously the headline parity figures (standard-IC 5.09e-14, rain-evap 4.53e-15, ...) were
only PRINTED by the C++ end-to-end test (CPPOUT/RCEOUT/NCCNOUT/COLDOUT dumps) and compared by
hand — no committed test asserted them, so a one-sided regression in EITHER tree would pass
both `pytest -q` and `ctest` silently (adversarial-audit finding, dim=test-efficacy).

This test closes that hole: it runs the real C++ test binary as a subprocess (OMP-isolated),
parses its live dumps, runs the Python oracle `_kdm6_pure` on the SAME initial conditions, and
asserts machine-precision agreement. No stale golden file — the C++ side is the live binary.

The ICs below MUST stay in lockstep with the dump blocks in
kdm6_libtorch/tests/test_autograd_endtoend.cpp (CPPOUT=g_base dt=300, RCEOUT dt=120,
NCCNOUT dt=600, COLDOUT dt=120). If you change one, change both.

ICs are deliberately well-conditioned (away from the complete-sublimation-cap knife-edge at
qi~4e-5/ni~O(0.01) — a documented precision-chaos discontinuity where the two trees can
legitimately diverge by O(1); see lessons / wiki). Do NOT randomize the ICs here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import torch

_REPO = Path(__file__).resolve().parents[2]
_BIN = _REPO / "kdm6_libtorch" / "build_miniforge" / "test_autograd_endtoend"

# (state cell0, state cell1) per field — matches the C++ dump blocks exactly.
_G_BASE = dict(
    th=(296.8, 282.4), qv=(1.40e-2, 2.0e-3), qc=(1.0e-3, 5.0e-4), qr=(1.0e-4, 1.0e-5),
    qi=(0.0, 1.0e-4), qs=(0.0, 5.0e-5), qg=(0.0, 1.0e-5), nccn=(1.0e9, 1.0e9),
    nc=(1.0e8, 1.0e8), ni=(0.0, 1.0e4), nr=(1.0e4, 1.0e3), bg=(0.0, 0.0),
)
_G_BASE_F = dict(rho=(1.089, 0.9567), pii=(0.9704, 0.9031), p=(9.0e4, 7.0e4), delz=(500.0, 500.0))

# uniform 2-cell ICs (both cells identical) — only cell 0 is dumped/compared.
def _uni(**kw):
    return {k: (v, v) for k, v in kw.items()}

_RCE = _uni(th=300.0, qv=2.0e-3, qc=0.0, qr=5.0e-6, qi=0.0, qs=0.0, qg=0.0,
            nccn=1.0e9, nc=0.0, ni=0.0, nr=1.0e4, bg=0.0)
_RCE_F = _uni(rho=1.0, pii=0.97, p=9.0e4, delz=500.0)

_NCCN = _uni(th=296.8, qv=1.5e-2, qc=1.0e-3, qr=0.0, qi=0.0, qs=0.0, qg=0.0,
             nccn=1.95e10, nc=5.0e7, ni=0.0, nr=0.0, bg=0.0)
_NCCN_F = _uni(rho=1.089, pii=0.9704, p=9.0e4, delz=500.0)

_COLD = _uni(th=258.0, qv=2.0e-3, qc=5.0e-4, qr=1.0e-5, qi=1.0e-4, qs=5.0e-5, qg=1.0e-5,
             nccn=1.0e9, nc=1.0e8, ni=1.0e4, nr=1.0e3, bg=0.0)
_COLD_F = _uni(rho=0.9567, pii=0.9031, p=7.0e4, delz=500.0)

# tag -> (state, forcing, dt, ncells_compared)
_CASES = {
    "CPPOUT": (_G_BASE, _G_BASE_F, 300.0, 2),
    "RCEOUT": (_RCE, _RCE_F, 120.0, 1),
    "NCCNOUT": (_NCCN, _NCCN_F, 600.0, 1),
    "COLDOUT": (_COLD, _COLD_F, 120.0, 1),
}


def _run_cpp_dumps() -> dict:
    """Run the C++ end-to-end binary, return {TAG: {field: [v0(,v1)]}}."""
    env = {**os.environ, "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    proc = subprocess.run([str(_BIN)], capture_output=True, text=True, env=env, timeout=300)
    dumps: dict = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in _CASES:
            tag, field = parts[0], parts[1]
            dumps.setdefault(tag, {})[field] = [float(x) for x in parts[2:]]
    return dumps


def _py_step(state: dict, forcing: dict, dt: float):
    from kdm6.state import State, Forcing
    from kdm6.runtime import _kdm6_pure, make_parameters

    def t2(pair):
        return torch.tensor([[pair[0], pair[1]]], dtype=torch.float64)

    s = State(**{k: t2(v) for k, v in state.items()})
    f = Forcing(**{k: t2(v) for k, v in forcing.items()})
    return _kdm6_pure(s, f, make_parameters(), dt=dt)


@pytest.mark.skipif(not _BIN.exists(), reason="C++ test_autograd_endtoend not built")
def test_cpp_python_forward_parity():
    """Every dumped field of every IC must match _kdm6_pure to fp64 machine precision."""
    dumps = _run_cpp_dumps()
    assert dumps, "no parity dumps parsed from the C++ binary output"
    worst = 0.0
    worst_where = ""
    with torch.no_grad():  # value comparison only — keep .item() off any live graph
        for tag, (state, forcing, dt, ncols) in _CASES.items():
            assert tag in dumps, f"C++ binary did not emit {tag}"
            out = _py_step(state, forcing, dt)
            for field, cpp_vals in dumps[tag].items():
                py = getattr(out, field).reshape(-1)
                for i in range(ncols):
                    c = cpp_vals[i]
                    p = py[i].item()
                    rel = abs(p - c) / (abs(c) if abs(c) > 0 else 1.0)
                    if rel > worst:
                        worst, worst_where = rel, f"{tag}.{field}[{i}] py={p:.15g} cpp={c:.15g}"
    assert worst < 1e-10, f"C++↔Python parity broke: worst relΔ={worst:.3e} at {worst_where}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
