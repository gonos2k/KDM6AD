"""da_cvt — per-field hybrid CVT (add/mul delta-form) 단위 검증.

핵심 계약:
  1. spec=None 레거시 경로는 기존 선형 CVT와 bitwise 동일 (byte-identity).
  2. CVT_LINEAR(전 필드 add)는 spec=None과 산술적으로 bitwise 동일.
  3. v=0 → x0 == xb bitwise (모든 mode); σ=0 성분은 어떤 v에도 배경 고정.
  4. mul 필드 양수성: x0 ≥ −ε − 4·U64·(xb+ε) (expm1 포화 포함 정직한 fp64 하계).
  5. jac은 구현된 forward의 정확한 도함수 — autograd를 시험 오라클로 대조.
  6. validate_cvt 는 위험 구성(σ>0@xb=0, clamp headroom 부족 등)을 fail-fast.
"""
from __future__ import annotations

import json

import pytest
import torch

from kdm6.da_cvt import (
    CVT_LINEAR, CvtSpec, U64, _stack, _unstack, build_cvt_record, cvt_apply,
    make_default_cvt, validate_cvt,
)
from kdm6.state import State

_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_state():
    return State(
        th=_t2(296.8, 282.4), qv=_t2(1.40e-2, 2.0e-3),
        qc=_t2(1.0e-3, 5.0e-4), qr=_t2(1.0e-4, 1.0e-5),
        qi=_t2(0.0, 1.0e-6), qs=_t2(0.0, 5.0e-5),
        qg=_t2(0.0, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(0.0, 1.0e8),
        nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0),
    )


def _full_sigma(ref: State, val: float) -> State:
    return State(**{k: torch.full_like(getattr(ref, k), val) for k in State._fields})


def _mul_spec(eps: float = 0.0) -> CvtSpec:
    """th=add, 나머지 11필드 mul (기본 설계 형태)."""
    return CvtSpec(mode=("add",) + ("mul",) * 11, eps=(0.0,) + (eps,) * 11)


def _rand(shape, gen):
    return torch.randn(shape, generator=gen, **_F64)


def test_cvt_apply_none_is_legacy_bitwise():
    """T1: spec=None은 기존 xb + σ⊙v 표현식 그대로 (음수 xb 포함, 검증 없음)."""
    g = torch.Generator().manual_seed(7)
    xb = _unstack(_rand((12, 3, 4), g))            # 음수 포함 임의 배경
    sig = _unstack(_rand((12, 3, 4), g).abs())
    v = _rand((12, 3, 4), g)
    x0, jac = cvt_apply(xb, sig, v)
    ref = _unstack(_stack(xb) + _stack(sig) * v)
    for f in State._fields:
        assert torch.equal(getattr(x0, f), getattr(ref, f)), f
    assert torch.equal(jac, _stack(sig))


def test_cvt_apply_all_add_matches_none_bitwise():
    """T2: CVT_LINEAR(전 필드 add)는 spec=None과 bitwise 동일."""
    g = torch.Generator().manual_seed(11)
    xb = _unstack(_rand((12, 2, 5), g))
    sig = _unstack(_rand((12, 2, 5), g).abs())
    v = _rand((12, 2, 5), g)
    x0_none, jac_none = cvt_apply(xb, sig, v)
    x0_lin, jac_lin = cvt_apply(xb, sig, v, CVT_LINEAR)
    for f in State._fields:
        assert torch.equal(getattr(x0_none, f), getattr(x0_lin, f)), f
    assert torch.equal(jac_none, jac_lin)


