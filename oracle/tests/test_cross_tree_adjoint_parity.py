"""Cross-tree ADJOINT parity — C++ fp64(kdm6_step_ad_c) vs 오라클 Handle (계획 §4).

감사가 지적한 MAJOR 갭의 게이트: 조인트 DA는 한 트리의 gradient로 증분을 만들어
다른 트리의 궤적에 적용한다 — forward parity(1e-6 bound)만으로는 gradient 수준
일치가 보증되지 않는다("forward parity는 kink의 subgradient parity를 함의하지
않는다"). 이 테스트가 실측으로 고정하는 계약:

  1. SMOOTH 점 (dt=20, 단일 subcycle, _G_BASE IC): VJP/JVP 전 성분 cross-tree
     worst_rel < 1e-6 (실측 ~5e-8).
  2. 다중 subcycle (dt=300, loops=3): 미분-레벨 kink 발산이 존재하며 그
     **발자국을 회귀 스냅샷으로 고정**한다 — VJP는 입력-0 저장고 {ni,bg}@cell0,
     JVP는 cell0의 {qc,qr,nc,nr}(rel~1) + {th,qv}(knock-on ~5e-4). 원인: 중간
     상태의 ~1e-8 차이가 내부 게이트 분기를 트리별로 뒤집음(forward 출력은
     zero-패턴까지 일치 — 순수 도함수-레벨 현상, 둘 다 유효한 subgradient).
     발자국 밖 전 성분은 < 1e-6; 발자국 확대는 테스트 실패로 재검토 강제.

DA 소비 규칙(이 계약의 실무 귀결): 입력-0 저장고 필드는 σ_b=0/active_fields로
제어에서 제외하거나 one-sided임을 감수한다 — da_minimizer의 CVT σ=0 제외가
정확히 그 장치다.

게이트: 빌드된 dylib 필요 (없으면 skip; port-ci가 빌드 후 이 파일도 실행 가능).
"""
from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.runtime import kdm6_step, make_parameters
from kdm6.state import Forcing, State

_REPO = Path(__file__).resolve().parents[2]
_DYLIB = _REPO / "libtorch" / "build" / "libkdm6_c.dylib"
needs_dylib = pytest.mark.skipif(not _DYLIB.exists(),
                                 reason="libkdm6_c.dylib not built")

FIELDS = State._fields
G_BASE = dict(th=(296.8, 282.4), qv=(1.40e-2, 2.0e-3), qc=(1.0e-3, 5.0e-4),
              qr=(1.0e-4, 1.0e-5), qi=(0.0, 1.0e-6), qs=(0.0, 5.0e-5),
              qg=(0.0, 1.0e-5), nccn=(1.0e9, 1.0e9), nc=(1.0e8, 1.0e8),
              ni=(0.0, 1.0e8), nr=(1.0e4, 1.0e3), bg=(0.0, 0.0))
G_F = dict(rho=(1.089, 0.9567), pii=(0.9704, 0.9031),
           p=(9.0e4, 7.0e4), delz=(500.0, 500.0))
IM, KME, JME = 1, 2, 1
N = IM * KME * JME
TOL = 1.0e-6                       # forward regression bound와 동일 등급


def _lib():
    lib = ctypes.CDLL(str(_DYLIB))
    d = ctypes.POINTER(ctypes.c_double)
    lib.kdm6_step_ad_c.restype = ctypes.c_int
    lib.kdm6_step_ad_c.argtypes = [
        d, d, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_double,
        ctypes.c_int, d, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_float), ctypes.c_double, ctypes.c_double]
    lib.kdm6_handle_vjp_c.restype = ctypes.c_int
    lib.kdm6_handle_vjp_c.argtypes = [ctypes.c_void_p, d, d]
    lib.kdm6_handle_jvp_c.restype = ctypes.c_int
    lib.kdm6_handle_jvp_c.argtypes = [ctypes.c_void_p, d, d]
    lib.kdm6_handle_closep_c.restype = ctypes.c_int
    lib.kdm6_handle_closep_c.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    return lib, d


def _cpp_products(dt: float, u_np: np.ndarray, v_np: np.ndarray):
    """C++ fp64 경로: packed VJP/JVP."""
    lib, d = _lib()
    pack = lambda spec, keys: np.ascontiguousarray(
        np.concatenate([np.array(spec[f], dtype=np.float64) for f in keys]))
    x = pack(G_BASE, FIELDS)
    f = pack(G_F, ("rho", "pii", "p", "delz"))
    xo = np.empty(12 * N)
    g = np.empty(12 * N)
    tg = np.empty(12 * N)
    h = ctypes.c_void_p()
    P = lambda a: a.ctypes.data_as(d)
    assert lib.kdm6_step_ad_c(P(x), P(f), IM, KME, JME, dt, 0, P(xo),
                              ctypes.byref(h), None, 1e-2, 1e-2) == 0
    assert h.value
    assert lib.kdm6_handle_vjp_c(h, P(u_np), P(g)) == 0
    assert lib.kdm6_handle_jvp_c(h, P(v_np), P(tg)) == 0
    lib.kdm6_handle_closep_c(ctypes.byref(h))
    return g, tg


