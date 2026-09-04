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
import sys
from types import SimpleNamespace

import numpy as np
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
from kdm6.io.frame_reader import G, R_D, R_V, T0, _flat

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


class _Variable:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def __getitem__(self, key):
        return self.data[key]


@pytest.fixture
def synthetic_frame(monkeypatch):
    """Two columns / two levels; exercise reader policies without private files or netCDF4."""
    names = ("QVAPOR THM P PB QNCCN QCLOUD QRAIN QICE QSNOW QGRAUP "
             "QNCLOUD QNICE QNRAIN QIB").split()
    variables = {name: _Variable(name, np.zeros((1, 2, 1, 2), dtype=np.float32))
                 for name in names}
    variables["PB"].data.fill(90000)
    heights = np.array([0., 500., 1200.]).reshape(1, 3, 1, 1)
    variables["PHB"] = _Variable("PHB", np.broadcast_to(heights * G, (1, 3, 1, 2)).copy())
    variables["PH"] = _Variable("PH", np.zeros((1, 3, 1, 2)))
    for name, values in (("XLAND", [1., 2.]), ("XLAT", [35., 36.]),
                         ("XLONG", [127., 128.])):
        variables[name] = _Variable(name, np.array(values).reshape(1, 1, 2))
    closed = []
    dataset = SimpleNamespace(
        variables=variables, USE_THETA_M=1,
        dimensions={name: SimpleNamespace(size=size) for name, size in
                    (("west_east", 2), ("south_north", 1), ("bottom_top", 2))},
        close=lambda: closed.append(True))
    monkeypatch.setitem(sys.modules, "netCDF4", SimpleNamespace(Dataset=lambda path: dataset))
    return variables, closed


@pytest.mark.parametrize("shape", [(2, 3, 2), (3, 2)])
def test_flat_preserves_values_and_column_layout(shape):
    raw = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    raw.flat[0] = -0.0
    # A MaskedArray with no missing elements is valid input.
    var = _Variable("sample", np.ma.array(raw[None], mask=False))
    actual = _flat(var, 0).numpy()
    expected = (raw.transpose(1, 2, 0).reshape(-1, shape[0])
                if len(shape) == 3 else raw.reshape(-1)).astype(np.float64)
    np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))


@pytest.mark.parametrize("policy", [None, "as_stored", "init_profile"])
def test_stored_zero_ccn_requires_explicit_synthesis(synthetic_frame, policy):
    _, closed = synthetic_frame
    kwargs = {} if policy is None else {"nccn_policy": policy}
    frame = read_wrfout_frame("synthetic", **kwargs)
    assert closed == [True]
    assert frame.meta["nccn_fallback"] is (policy == "init_profile")
    if policy == "init_profile":
        expected = torch.tensor([
            [(5000 * math.exp(-0.4 * z / 1000) + 100) * 1e6 for z in (500, 1200)],
            [(150 * math.exp(-0.35 * z / 1000) + 10) * 1e6 for z in (500, 1200)],
        ], dtype=torch.float64)
        torch.testing.assert_close(frame.state.nccn, expected, rtol=1e-12, atol=0)
    else:
        assert torch.equal(frame.state.nccn, torch.zeros((2, 2), dtype=torch.float64))


@pytest.mark.parametrize("policy", ["as_stored", "init_profile"])
def test_nonzero_ccn_preserves_entire_stored_field(synthetic_frame, policy):
    variables, _ = synthetic_frame
    # One nonzero cell must prevent replacement of every zero in the field.
    variables["QNCCN"].data[0, 1, 0, 0] = 123.
    frame = read_wrfout_frame("synthetic", nccn_policy=policy)
    assert not frame.meta["nccn_fallback"]
    assert torch.equal(frame.state.nccn, torch.tensor([[0., 123.], [0., 0.]],
                                                     dtype=torch.float64))


def test_unknown_ccn_policy_rejected_before_opening_file():
    with pytest.raises(ValueError, match="unknown nccn_policy"):
        read_wrfout_frame("does-not-exist", nccn_policy="automatic")


@pytest.mark.parametrize("name", ["QNCCN", "QVAPOR", "XLAT", "XLONG"])
@pytest.mark.parametrize("bad", ["masked", np.nan, np.inf, -np.inf])
def test_reader_rejects_missing_inputs_and_closes_dataset(synthetic_frame, name, bad):
    variables, closed = synthetic_frame
    var = variables[name]
    if bad == "masked":
        var.data = np.ma.array(var.data, mask=False)
        var.data.data.flat[0] = 9.9692e36  # finite hidden fill value
        var.data.mask.flat[0] = True
        reason = "masked values"
    else:
        var.data.flat[0] = bad
        reason = "non-finite values"
    with pytest.raises(ValueError, match=f"{name}: {reason}"):
        read_wrfout_frame("synthetic", nccn_policy="init_profile")
    assert closed == [True]


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
def test_real_frame_preserves_stored_ccn(frame):
    """기본 정책은 저장된 QNCCN을 합성 프로파일로 대체하지 않는다."""
    assert frame.meta["nccn_fallback"] is False
    assert frame.state.nccn.max() > 0