def test_v0_identity_bitwise_all_modes():
    """T3: v=0 → x0 == xb bitwise (기본 spec과 ε>0 변형 모두)."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    for sp in (spec, _mul_spec(eps=1.0e-5)):
        sig = b_sigma if sp is spec else _full_sigma(xb, 0.3)._replace(
            th=torch.full_like(xb.th, 0.8))
        x0, _ = cvt_apply(xb, sig, torch.zeros((12, 1, 2), **_F64), sp)
        for f in State._fields:
            assert torch.equal(getattr(x0, f), getattr(xb, f)), (f, sp.eps)


def test_sigma0_pins_bitwise_any_v():
    """T4: σ=0 셀은 v=±50에도 배경 고정 bitwise, jac 정확히 0; σ>0 셀은 이동."""
    xb = _mk_state()
    spec = _mul_spec()
    sig = _full_sigma(xb, 0.0)._replace(qc=_t2(0.5, 0.0))   # qc 셀0만 제어
    for vval in (50.0, -50.0):
        v = torch.full((12, 1, 2), vval, **_F64)
        x0, jac = cvt_apply(xb, sig, v, spec)
        for f in State._fields:
            if f == "qc":
                continue
            assert torch.equal(getattr(x0, f), getattr(xb, f)), (f, vval)
        assert torch.equal(x0.qc[0, 1], xb.qc[0, 1])         # σ=0 셀
        assert not torch.equal(x0.qc[0, 0], xb.qc[0, 0])     # σ>0 셀
        assert float(jac[2, 0, 1]) == 0.0
        assert (jac[[0, 1] + list(range(3, 12))] == 0.0).all()


def test_positivity_and_eps_floor():
    """T5: ε=0 → xb>0 셀 x0>0; ε>0 → x0 ≥ −ε−4·U64·(xb+ε) (expm1 포화 포함)."""
    xb = _mk_state()
    sig = _full_sigma(xb, 0.5)
    spec0 = _mul_spec(eps=0.0)
    for vval in (40.0, -40.0):
        x0, _ = cvt_apply(xb, sig, torch.full((12, 1, 2), vval, **_F64), spec0)
        for f in State._fields[1:]:
            xbf, x0f = getattr(xb, f), getattr(x0, f)
            assert bool((x0f[xbf > 0] > 0).all()), (f, vval)
    eps = 1.0e-5
    spec_e = _mul_spec(eps=eps)
    x0, _ = cvt_apply(xb, sig, torch.full((12, 1, 2), -50.0, **_F64), spec_e)
    for f in State._fields[1:]:
        assert bool((getattr(x0, f) > -eps).all()), f
    # expm1(-500) == -1.0 정확히 → 하계는 −ε−(반올림 여유)
    x0, _ = cvt_apply(xb, sig, torch.full((12, 1, 2), -1000.0, **_F64), spec_e)
    for f in State._fields[1:]:
        lo = -eps - 4.0 * U64 * (getattr(xb, f) + eps)
        assert bool((getattr(x0, f) >= lo).all()), f


def test_overflow_raises_floatingpoint():
    """T6: exp 오버플로 → FloatingPointError (θ-CVT 관례)."""
    xb = _mk_state()
    with pytest.raises(FloatingPointError):
        cvt_apply(xb, _full_sigma(xb, 1.0),
                  torch.full((12, 1, 2), 800.0, **_F64), _mul_spec())


def test_jacobian_matches_autograd_oracle():
    """T7: 수동 jac vs autograd 오라클 — 드리프트 감시 (rtol 1e-13, atol 0)."""
    g = torch.Generator().manual_seed(3)
    xb = _mk_state()
    sig = _full_sigma(xb, 0.4)._replace(th=torch.full_like(xb.th, 0.8))
    v = (_rand((12, 1, 2), g).clamp(-5.0, 5.0) / 0.4).clamp(-10.0, 10.0)
    v = v.detach().requires_grad_(True)
    x0, jac = cvt_apply(xb, sig, v, _mul_spec(eps=1.0e-6))
    w = _rand((12, 1, 2), g)
    (torch.stack(list(x0)) * w).sum().backward()
    assert torch.allclose(v.grad, jac * w, rtol=1.0e-13, atol=0.0)


def test_validate_cvt_rejects():
    """T8: 위험 구성 fail-fast — 각 케이스가 ValueError."""
    xb = _mk_state()
    spec = _mul_spec()
    z = _full_sigma(xb, 0.0)

    # (a) σ>0 & xb==0 & ε=0 (qi 셀0이 0)
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(qi=_t2(0.5, 0.5)), spec)
    # (b) σ>0 & xb<0
    xb_neg = xb._replace(qc=_t2(-1.0e-4, 5.0e-4))
    with pytest.raises(ValueError):
        validate_cvt(xb_neg, z._replace(qc=_t2(0.5, 0.5)), spec)
    # (c) σ<0
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(th=torch.full_like(xb.th, -1.0)), spec)
    # (d) σ NaN
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(th=torch.full_like(xb.th, float("nan"))), spec)
    # (e) ni 상한 headroom: xb=1e8, σ=0.3 → xb·e^{0.9} ≥ 1e6
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(ni=_t2(0.0, 0.3)), spec)
    # (f) nccn 하한 headroom: xb=1.1e8 ≈ NCCN_MIN·e^{0.9}/2.24 → 미달
    xb_n = xb._replace(nccn=_t2(1.1e8, 1.1e8))
    with pytest.raises(ValueError):
        validate_cvt(xb_n, z._replace(nccn=torch.full_like(xb.nccn, 0.3)), spec)
    # (g) active_fields에 없는 필드 σ>0
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(qc=_t2(0.5, 0.5)), spec,
                     active_fields=("th",))
    # (h) 생성자 검증
    with pytest.raises(ValueError):
        CvtSpec(mode=("add",) * 11, eps=(0.0,) * 11)            # len 11
    with pytest.raises(ValueError):
        CvtSpec(mode=("bad",) + ("mul",) * 11, eps=(0.0,) * 12)  # bad mode
    with pytest.raises(ValueError):
        CvtSpec(mode=("add",) * 12, eps=(-1.0,) + (0.0,) * 11)   # eps<0
    with pytest.raises(ValueError):
        CvtSpec(mode=("add",) + ("mul",) * 11,
                eps=(1.0e-5,) + (0.0,) * 11)                     # add & eps>0
    # (i) mul σ > 2 (절대단위 σ 오인 방지)
    with pytest.raises(ValueError):
        validate_cvt(xb, z._replace(qc=_t2(5.0, 5.0)), spec)
    # (j) override 오타 키는 조용한 pin 대신 즉시 거부 (default_param_prior 관례)
    with pytest.raises(ValueError, match="unknown"):
        make_default_cvt(xb, sigma_overrides={"q_r": 0.5})
    with pytest.raises(ValueError, match="unknown"):
        make_default_cvt(xb, eps_overrides={"Ni": 1.0e-5})
    # (k) V4 하한의 −ε 항 회귀: 검사값 (xb+ε)e^{−3σ}=1.100e8 > lo 이지만 참
    #     3σ 하강점 (xb+ε)e^{−3σ}−ε = 9.00e7 < NCCN_MIN → 반드시 거부
    xb_k = xb._replace(nccn=torch.full_like(xb.nccn, 2.50556e8))
    spec_k = CvtSpec(mode=("add",) + ("mul",) * 11,
                     eps=(0.0,) * 7 + (2.0e7,) + (0.0,) * 4)   # nccn ε=2e7
    with pytest.raises(ValueError):
        validate_cvt(xb_k, z._replace(nccn=torch.full_like(xb.nccn, 0.3)), spec_k)
    # (l) add-모드 clamp 필드도 headroom 검사 (mul 전용 dead-zone 방지):
    #     ni add σ=5e5, xb=8e5 → xb+3σ=2.3e6 ≥ 1e6
    mode_add_ni = tuple("add" if f in ("th", "ni") else "mul"
                        for f in State._fields)
    spec_add_ni = CvtSpec(mode=mode_add_ni, eps=(0.0,) * 12)
    with pytest.raises(ValueError):
        validate_cvt(xb._replace(ni=_t2(0.0, 8.0e5)),
                     z._replace(ni=_t2(0.0, 5.0e5)), spec_add_ni)
    # (m) 빌더는 범위 밖 override를 스스로 거부 (by-construction 보증의 실체)
    with pytest.raises(ValueError):
        make_default_cvt(xb, sigma_overrides={"qc": 5.0})


def test_spec_fingerprint_and_record_roundtrip():
    """T9: as_dict/from_dict 왕복, fingerprint 안정성/민감성, record JSON 직렬화."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    assert CvtSpec.from_dict(spec.as_dict()) == spec
    assert spec.fingerprint() == spec.fingerprint()
    other = CvtSpec(mode=spec.mode,
                    eps=(0.0, 1.0e-5) + spec.eps[2:])
    assert other.fingerprint() != spec.fingerprint()
    # version 필드는 장식이 아님 — 미래/손상 레코드 fail-fast
    bad = spec.as_dict()
    bad["version"] = 2
    with pytest.raises(ValueError, match="version"):
        CvtSpec.from_dict(bad)
    # ε=−0.0은 +0.0으로 정규화 — 동일 spec은 동일 fingerprint
    s_neg = CvtSpec(mode=("add",) + ("mul",) * 11, eps=(0.0,) + (-0.0,) * 11)
    s_pos = CvtSpec(mode=("add",) + ("mul",) * 11, eps=(0.0,) * 12)
    assert s_neg == s_pos and s_neg.fingerprint() == s_pos.fingerprint()

    v = torch.full((12, 1, 2), 0.1, **_F64)
    x_a, _ = cvt_apply(xb, b_sigma, v, spec)
    rec = build_cvt_record(spec, b_sigma, xb, x_a)
    rec2 = json.loads(json.dumps(rec))
    assert rec2["spec"] == spec.as_dict()
    assert rec2["spec_sha256"] == spec.fingerprint()
    # σ 1바이트 변화 → b_sigma sha 변화
    b2 = b_sigma._replace(th=b_sigma.th + 1.0e-12)
    rec3 = build_cvt_record(spec, b2, xb, x_a)
    assert rec3["b_sigma_sha256"] != rec2["b_sigma_sha256"]


