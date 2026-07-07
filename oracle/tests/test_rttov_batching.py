"""T1-5 RTTOV 프로파일 배치화 검증 (docs/DA_REALTIME_PLAN.md).

3-사이트 배치화의 게이트:
  (b) interp/builder — 배치 결과가 단일-컬럼 루프와 **정확히**(torch.equal) 같아야
      한다: 배치화는 벡터화일 뿐 수치 경로 변경이 아니다.
  (a) case-writer — 픽스처 6개 초과 nprof를 템플릿 복제로 수용, 연속 번호,
      namelist 카운트 패치 (픽스처-gated).
  (live) 배치 1회 runK의 BT가 프로파일별 개별 runK와 일치 (RTTOV 결정론) —
      배치화가 H(x) 값을 바꾸지 않음을 실기로 증명.

전부 correctness 기반 — wall-time assert 없음 (동시 부하 캐비앳).
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from kdm6.state import Forcing, State
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig, interp_log_pressure, model_to_rttov_tensors)
from kdm6.obs.rttov_input_builder import RttovInputConfig, pack_rttov_input

# 픽스처/exe 게이트 + 헬퍼는 case-writer 테스트 모듈의 것을 재사용
from tests.test_rttov_case_writer import (
    _CHANNELS, _HAVE_EXE, _HAVE_FIXTURE, _fixture_p_half, _fixture_tq,
    make_live_run_k, needs_fixture, needs_live, write_rttov_case)

_F64 = dict(dtype=torch.float64)


def _batched_columns(B: int = 4, nlev: int = 12, seed: int = 7):
    """컬럼별로 다른 ascending 압력 그리드 + 물리적 T/qv."""
    g = torch.Generator().manual_seed(seed)
    p = torch.sort(50.0 + 900.0 * torch.rand((B, nlev), generator=g, **_F64), dim=-1).values
    th = 250.0 + 60.0 * torch.rand((B, nlev), generator=g, **_F64)
    qv = 1.0e-5 + 1.0e-2 * torch.rand((B, nlev), generator=g, **_F64)
    return p, th, qv


# ─── (b) interp — 배치 == 단일-컬럼 루프 (정확 일치) ─────────────────────────


def test_interp_batched_equals_percolumn_loop():
    p_src, th, _ = _batched_columns()
    p_dst = torch.linspace(100.0, 900.0, 9, **_F64)
    out_b = interp_log_pressure(th, p_src, p_dst)
    rows = [interp_log_pressure(th[i], p_src[i], p_dst) for i in range(th.shape[0])]
    assert out_b.shape == (th.shape[0], 9)
    assert torch.equal(out_b, torch.stack(rows)), "batched interp != per-column loop"


def test_interp_batched_rejects_disjoint_column():
    p_src, th, _ = _batched_columns()
    p_src_bad = p_src.clone()
    p_src_bad[1] = p_src_bad[1] * 100.0                 # 한 컬럼만 Pa 단위 흉내
    p_dst = torch.linspace(100.0, 900.0, 9, **_F64)
    with pytest.raises(ValueError, match="disjoint"):
        interp_log_pressure(th, p_src_bad, p_dst)


# ─── (b) builder — 배치 == 단일-컬럼 스택 (정확 일치) ────────────────────────


def _cfg(nlay_target: int = 9):
    p_lay = torch.linspace(100.0, 900.0, nlay_target, **_F64)
    # p_half: nlay+1 레벨 (Nlayers = Nlevels - 1 불변식)
    p_half = torch.linspace(95.0, 905.0, nlay_target + 1, **_F64)
    return RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay, rttov_level_pressure=p_half)


def _leaves(th, qv):
    z = torch.zeros_like(th)
    return State(th=th, qv=qv, qc=z, qr=z, qi=z, qs=z, qg=z,
                 nccn=z, nc=z, ni=z, nr=z, bg=z)


def test_builder_batched_equals_stacked_single_columns():
    p, th, qv = _batched_columns()
    ones = torch.ones_like(p)
    cfg = _cfg()
    prof_b = model_to_rttov_tensors(
        _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), cfg)
    singles_t, singles_q = [], []
    for i in range(p.shape[0]):
        prof_i = model_to_rttov_tensors(
            _leaves(th[i], qv[i]),
            Forcing(rho=ones[i], pii=ones[i], p=p[i], delz=ones[i]), cfg)
        singles_t.append(prof_i.t_lay)
        singles_q.append(prof_i.q_lay)
    assert torch.equal(prof_b.t_lay, torch.stack(singles_t))
    assert torch.equal(prof_b.q_lay, torch.stack(singles_q))
    # p_half는 (B, nlev)로 broadcast — 모든 행이 공유 그리드와 동일
    assert prof_b.p_half.shape == (p.shape[0], 10)
    assert torch.equal(prof_b.p_half[0], prof_b.p_half[-1])


def test_builder_batched_grad_reaches_each_column():
    p, th, qv = _batched_columns()
    th = th.requires_grad_(True)
    ones = torch.ones_like(p)
    prof = model_to_rttov_tensors(
        _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), _cfg())
    prof.t_lay.sum().backward()
    # 모든 컬럼 행에 비영 gradient (배치화가 grad 경로를 끊지 않음)
    assert (th.grad.abs().sum(dim=-1) > 0).all()


def test_builder_batched_requires_interp_target():
    p, th, qv = _batched_columns()
    ones = torch.ones_like(p)
    cfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                             rttov_layer_pressure=None, rttov_level_pressure=None)
    with pytest.raises(ValueError, match="batched columns require"):
        model_to_rttov_tensors(
            _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), cfg)


def test_builder_batched_rejects_cloud_for_now():
    p, th, qv = _batched_columns()
    ones = torch.ones_like(p)
    cfg = _cfg()
    object.__setattr__(cfg, "cloud", True) if hasattr(cfg, "__dataclass_fields__") \
        else None
    try:
        cfg2 = cfg._replace(cloud=True) if hasattr(cfg, "_replace") else cfg
    except (AttributeError, TypeError, ValueError):
        cfg2 = cfg
    if not getattr(cfg2, "cloud", False):
        pytest.skip("RttovProfileConfig has no cloud flag on this path")
    with pytest.raises(ValueError, match="clear-sky only"):
        model_to_rttov_tensors(
            _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), cfg2)


def test_pack_accepts_batched_builder_output():
    p, th, qv = _batched_columns()
    ones = torch.ones_like(p)
    prof = model_to_rttov_tensors(
        _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), _cfg())
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="ami_501_test",
                                                  channels=_CHANNELS))
    assert rin.nprofiles == p.shape[0]
    assert rin.profile["T"].shape == (p.shape[0], 9)


# ─── (a) case-writer 복제 (픽스처-gated) ─────────────────────────────────────


def _fixture_batch_input(nprof: int):
    """픽스처 T/Q를 프로파일별 미세 섭동으로 복제한 nprof-프로파일 입력."""
    t_vec, q_vec = _fixture_tq()
    nlay = len(t_vec)
    t = torch.tensor(np.stack([t_vec + 0.01 * k for k in range(nprof)]), **_F64)
    q = torch.tensor(np.stack([q_vec * (1.0 + 1.0e-4 * k) for k in range(nprof)]), **_F64)
    from kdm6.obs.model_profile_builder import RttovProfileTensors
    prof = RttovProfileTensors(
        t_lay=t, q_lay=q, p_lay=None,
        p_half=torch.as_tensor(_fixture_p_half(), **_F64).unsqueeze(0).expand(nprof, -1))
    return pack_rttov_input(prof, RttovInputConfig(coef_id="ami_501_test",
                                                   channels=_CHANNELS))


@needs_fixture
def test_case_writer_replicates_profiles_beyond_fixture(tmp_path):
    rin = _fixture_batch_input(9)                     # 픽스처는 6개 → 3개 복제 필요
    out = write_rttov_case(rin, tmp_path / "case9")
    prof_root = out.parent / "in" / "profiles"
    ids = sorted(d.name for d in prof_root.iterdir() if d.is_dir())
    assert ids == [str(i).zfill(3) for i in range(1, 10)], ids
    # namelist 카운트 패치 확인
    txt = (out / "rttov_test.txt").read_text()
    assert "defn%nprofiles = 9" in txt.replace("  ", " ") or \
           any(f"nprofiles{pad}={pad}9" in txt.replace(" ", "")
               for pad in ("",)), txt[:400]


@needs_fixture
def test_case_writer_rejects_beyond_digit_width(tmp_path):
    # 1-행 공유 P_HALF(행수 가드 통과) + nprofiles=1000 → 3자리 번호 한계 초과.
    t_vec, q_vec = _fixture_tq()
    from kdm6.obs.model_profile_builder import RttovProfileTensors
    prof = RttovProfileTensors(
        t_lay=torch.tensor(np.tile(t_vec, (6, 1)), **_F64),
        q_lay=torch.tensor(np.tile(q_vec, (6, 1)), **_F64),
        p_lay=None, p_half=torch.as_tensor(_fixture_p_half(), **_F64))
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="ami_501_test",
                                                  channels=_CHANNELS))
    rin = rin._replace(nprofiles=1000) if hasattr(rin, "_replace") else rin
    if rin.nprofiles != 1000:
        pytest.skip("RttovInput not _replace-able")
    with pytest.raises(ValueError, match="chunk the"):
        write_rttov_case(rin, tmp_path / "case1000")


# ─── LIVE — 배치 runK == 프로파일별 개별 runK (BT 값 불변 증명) ──────────────


@needs_live
def test_live_batched_runk_matches_individual_runs(tmp_path):
    nprof = 8                                          # 6-cap 초과 → 복제 경로 실증
    rin = _fixture_batch_input(nprof)
    bt_b, k_b, rq_b = make_live_run_k(tmp_path / "batched")(rin)
    bt_b = np.asarray(bt_b)
    assert bt_b.shape == (nprof, 16)
    assert np.asarray(k_b["T"]).shape[0] == nprof

    for p_idx in (0, 3, 7):                            # 대표 3개만 개별 대조 (비용 절약)
        rin1 = _fixture_batch_input(nprof)
        # 단일 프로파일 입력: 해당 행만 추출
        from kdm6.obs.model_profile_builder import RttovProfileTensors
        t1 = torch.as_tensor(rin1.profile["T"][p_idx], **_F64)
        q1 = torch.as_tensor(rin1.profile["Q"][p_idx], **_F64)
        ph1 = torch.as_tensor(rin1.profile["P_HALF"][p_idx], **_F64)
        prof1 = RttovProfileTensors(t_lay=t1, q_lay=q1, p_lay=None, p_half=ph1)
        r1 = pack_rttov_input(prof1, RttovInputConfig(coef_id="ami_501_test",
                                                      channels=_CHANNELS))
        bt1 = np.asarray(make_live_run_k(tmp_path / f"single{p_idx}")(r1)[0])
        assert np.allclose(bt_b[p_idx], bt1[0], rtol=0, atol=2.0e-3), (
            f"profile {p_idx}: batched BT != individual BT\n"
            f"batched {bt_b[p_idx]}\nsingle  {bt1[0]}")


@needs_fixture
def test_case_writer_accepts_batched_builder_output_with_p_witness(tmp_path):
    """Codex stop-review 회귀 가드: 배치 builder의 공유 layer-grid witness(P)는
    pack에서 1-행으로 승격되는데, writer가 이를 nprof로 broadcast하지 않으면
    pl_all[p]가 p>=1에서 IndexError — 전체 배치 체인(builder->pack->write)을
    P 존재 상태로 검증한다."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    p_lay_fix = torch.as_tensor(np.asarray(fixture_layer_pressure(), dtype=float), **_F64)
    ph_fix = torch.as_tensor(np.asarray(_fixture_p_half(), dtype=float), **_F64)
    B, nlev = 7, 40
    g = torch.Generator().manual_seed(3)
    # 컬럼별 서로 다른 ascending 소스 그리드 (픽스처 범위와 겹치게)
    p = torch.sort(1.0 + 900.0 * torch.rand((B, nlev), generator=g, **_F64), dim=-1).values
    th = 210.0 + 90.0 * torch.rand((B, nlev), generator=g, **_F64)
    qv = 1.0e-6 + 5.0e-3 * torch.rand((B, nlev), generator=g, **_F64)
    ones = torch.ones_like(p)
    cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay_fix, rttov_level_pressure=ph_fix)
    prof = model_to_rttov_tensors(
        _leaves(th, qv), Forcing(rho=ones, pii=ones, p=p, delz=ones), cfg)
    assert prof.p_lay is not None                      # P witness 존재 (지적된 경로)
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="ami_501_test",
                                                  channels=_CHANNELS))
    assert rin.nprofiles == B
    out = write_rttov_case(rin, tmp_path / "case7p")   # 이전 코드면 IndexError
    ids = sorted(d.name for d in (out.parent / "in" / "profiles").iterdir() if d.is_dir())
    assert ids == [str(i).zfill(3) for i in range(1, B + 1)], ids


