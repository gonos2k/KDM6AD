"""G4 파라미터 gradient 검증 (계획 §4 — oracle 측만; frozen dylib 무접촉).

게이트:
  1. 기본(frozen) 경로 byte-불변 — live 파라미터 텐서 경로의 forward 값이
     상수 경로와 torch.equal (f32t 캐스트는 struct f32와 IEEE 동일 라운딩).
  2. dJ/dPEAUT: 단일 스텝에서 nonzero + 중앙 FD 대조 (rel < 2e-3 —
     f32-stepwise qck1 계단의 물리적 바닥 ~6e-4에 3× 마진; 테스트 주석 참조).
  3. 창 관통: run_da_window(param_grads=True)의 grad_params["peaut"]가
     창-손실의 FD와 일치 — dJ/dθ = Σ_t ∂⟨M,λ⟩/∂θ 누적의 정당성.
  4. live leaf 없이 param_grad 호출 → 명시적 에러 (조용한 빈 결과 금지).
"""
from __future__ import annotations

import pytest
import torch

from kdm6.da_window import WindowConfig, run_da_window
from kdm6.runtime import Parameters, kdm6_step, make_parameters
from kdm6.state import Forcing, State

DT = 20.0
_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_state(rg=False):
    s = State(
        th=_t2(296.8, 282.4), qv=_t2(1.40e-2, 2.0e-3),
        qc=_t2(1.0e-3, 5.0e-4), qr=_t2(1.0e-4, 1.0e-5),
        qi=_t2(0.0, 1.0e-6), qs=_t2(0.0, 5.0e-5),
        qg=_t2(0.0, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(0.0, 1.0e8),
        nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0),
    )
    if rg:
        s = State(*(f.requires_grad_(True) for f in s))
    return s


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _params_with_peaut(value: float, grad: bool = True) -> Parameters:
    base = make_parameters()
    peaut = torch.tensor(value, **_F64)
    if grad:
        peaut = peaut.requires_grad_(True)
    return base._replace(peaut=peaut)


def test_live_param_forward_is_byte_identical_to_frozen():
    """f32t 텐서 체인의 qck1이 struct-f32 체인과 IEEE 동일 → forward 값 불변."""
    import kdm6.constants as c
    s, f = _mk_state(), _mk_forcing()
    out_frozen, h1 = kdm6_step(s, f, make_parameters(), DT, value_only=True)
    h1.close()
    out_live, h2 = kdm6_step(_mk_state(True), f,
                             _params_with_peaut(c.PEAUT), DT, value_only=False)
    h2.close()
    for k in State._fields:
        assert torch.equal(getattr(out_frozen, k),
                           getattr(out_live, k).detach()), k


def test_dj_dpeaut_single_step_fd():
    """∂(Σ qr_out)/∂PEAUT — autoconv(qc→qr)가 peaut에 직결: nonzero + 중앙 FD.

    허용오차 주의: qck1은 REAL(4) 미러의 f32-stepwise 체인이라 peaut→qck1이
    **f32 계단함수**다 — 해석 gradient는 straight-through 도함수(매끈한 경사),
    FD는 계단의 secant를 표집하므로 rel ≈ f32 ULP/h_rel ≈ 6e-4 (실측 6.2e-4,
    예측과 정확 일치). 2e-3는 그 물리적 바닥의 ~3× 마진이다.
    """
    import kdm6.constants as c
    f = _mk_forcing()

    def loss_at(peaut_value: float, grad: bool):
        params = _params_with_peaut(peaut_value, grad=grad)
        out, h = kdm6_step(_mk_state(grad), f, params, DT, value_only=False)
        j = out.qr.sum()
        if grad:
            g = h.param_grad(j)["peaut"]
            h.close()
            return float(j.detach()), float(g)
        h.close()
        return float(j.detach()), None

    j0, g = loss_at(c.PEAUT, grad=True)
    assert g != 0.0
    h_rel = 1.0e-5 * c.PEAUT
    jp, _ = loss_at(c.PEAUT + h_rel, grad=False)
    jm, _ = loss_at(c.PEAUT - h_rel, grad=False)
    fd = (jp - jm) / (2 * h_rel)
    rel = abs(fd - g) / max(abs(fd), 1e-30)
    assert rel < 2.0e-3, (fd, g, rel)      # f32-계단 바닥(~6e-4)의 3× 마진


def test_dj_dpeaut_through_window_fd():
    """창 누적 dJ/dθ = Σ_t ∂⟨M,λ⟩/∂θ 의 FD 대조 (T=2, J=Σ th_T)."""
    import kdm6.constants as c
    forcings = [_mk_forcing()] * 2
    u_T = State(**{k: (torch.ones_like(_t2(0, 0)) if k == "th"
                       else torch.zeros_like(_t2(0, 0)))
                   for k in State._fields})

    def run(peaut_value: float, grad: bool):
        params = _params_with_peaut(peaut_value, grad=grad)
        cfg = WindowConfig(dt=DT, params=params, param_grads=grad)
        res = run_da_window(_mk_state(), forcings,
                            lambda t, x: u_T if t == 2 else None, cfg)
        j = float(res.state_final.th.sum())
        g = float(res.grad_params["peaut"]) if grad else None
        return j, g

    j0, g = run(c.PEAUT, grad=True)
    assert g != 0.0
    h_rel = 1.0e-5 * c.PEAUT
    jp, _ = run(c.PEAUT + h_rel, grad=False)
    jm, _ = run(c.PEAUT - h_rel, grad=False)
    fd = (jp - jm) / (2 * h_rel)
    rel = abs(fd - g) / max(abs(fd), 1e-30)
    assert rel < 1.0e-3, (fd, g, rel)      # 실측 7.3e-5 (f32-계단), 13× 마진


def test_param_grad_without_live_leaves_raises():
    s, f = _mk_state(True), _mk_forcing()
    out, h = kdm6_step(s, f, make_parameters(), DT, value_only=False)
    with pytest.raises(ValueError, match="no live parameter leaves"):
        h.param_grad(out.qr.sum())
    h.close()
