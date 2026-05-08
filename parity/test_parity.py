"""pytest discovery wrapper for golden-vector parity tests.

Each `golden/<name>/` subdirectory becomes one parametrised test. The test
loads the vector, runs the Python oracle on the same input, and asserts
state fields match within tolerance.

The harness pipeline is fully wired (review10 follow-up). The `self_test`
golden vector is generated from the Python oracle itself — it must round-trip
exactly. Real Fortran-captured vectors will reveal Python-vs-Fortran drift
within the configured tolerance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve().parent
_PROJ = _THIS.parent
sys.path.insert(0, str(_THIS))
sys.path.insert(0, str(_PROJ / "kdm6_torch"))

from _schema import (
    SCHEMA_EXCLUDED_FIELDS,
    StateFields,
    ForcingFields,
    load as load_golden,
    save as save_golden,
)  # noqa: E402
from run_parity import run_parity  # noqa: E402


def test_parity_schema_excludes_wrapper_nccn_qnn_contract():
    """Current T3 parity schema excludes wrapper-level NCCN/QNN/NN."""
    excluded_lower = {name.lower() for name in SCHEMA_EXCLUDED_FIELDS}
    assert {"nccn", "qnn", "nn"}.issubset(excluded_lower)

    state_fields = {name.lower() for name in StateFields._fields}
    forcing_fields = {name.lower() for name in ForcingFields._fields}
    assert state_fields.isdisjoint(excluded_lower)
    assert forcing_fields.isdisjoint(excluded_lower)


def _golden_dirs() -> list[Path]:
    root = _THIS / "golden"
    return sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []


@pytest.mark.parametrize("golden_dir", _golden_dirs())
def test_golden_vector_loads(golden_dir: Path):
    """Schema validation only."""
    g = load_golden(golden_dir)
    K = g.state_in.qv.shape[-1]
    assert g.state_out.qv.shape[-1] == K, "state_in/state_out K-dim must match"
    assert g.scalars["dtcld"] > 0


@pytest.mark.parametrize("golden_dir", _golden_dirs())
def test_golden_vector_parity(golden_dir: Path):
    """Full pipeline: load vector, run Python oracle, compare to state_out.

    For `self_test` (Python-self-generated): demands exact equality (atol=rtol=0).
    For real Fortran vectors: relax to atol=1e-6, rtol=1e-5.
    """
    name = golden_dir.name
    if name == "self_test":
        atol, rtol = 0.0, 0.0
    else:
        atol, rtol = 1e-6, 1e-5
    all_pass, summary = run_parity(golden_dir, atol=atol, rtol=rtol)
    if not all_pass:
        msg = f"parity FAIL for {name}\n" + "\n".join(summary)
        pytest.fail(msg)


# ─── review11#4: independent _build_aux validation ────────────────────────────
#
# self-test reuses _build_aux for both vector creation AND verification, so an
# auxdiag bug would silently round-trip. The tests below pin _build_aux outputs
# against values computed *without* calling _build_aux internals — pure expected
# values from the public API + Γ-truth + cloud_dsd diag.


def test_build_aux_qcr_matches_diag_qcr():
    """qcr field in _build_aux must equal diag_qcr_torch(sea_mask, params, ref).

    If _build_aux ever swaps in a wrong qcr formula, this test fails immediately.
    """
    import torch
    from kdm6 import coordinator as _coord
    from kdm6.cloud_dsd import diag_qcr_torch

    sys.path.insert(0, str(_THIS))
    from run_parity import _build_aux

    dtype = torch.float64
    B, K = 2, 3
    state = _coord.CoordinatorState(
        qv=torch.full((B, K), 8e-3, dtype=dtype),
        qc=torch.full((B, K), 5e-4, dtype=dtype),
        qr=torch.full((B, K), 1e-4, dtype=dtype),
        qs=torch.full((B, K), 1e-5, dtype=dtype),
        qg=torch.full((B, K), 1e-5, dtype=dtype),
        qi=torch.full((B, K), 1e-5, dtype=dtype),
        nc=torch.full((B, K), 1e8, dtype=dtype),
        nr=torch.full((B, K), 1e5, dtype=dtype),
        ni=torch.full((B, K), 1e6, dtype=dtype),
        brs=torch.zeros((B, K), dtype=dtype),
        t=torch.full((B, K), 270.0, dtype=dtype),
    )
    forcing = _coord.CoordinatorForcing(
        p=torch.full((B, K), 8e4, dtype=dtype),
        den=torch.full((B, K), 1.1, dtype=dtype),
        delz=torch.full((B, K), 500.0, dtype=dtype),
        dend=torch.full((B, K), 1.1 * 500.0, dtype=dtype),
    )
    sea_mask = torch.tensor([[True] * K, [False] * K])

    params = _coord.default_coordinator_params()
    aux = _build_aux(state, forcing, sea_mask, params)

    # Independent reference: directly call public diag_qcr_torch.
    expected_qcr = diag_qcr_torch(sea_mask, params=params.cloud_dsd, ref=state.qc)
    assert torch.allclose(aux.qcr, expected_qcr, atol=0, rtol=0), (
        "aux.qcr drifted from diag_qcr_torch(sea_mask, ...) — _build_aux helper bug"
    )
    # Sea row should equal qc1, land row should equal qc0.
    assert torch.allclose(aux.qcr[0], torch.full((K,), params.cloud_dsd.qc1, dtype=dtype))
    assert torch.allclose(aux.qcr[1], torch.full((K,), params.cloud_dsd.qc0, dtype=dtype))


def test_build_aux_rslopecmu_rslopecd_match_preamble():
    """rslopecmu = rslopec**MUC, rslopecd = rslopec**DMC. Preamble로부터 독립 산출."""
    import torch
    from kdm6 import constants as c
    from kdm6 import coordinator as _coord

    sys.path.insert(0, str(_THIS))
    from run_parity import _build_aux

    dtype = torch.float64
    B, K = 1, 2
    state = _coord.CoordinatorState(
        qv=torch.full((B, K), 8e-3, dtype=dtype),
        qc=torch.full((B, K), 5e-4, dtype=dtype),
        qr=torch.full((B, K), 1e-4, dtype=dtype),
        qs=torch.full((B, K), 1e-5, dtype=dtype),
        qg=torch.full((B, K), 1e-5, dtype=dtype),
        qi=torch.full((B, K), 1e-5, dtype=dtype),
        nc=torch.full((B, K), 1e8, dtype=dtype),
        nr=torch.full((B, K), 1e5, dtype=dtype),
        ni=torch.full((B, K), 1e6, dtype=dtype),
        brs=torch.zeros((B, K), dtype=dtype),
        t=torch.full((B, K), 270.0, dtype=dtype),
    )
    forcing = _coord.CoordinatorForcing(
        p=torch.full((B, K), 8e4, dtype=dtype),
        den=torch.full((B, K), 1.1, dtype=dtype),
        delz=torch.full((B, K), 500.0, dtype=dtype),
        dend=torch.full((B, K), 1.1 * 500.0, dtype=dtype),
    )
    sea_mask = torch.ones((B, K), dtype=torch.bool)
    params = _coord.default_coordinator_params()

    aux = _build_aux(state, forcing, sea_mask, params)
    pre = _coord.preamble_torch(state, forcing, sea_mask, params=params)

    expected_cmu = pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    expected_cd = pre.rslopec ** c.DMC
    assert torch.allclose(aux.rslopecmu, expected_cmu, atol=0, rtol=0)
    assert torch.allclose(aux.rslopecd, expected_cd, atol=0, rtol=0)


# review13#2: Python-vs-C++ symbol parity check as a regression test.
# Runs symbol_parity.py in strict mode. Catches the "function entirely missing"
# bug class that LLM review can't see (Task #86 graupel_evap was missing for
# weeks before discovery).


def test_python_cpp_symbol_parity():
    """`*_torch` Python 함수 ↔ C++ exported symbol parity (suffix fungible).

    EXPECTED_MISSING allowlist 외의 Python-only 함수가 발견되면 fail.
    포팅 완료 시 entry를 allowlist에서 제거.
    """
    import subprocess
    result = subprocess.run(
        [sys.executable, str(_THIS / "symbol_parity.py"), "--strict"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "Python ↔ C++ symbol parity violated:\n"
            + result.stdout + "\n"
            + result.stderr
        )


def test_build_aux_shape_dtype_contract():
    """Every aux field has shape (B, K) and dtype matching state.qc."""
    import torch
    from kdm6 import coordinator as _coord

    sys.path.insert(0, str(_THIS))
    from run_parity import _build_aux

    dtype = torch.float64
    B, K = 1, 4
    state = _coord.CoordinatorState(
        qv=torch.full((B, K), 8e-3, dtype=dtype),
        qc=torch.full((B, K), 5e-4, dtype=dtype),
        qr=torch.full((B, K), 1e-4, dtype=dtype),
        qs=torch.full((B, K), 1e-5, dtype=dtype),
        qg=torch.full((B, K), 1e-5, dtype=dtype),
        qi=torch.full((B, K), 1e-5, dtype=dtype),
        nc=torch.full((B, K), 1e8, dtype=dtype),
        nr=torch.full((B, K), 1e5, dtype=dtype),
        ni=torch.full((B, K), 1e6, dtype=dtype),
        brs=torch.zeros((B, K), dtype=dtype),
        t=torch.full((B, K), 270.0, dtype=dtype),
    )
    forcing = _coord.CoordinatorForcing(
        p=torch.full((B, K), 8e4, dtype=dtype),
        den=torch.full((B, K), 1.1, dtype=dtype),
        delz=torch.full((B, K), 500.0, dtype=dtype),
        dend=torch.full((B, K), 1.1 * 500.0, dtype=dtype),
    )
    sea_mask = torch.ones((B, K), dtype=torch.bool)
    params = _coord.default_coordinator_params()

    aux = _build_aux(state, forcing, sea_mask, params)
    for name in aux._fields:
        v = getattr(aux, name)
        assert v.shape == (B, K), f"aux.{name} shape {v.shape} != (B,K)=({B},{K})"
        assert v.dtype == dtype, f"aux.{name} dtype {v.dtype} != {dtype}"


def test_schema_round_trip(tmp_path):
    """save() → load() preserves data exactly."""
    import numpy as np

    from _schema import StateFields, ForcingFields

    K, B = 3, 1
    state = StateFields(
        qv=np.full((B, K), 1.0e-3),
        qc=np.full((B, K), 1.0e-5),
        qr=np.full((B, K), 0.0),
        qs=np.full((B, K), 0.0),
        qg=np.full((B, K), 0.0),
        qi=np.full((B, K), 0.0),
        nc=np.full((B, K), 1.0e8),
        nr=np.full((B, K), 0.0),
        ni=np.full((B, K), 0.0),
        brs=np.full((B, K), 0.0),
        t=np.full((B, K), 280.0),
    )
    forcing = ForcingFields(
        p=np.full((B, K), 1.0e5),
        den=np.full((B, K), 1.2),
        delz=np.full((B, K), 100.0),
        dend=np.full((B, K), 1.2),
    )
    scalars = {
        "dtcld": 60.0,
        "ccn0": 1.0e8,
        "qmin": 1.0e-15,
        "ncmin_land": 1.0e6,
        "ncmin_sea": 1.0e6,
    }
    out = _THIS  # any field, won't be checked here
    save_golden(
        tmp_path / "case",
        state_in=state, forcing=forcing, scalars=scalars,
        state_out=state,
        metadata={"test_name": "round_trip"},
    )
    loaded = load_golden(tmp_path / "case")
    assert loaded.scalars["dtcld"] == 60.0
    assert loaded.metadata["test_name"] == "round_trip"
    import numpy as np

    np.testing.assert_array_equal(loaded.state_in.qv, state.qv)
    np.testing.assert_array_equal(loaded.state_out.t, state.t)