def _oracle_products(dt: float, u_np: np.ndarray, v_np: np.ndarray):
    t2 = lambda ab: torch.tensor([list(ab)], dtype=torch.float64)
    leaves = State(**{k: t2(G_BASE[k]).requires_grad_(True) for k in FIELDS})
    fc = Forcing(**{k: t2(G_F[k]) for k in ("rho", "pii", "p", "delz")})
    _, hd = kdm6_step(leaves, fc, make_parameters(), dt, value_only=False)
    mk = lambda arr: State(*(torch.tensor(arr[i * N:(i + 1) * N],
                                          dtype=torch.float64).reshape(1, KME)
                             for i in range(12)))
    g = hd.vjp(mk(u_np), retain_graph=True)
    tg = hd.jvp(mk(v_np))
    hd.close()
    cat = lambda st: np.concatenate(
        [getattr(st, fld).detach().numpy().reshape(-1) for fld in FIELDS])
    return cat(g), cat(tg)


def _rel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    s = np.abs(a) + np.abs(b)
    r = np.zeros_like(a)
    m = s > 1e-300
    r[m] = np.abs(a - b)[m] / s[m]
    return r


def _input_zero_mask() -> np.ndarray:
    """입력 상태가 정확히 0인 (field, cell) 성분 — kink 허용 집합."""
    x = np.concatenate([np.array(G_BASE[f], dtype=np.float64) for f in FIELDS])
    return x == 0.0


@needs_dylib
def test_cross_tree_parity_smooth_point():
    """dt=20 (단일 subcycle): 전 성분 VJP/JVP cross-tree < 1e-6 (실측 ~5e-8)."""
    rng = np.random.default_rng(7)
    u, v = rng.standard_normal(12 * N), rng.standard_normal(12 * N)
    g_c, t_c = _cpp_products(20.0, u, v)
    g_o, t_o = _oracle_products(20.0, u, v)
    assert _rel(g_c, g_o).max() < TOL, f"vjp worst_rel {_rel(g_c, g_o).max():.3e}"
    assert _rel(t_c, t_o).max() < TOL, f"jvp worst_rel {_rel(t_c, t_o).max():.3e}"


@needs_dylib
def test_cross_tree_divergence_footprint_pinned():
    """dt=300 (3 subcycles): 미분-레벨 kink 발산의 **발자국 회귀 스냅샷**.

    실측 사실(이 IC/시드): forward 출력은 zero-패턴까지 두 트리 일치하지만,
    내부 subcycle 게이트의 분기 선택이 트리별로 달라(값 영향은 무시 가능,
    도함수 구조는 상이) 파생 산물이 cell 0에서 갈라진다:
      - VJP: 입력-0 저장고 성분 {ni, bg}@cell0 만 (one-sided subgradient).
      - JVP: cell0의 {qc, qr, nc, nr} (rel~1, 한 트리 경로 기여 0) +
        {th, qv} (rel ~ 5e-4 — 셀 내 knock-on).
    forward-관측 가능한 판별자는 없다(zero-패턴 일치 확인됨) — 그래서 이
    테스트는 물리 법칙이 아니라 **발자국 고정**이다: 집합이 줄면(개선) 통과,
    늘면(회귀) 실패해 재검토를 강제한다. 발자국 밖 전 성분은 < 1e-6.

    DA 소비 규칙: 사이클은 한 트리로 자기일관되게 (증분 계산과 적용을 같은
    트리에서); 트리 교차는 smooth 성분에서만 안전 (~1e-7).
    """
    rng = np.random.default_rng(7)
    u, v = rng.standard_normal(12 * N), rng.standard_normal(12 * N)
    g_c, t_c = _cpp_products(300.0, u, v)
    g_o, t_o = _oracle_products(300.0, u, v)

    ALLOWED = {
        "vjp": {("ni", 0), ("bg", 0)},
        "jvp": {("qc", 0), ("qr", 0), ("nc", 0), ("nr", 0),
                ("th", 0), ("qv", 0)},
    }
    for tag, a, b in (("vjp", g_c, g_o), ("jvp", t_c, t_o)):
        r = _rel(a, b)
        divergent = {(FIELDS[i // N], i % N) for i in np.where(r > TOL)[0]}
        extra = divergent - ALLOWED[tag]
        assert not extra, (
            f"{tag}: divergence footprint GREW beyond the pinned kink set — "
            f"new components {sorted(extra)} (re-review required; "
            f"full rel map {[(FIELDS[i // N], i % N, float(r[i])) for i in np.where(r > TOL)[0]]})")
        ok = np.ones_like(r, dtype=bool)
        for i in range(r.size):
            if (FIELDS[i // N], i % N) in ALLOWED[tag]:
                ok[i] = False
        assert r[ok].max() < TOL, f"{tag} smooth-part worst {r[ok].max():.3e}"
