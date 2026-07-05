"""T0-1 frame reader 검증 (docs/DA_REALTIME_PLAN.md).

두 층위:
  1. 순수 파생 함수 테스트 — wrfout 불필요, 공개 CI에서도 실행.
  2. 로컬 wrfout 통합 테스트 — private host 트리의 SS 케이스 산출물이 있을 때만
     (없으면 skip; live-RTTOV tier와 같은 gating).

통합 검증의 불변식 (외부 진리값 불필요 — 파일 내 자기일관성):
  - THM 교차검증: 이 wrfout은 THM(예후 θm−T0)과 T(진단 dry θ−T0)를 둘 다 실어
    derive_th(THM,qv) == T+T0 가 성립해야 한다. 파생 1의 무진리값 검증.
  - 정수압 일관성: 중앙차분 dp/dz ≈ −rho·g — rho(EOS 재구성)와 delz(destagger)를
    동시에 잡는다. SS 케이스는 준정수압이므로 수 % 이내.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import torch

from kdm6.io import (
    derive_delz,
    derive_p_pii,
    derive_rho,
    derive_th,
    nccn_init_profile,
    read_wrfout_frame,
)
from kdm6.io.frame_reader import G, R_D, R_V, T0

_REPO = Path(__file__).resolve().parents[2]
_WRFOUT = _REPO / "host" / "KIM-meso_v1.0" / "run" / "wrfout.37.quarter_ss.nc"
needs_wrfout = pytest.mark.skipif(
    not _WRFOUT.exists(), reason=f"local SS wrfout not found: {_WRFOUT}")


# ─── 1. 순수 파생 함수 (wrfout 불필요) ────────────────────────────────────────


def test_nccn_init_formula_hand_values():
    """wrapper ITIMESTEP==1 공식의 손계산 대조 (land/sea 각 1컬럼, K=2).

    delz = [500, 700] → Z_SUM = [500, 1200] (해당 층 포함 하부누적 — Fortran 루프
    순서 그대로: Z_SUM 누적 후 NN 계산).
    """
    delz = torch.tensor([[500.0, 700.0], [500.0, 700.0]], dtype=torch.float64)
    is_land = torch.tensor([True, False])
    nn = nccn_init_profile(delz, is_land)

    z1, z2 = 500.0, 1200.0
    land1 = (5000.0 * math.exp(-0.4 * z1 / 1000.0) + 100.0) * 1e6
    land2 = (5000.0 * math.exp(-0.4 * z2 / 1000.0) + 100.0) * 1e6
    sea1 = (150.0 * math.exp(-0.35 * z1 / 1000.0) + 10.0) * 1e6
    sea2 = (150.0 * math.exp(-0.35 * z2 / 1000.0) + 10.0) * 1e6
    expect = torch.tensor([[land1, land2], [sea1, sea2]], dtype=torch.float64)
    assert torch.allclose(nn, expect, rtol=1e-12)


def test_derive_th_matches_phy_prep_formula():
    """phy_prep F:105 그대로: th = (THM+T0)/(1+Rv/Rd·qv)."""
    thm_pert = torch.tensor([[5.0]], dtype=torch.float64)
    qv = torch.tensor([[0.01]], dtype=torch.float64)
    th = derive_th(thm_pert, qv)
    assert th.item() == pytest.approx((5.0 + T0) / (1.0 + (R_V / R_D) * 0.01), rel=1e-14)


def test_derive_delz_destagger():
    """z_w=(PH+PHB)/g 41→40 destagger; 균일 두께 케이스 손검증."""
    K = 4
    z_w = torch.arange(K + 1, dtype=torch.float64)[None, :] * 500.0  # 0,500,...,2000 m
    ph = torch.zeros_like(z_w)
    phb = z_w * G
    delz = derive_delz(ph, phb)
    assert delz.shape == (1, K)
    assert torch.allclose(delz, torch.full((1, K), 500.0, dtype=torch.float64), rtol=1e-12)


def test_derive_rho_ideal_gas_roundtrip():
    """EOS 재구성의 자기일관성: p == ρ_d·R_d·θm·π 를 재조립으로 확인."""
    p_pert = torch.tensor([[500.0]], dtype=torch.float64)
    pb = torch.tensor([[9.0e4]], dtype=torch.float64)
    thm_pert = torch.tensor([[8.0]], dtype=torch.float64)
    qv = torch.tensor([[0.008]], dtype=torch.float64)
    p, pii = derive_p_pii(p_pert, pb)
    rho = derive_rho(p, thm_pert, pii, qv)
    rho_d = rho / (1.0 + qv)
    p_back = rho_d * R_D * (thm_pert + T0) * pii
    assert torch.allclose(p_back, p, rtol=1e-14)


# ─── 2. 로컬 wrfout 통합 (없으면 skip) ────────────────────────────────────────


@pytest.fixture(scope="module")
def frame():
    return read_wrfout_frame(str(_WRFOUT), time_idx=1)  # t=1: 물리 1스텝 이후 프레임


@needs_wrfout
def test_shapes_dtypes_finite(frame):
    B, K = frame.meta["ny"] * frame.meta["nx"], frame.meta["kme"]
    for name, t in frame.state._asdict().items():
        assert t.shape == (B, K), name
        assert t.dtype == torch.float64, name
        assert torch.isfinite(t).all(), name
    for name, t in frame.forcing._asdict().items():
        assert t.shape == (B, K), name
        assert torch.isfinite(t).all(), name
    # 수분류 비음수 (wrfout이 이미 dynamics 음수패딩 이후라 ≥0이어야 정상)
    for name in ("qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"):
        assert getattr(frame.state, name).min() >= 0.0, name
    assert frame.xland.shape == (B,)
    assert set(frame.xland.unique().tolist()) <= {1.0, 2.0}


@needs_wrfout
def test_th_cross_check_thm_vs_diagnostic_t(frame):
    """파생 1의 무진리값 검증: derive_th(THM,qv) == wrfout T(진단 dry θ)+T0.

    wrfout 저장이 float32라 상대오차 ~1e-6 수준까지만 요구.
    """
    import netCDF4

    ds = netCDF4.Dataset(str(_WRFOUT))
    try:
        t_diag = torch.from_numpy(
            ds.variables["T"][1, ...].astype("float64")).permute(1, 2, 0).reshape(
            frame.state.th.shape[0], -1)
    finally:
        ds.close()
    th_from_t = t_diag + T0
    rel = ((frame.state.th - th_from_t).abs() / th_from_t).max()
    assert rel < 5e-6, f"THM-derived th vs diagnostic T mismatch: max rel {rel:.3e}"


@needs_wrfout
def test_hydrostatic_consistency(frame):
    """rho(EOS)와 delz(destagger)의 결합 검증: 내부 레벨 중앙차분
    dp/dz ≈ −rho·g. SS 케이스는 준정수압 — 중앙값 2% 이내, 최악 10% 이내."""
    p, rho, delz = frame.forcing.p, frame.forcing.rho, frame.forcing.delz
    # 레벨 k의 중앙차분: (p[k+1]-p[k-1]) / (0.5*(delz[k-1]+delz[k+1]) + delz[k])
    dz_c = 0.5 * (delz[:, :-2] + delz[:, 2:]) + delz[:, 1:-1]
    dpdz = (p[:, 2:] - p[:, :-2]) / dz_c
    ratio = -dpdz / (rho[:, 1:-1] * G)
    err = (ratio - 1.0).abs()
    assert err.median() < 0.02, f"hydrostatic median err {err.median():.4f}"
    assert err.max() < 0.10, f"hydrostatic max err {err.max():.4f}"


@needs_wrfout
def test_oracle_step_smoke(frame):
    """통합 증명: 읽은 State/Forcing으로 오라클 1스텝(dt=300)이 유한하게 돈다.

    비용 절약을 위해 128컬럼 서브샘플 (mstep batch-global — 전 컬럼이면 최악
    컬럼이 지배해 테스트가 느려질 수 있음).
    """
    from kdm6.runtime import _kdm6_pure, make_parameters
    from kdm6.state import State, Forcing

    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 128).long()
    s = State(**{k: v[idx] for k, v in frame.state._asdict().items()})
    f = Forcing(**{k: v[idx] for k, v in frame.forcing._asdict().items()})
    out = _kdm6_pure(s, f, make_parameters(), dt=300.0)
    for name, t in out._asdict().items():
        assert torch.isfinite(t).all(), f"non-finite {name} after one oracle step"


@needs_wrfout
def test_nccn_t0_fallback_applies_only_when_all_zero(frame):
    """t=1 프레임은 QNCCN이 살아 있으므로 폴백 미적용이어야 한다."""
    assert frame.meta["nccn_fallback"] is False
    assert frame.state.nccn.max() > 0