def test_interp_batched_exact_knots_and_endpoint_clamp():
    """Codex 검토 보강: searchsorted(right=True) 타이(정확한 knot 일치)와
    no-extrapolation endpoint 클램프에서도 배치 == 단일-컬럼 루프 정확 일치.
    p_dst가 row0의 knot들과 정확히 일치(50=클램프, 100/200/400=타이, 500=클램프)."""
    p_src = torch.tensor([[100.0, 200.0, 300.0, 400.0],
                          [150.0, 250.0, 350.0, 450.0]], **_F64)
    field = torch.tensor([[1.0, 2.0, 3.0, 4.0],
                          [10.0, 20.0, 30.0, 40.0]], **_F64)
    p_dst = torch.tensor([50.0, 100.0, 200.0, 400.0, 500.0], **_F64)
    out_b = interp_log_pressure(field, p_src, p_dst)
    rows = [interp_log_pressure(field[i], p_src[i], p_dst) for i in range(2)]
    assert torch.equal(out_b, torch.stack(rows))
    # 의미 검증(row0): 정확 knot은 그 값 그대로, 범위 밖은 endpoint 클램프
    assert torch.equal(out_b[0], torch.tensor([1.0, 1.0, 2.0, 4.0, 4.0], **_F64))


def test_k_index_width_guard():
    """K 출력 인덱스 4자리 한계 가드 — nprof×nch > 9999 는 '****' 오버플로로
    파서가 거부하게 되므로 케이스 생성 단계에서 loud 거부 (전 도메인 999-chunk
    ×16ch 실측 발견의 회귀 고정)."""
    import pytest
    from kdm6.obs.rttov_case_writer import _guard_k_index_width
    _guard_k_index_width(624, 16)                      # 9984 ≤ 9999 통과
    with pytest.raises(ValueError, match="4 digits"):
        _guard_k_index_width(999, 16)                  # 15984 거부
