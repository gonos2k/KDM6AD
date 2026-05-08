"""Compare Python oracle output against a Fortran golden vector.

Usage:
    PYTHONPATH=. python parity/run_parity.py parity/golden/<name>

Exit code 0 ⟺ all schema fields match within atol=1e-6, rtol=1e-5.
NCCN/QNN/NN is intentionally outside this T3 schema; wrapper-level NCCN
pass-through is validated in the libtorch/C ABI tests, not here.
Field-by-field diffs are printed regardless.

Per the codex review #2 priority recommendation, this is the verification
gate between Stage F (oracle complete) and Stage G (KIM-meso integration),
but only for the 11 microphysics-level state fields in `parity/_schema.py`.

auxdiag is computed from `state_in + forcing` inside the harness (option (b)
from review #5). The current schema does not consume captured operational
auxdiag arrays, so divergence can reflect auxdiag/default mismatch rather than
oracle-vs-Fortran drift. Sea/land mask defaults to all-sea unless the golden
vector's metadata has a "sea_mask" entry.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

# Make `kdm6_torch/kdm6` importable when run from project root.
_THIS = Path(__file__).resolve().parent
_PROJ = _THIS.parent
sys.path.insert(0, str(_PROJ / "kdm6_torch"))

from kdm6 import constants as c  # noqa: E402
from kdm6 import coordinator as _coord  # noqa: E402
from kdm6.cloud_dsd import diag_qcr_torch  # noqa: E402

from _schema import StateFields, ForcingFields, load as load_golden  # noqa: E402


_ATOL_DEFAULT = 1e-6
_RTOL_DEFAULT = 1e-5
_STATE_FIELDS = ("qv", "qc", "qr", "qs", "qg", "qi", "nc", "nr", "ni", "brs", "t")


def _to_tensor(arr: np.ndarray, dtype=torch.float64) -> torch.Tensor:
    return torch.from_numpy(np.ascontiguousarray(arr)).to(dtype)


def _state_to_coordinator(state: StateFields) -> _coord.CoordinatorState:
    return _coord.CoordinatorState(
        qv=_to_tensor(state.qv),
        qc=_to_tensor(state.qc),
        qr=_to_tensor(state.qr),
        qs=_to_tensor(state.qs),
        qg=_to_tensor(state.qg),
        qi=_to_tensor(state.qi),
        nc=_to_tensor(state.nc),
        nr=_to_tensor(state.nr),
        ni=_to_tensor(state.ni),
        brs=_to_tensor(state.brs),
        t=_to_tensor(state.t),
    )


def _forcing_to_coordinator(forcing: ForcingFields) -> _coord.CoordinatorForcing:
    return _coord.CoordinatorForcing(
        p=_to_tensor(forcing.p),
        den=_to_tensor(forcing.den),
        delz=_to_tensor(forcing.delz),
        dend=_to_tensor(forcing.dend),
    )


def _build_aux(
    state: _coord.CoordinatorState,
    forcing: _coord.CoordinatorForcing,
    sea_mask: torch.Tensor,
    params: _coord.CoordinatorParams,
) -> _coord.CoordinatorAuxDiagnostics:
    """auxdiag를 state+forcing에서 inline 재진단.

    Current T3 parity does not read captured operational auxdiag arrays. It
    uses default/re-derived diagnostics for n0r/n0i/n0c/n0so/n0go, work1_*,
    qcr, avedia_i, and rslopec*. If the KIM-meso wrapper uses different
    land/sea- or density-aware diagnostics, drift may be wrapper/diagnostic
    mismatch rather than oracle mismatch.
    """
    n0r = torch.full_like(state.qr, 8.0e6)
    n0i = torch.full_like(state.qi, 1.0e6)
    n0c = torch.full_like(state.qc, 1.0e8)
    n0so = torch.full_like(state.qs, 2.0e6)
    n0go = torch.full_like(state.qg, 4.0e6)
    work1_r = torch.full_like(state.qr, 1.0e-3)
    work1_ice = torch.full_like(state.qi, 1.0e-3)
    work1_water = torch.full_like(state.qi, 1.0e-3)
    qcr = diag_qcr_torch(sea_mask, params=params.cloud_dsd, ref=state.qc)
    avedia_i = torch.full_like(state.qi, 1.0e-4)

    pre = _coord.preamble_torch(state, forcing, sea_mask, params=params)
    rslopecmu = (
        pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    )
    rslopecd = pre.rslopec ** c.DMC
    return _coord.CoordinatorAuxDiagnostics(
        n0r=n0r, n0i=n0i, n0c=n0c, n0so=n0so, n0go=n0go,
        work1_r=work1_r, work1_ice=work1_ice, work1_water=work1_water,
        qcr=qcr, avedia_i=avedia_i,
        rslopecmu=rslopecmu, rslopecd=rslopecd,
    )


def _diff_field(name: str, fortran: np.ndarray, python: np.ndarray,
                atol: float, rtol: float) -> tuple[bool, str]:
    """Return (passed, summary_line) including max-error location (review11#5).

    Summary includes max|Δ| location (B,K index), RMS error, and fraction of
    cells within tolerance. Helps localize Python-vs-Fortran drift to a
    specific column/level when a future Fortran golden fails.
    """
    diff = np.abs(fortran - python)
    scale = np.maximum(np.abs(fortran), np.abs(python))
    rel = diff / np.where(scale > 0, scale, 1.0)
    max_abs = float(diff.max())
    max_rel = float(rel.max())
    rms = float(np.sqrt(np.mean(diff ** 2)))
    fortran_max = float(np.abs(fortran).max() + 1e-30)

    # per-cell tolerance: atol + rtol * |fortran|
    per_cell_tol = atol + rtol * np.abs(fortran)
    within = diff <= per_cell_tol
    frac_in = float(within.mean())

    # max-location index (B, K)
    if diff.size > 0:
        flat_idx = int(np.argmax(diff))
        loc = np.unravel_index(flat_idx, diff.shape)
        loc_str = "[" + ",".join(str(int(x)) for x in loc) + "]"
    else:
        loc_str = "[]"

    passed = max_abs <= atol + rtol * fortran_max
    flag = "PASS" if passed else "FAIL"
    return passed, (
        f"  {flag}  {name:5s}  max|Δ|={max_abs:.3e} @ {loc_str}  "
        f"RMS={rms:.3e}  in_tol={frac_in*100:.1f}%"
    )


def run_parity(
    golden_dir: Path,
    *,
    atol: float = _ATOL_DEFAULT,
    rtol: float = _RTOL_DEFAULT,
) -> tuple[bool, list[str]]:
    """Run a single golden-vector comparison. Return (all_pass, summary_lines)."""
    g = load_golden(golden_dir)
    state_in = _state_to_coordinator(g.state_in)
    forcing = _forcing_to_coordinator(g.forcing)
    dtcld = float(g.scalars["dtcld"])

    # sea_mask: golden vector가 명시하지 않으면 all-sea 기본값. shape를 (B,K)로 정규화
    # (review11#2). diag_qcr_torch는 (B,K) 가정이라 (B,) 또는 (B,1)은 broadcasting
    # 사고 위험 — 미리 expand.
    B, K = state_in.qc.shape
    raw_mask = g.metadata.get("sea_mask")
    if raw_mask is None:
        sea_mask = torch.ones((B, K), dtype=torch.bool)
    else:
        m = torch.tensor(raw_mask, dtype=torch.bool)
        if m.dim() == 1:
            if m.shape[0] != B:
                raise ValueError(f"sea_mask 1D shape ({m.shape[0]}) != B={B}")
            sea_mask = m.unsqueeze(-1).expand(B, K).contiguous()
        elif m.dim() == 2:
            if m.shape == (B, 1):
                sea_mask = m.expand(B, K).contiguous()
            elif m.shape == (B, K):
                sea_mask = m
            else:
                raise ValueError(
                    f"sea_mask 2D shape {tuple(m.shape)} not in "
                    f"{{(B,1)=({B},1), (B,K)=({B},{K})}}"
                )
        else:
            raise ValueError(f"sea_mask must be 1D or 2D, got dim={m.dim()}")
    assert sea_mask.shape == (B, K), f"sea_mask normalization bug: {sea_mask.shape} != ({B},{K})"

    full_params = _coord.default_coordinator_params()
    warm_params = _coord.default_warm_phase_params()
    cold_params = _coord.default_cold_phase_params()
    mf_params = _coord.default_melt_freeze_phase_params()

    aux = _build_aux(state_in, forcing, sea_mask, full_params)
    py_state = _coord.kdm62d_one_step_torch(
        state_in, forcing, aux, sea_mask,
        full_params=full_params, warm_params=warm_params,
        cold_params=cold_params, mf_params=mf_params,
        dtcld=dtcld,
    )

    summary = []
    all_pass = True
    for name in _STATE_FIELDS:
        fortran_arr = getattr(g.state_out, name)
        py_arr = getattr(py_state, name).detach().cpu().numpy()
        ok, line = _diff_field(name, fortran_arr, py_arr, atol, rtol)
        summary.append(line)
        all_pass = all_pass and ok
    return all_pass, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("golden_dir", type=Path,
                        help="Directory holding a golden vector (state_in.npz, ...)")
    parser.add_argument("--atol", type=float, default=_ATOL_DEFAULT)
    parser.add_argument("--rtol", type=float, default=_RTOL_DEFAULT)
    args = parser.parse_args()

    g = load_golden(args.golden_dir)
    print(f"# parity: {args.golden_dir}")
    print(f"# capture: {g.metadata.get('capture_date', '?')}  "
          f"test: {g.metadata.get('test_name', '?')}")
    print(f"# atol={args.atol}  rtol={args.rtol}")

    all_pass, summary = run_parity(args.golden_dir, atol=args.atol, rtol=args.rtol)
    for line in summary:
        print(line)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
