"""Generate a synthetic golden vector by running the Python oracle.

The goal is to verify that `run_parity.py` is wired correctly end-to-end,
NOT to reveal Python vs Fortran drift. With this self-test, we can:
  1. Run the Python oracle on a hand-built input state.
  2. Save the inputs *and* the oracle output as a golden vector.
  3. Run `run_parity.py` against it — every field should match exactly.

When a real Fortran-captured golden vector arrives, only the data source
changes; the harness pipeline is already verified.

Usage:
    PYTHONPATH=kdm6_torch python parity/build_self_test_vector.py
    PYTHONPATH=kdm6_torch python parity/run_parity.py parity/golden/self_test
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import torch

_THIS = Path(__file__).resolve().parent
_PROJ = _THIS.parent
sys.path.insert(0, str(_PROJ / "kdm6_torch"))
sys.path.insert(0, str(_THIS))

from kdm6 import constants as c  # noqa: E402
from kdm6 import coordinator as _coord  # noqa: E402

from _schema import StateFields, ForcingFields, save as save_golden  # noqa: E402
from run_parity import _build_aux  # reuse the same auxdiag derivation  # noqa: E402


def main() -> int:
    dtype = torch.float64
    K = 4
    B = 1

    state = _coord.CoordinatorState(
        qv=torch.full((B, K), 8.0e-3, dtype=dtype),
        qc=torch.full((B, K), 5.0e-4, dtype=dtype),
        qr=torch.full((B, K), 1.0e-4, dtype=dtype),
        qs=torch.full((B, K), 5.0e-5, dtype=dtype),
        qg=torch.full((B, K), 1.0e-5, dtype=dtype),
        qi=torch.full((B, K), 1.0e-5, dtype=dtype),
        nc=torch.full((B, K), 1.0e8, dtype=dtype),
        nr=torch.full((B, K), 1.0e5, dtype=dtype),
        ni=torch.full((B, K), 1.0e6, dtype=dtype),
        brs=torch.full((B, K), 0.0, dtype=dtype),
        t=torch.full((B, K), 270.0, dtype=dtype),
    )
    forcing = _coord.CoordinatorForcing(
        p=torch.full((B, K), 8.0e4, dtype=dtype),
        den=torch.full((B, K), 1.1, dtype=dtype),
        delz=torch.full((B, K), 500.0, dtype=dtype),
        dend=torch.full((B, K), 1.1 * 500.0, dtype=dtype),
    )
    sea_mask = torch.ones(B, dtype=torch.bool)

    full_params = _coord.default_coordinator_params()
    warm_params = _coord.default_warm_phase_params()
    cold_params = _coord.default_cold_phase_params()
    mf_params = _coord.default_melt_freeze_phase_params()

    aux = _build_aux(state, forcing, sea_mask, full_params)
    new_state = _coord.kdm62d_one_step_torch(
        state, forcing, aux, sea_mask,
        full_params=full_params, warm_params=warm_params,
        cold_params=cold_params, mf_params=mf_params,
        dtcld=60.0,
    )

    def _to_np(t: torch.Tensor) -> np.ndarray:
        return t.detach().cpu().numpy()

    state_in_npy = StateFields(
        qv=_to_np(state.qv), qc=_to_np(state.qc), qr=_to_np(state.qr),
        qs=_to_np(state.qs), qg=_to_np(state.qg), qi=_to_np(state.qi),
        nc=_to_np(state.nc), nr=_to_np(state.nr), ni=_to_np(state.ni),
        brs=_to_np(state.brs), t=_to_np(state.t),
    )
    state_out_npy = StateFields(
        qv=_to_np(new_state.qv), qc=_to_np(new_state.qc), qr=_to_np(new_state.qr),
        qs=_to_np(new_state.qs), qg=_to_np(new_state.qg), qi=_to_np(new_state.qi),
        nc=_to_np(new_state.nc), nr=_to_np(new_state.nr), ni=_to_np(new_state.ni),
        brs=_to_np(new_state.brs), t=_to_np(new_state.t),
    )
    forcing_npy = ForcingFields(
        p=_to_np(forcing.p), den=_to_np(forcing.den),
        delz=_to_np(forcing.delz), dend=_to_np(forcing.dend),
    )
    scalars = {
        "dtcld": 60.0,
        "ccn0": 1.0e8,
        "qmin": 1.0e-15,
        "ncmin_land": 1.0e6,
        "ncmin_sea": 1.0e6,
    }
    metadata = {
        "test_name": "self_test_round_trip",
        "kim_version": "synthetic",
        "fortran_commit": "n/a",
        "capture_date": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "shape": [B, K],
        "sea_mask": sea_mask.tolist(),
        "note": "Generated from Python oracle output — round-trip parity should be exact.",
    }
    out_dir = _THIS / "golden" / "self_test"
    save_golden(out_dir, state_in=state_in_npy, forcing=forcing_npy,
                scalars=scalars, state_out=state_out_npy, metadata=metadata)
    print(f"wrote {out_dir}/  (B={B}, K={K})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