def test_make_default_cvt_rules():
    """T10: 빌더 규칙 — V3/V4 zeroing 자체 적용, validate 통과."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb)
    assert spec.mode[0] == "add" and set(spec.mode[1:]) == {"mul"}
    # ni ≡ 0: 셀0 xb=0(V3), 셀1 xb=1e8 → 1e8·e^{0.9} ≥ 1e6(V4)
    assert float(b_sigma.ni.abs().max()) == 0.0
    # 간접(M^T 전용) 필드 기본 제외
    for f in ("qr", "qg", "nr"):
        assert float(getattr(b_sigma, f).abs().max()) == 0.0, f
    # nccn/bg 기본 제외
    assert float(b_sigma.nccn.abs().max()) == 0.0
    assert float(b_sigma.bg.abs().max()) == 0.0
    # th 전역 0.8, qv>0 셀 0.08, qc는 양배경 셀만 0.5
    assert bool((b_sigma.th == 0.8).all())
    assert bool((b_sigma.qv == 0.08).all())
    assert bool((b_sigma.qc == 0.5).all())
    assert float(b_sigma.qi[0, 0]) == 0.0 and float(b_sigma.qi[0, 1]) == 0.5
    validate_cvt(xb, b_sigma, spec)

    spec_i, b_i = make_default_cvt(xb, enable_indirect=True)
    assert bool((b_i.qr == 0.5).all())
    assert float(b_i.nr[0, 0]) == 0.3 and float(b_i.nr[0, 1]) == 0.3
    validate_cvt(xb, b_i, spec_i)

    # qv_levels: K=2 < 12 → 전 레벨 제어; qv_levels=1 → k=1 제외
    _, b_l = make_default_cvt(xb, qv_levels=1)
    assert float(b_l.qv[0, 0]) == 0.08 and float(b_l.qv[0, 1]) == 0.0

    # override로 nccn opt-in: xb=1e9 → [1e8·e^{0.9}, 2e10·e^{-0.9}] 안 → σ 유지
    _, b_o = make_default_cvt(xb, sigma_overrides={"nccn": 0.3})
    assert bool((b_o.nccn == 0.3).all())
