"""Cross-tree ADJOINT parity — C++ fp64(kdm6_step_ad_c) vs 오라클 Handle (계획 §4).

감사가 지적한 MAJOR 갭의 게이트: 조인트 DA는 한 트리의 gradient로 증분을 만들어
다른 트리의 궤적에 적용한다 — forward parity(1e-6 bound)만으로는 gradient 수준
일치가 보증되지 않는다("forward parity는 kink의 subgradient parity를 함의하지
않는다"). 이 테스트가 실측으로 고정하는 계약:

  1. SMOOTH 점 (dt=20, 단일 subcycle, _G_BASE IC): VJP/JVP 전 성분 cross-tree
     worst_rel < 1e-6 (실측 ~5e-8).
  2. 다중 subcycle (dt=300, loops=3): 같은 고정 fixture의 VJP/JVP 전 성분
     cross-tree worst_rel < 1e-6. Python runtime이 ProgB의 volume-only 활성
     출력을 침강 전에 버리던 중복 게이트를 제거한 뒤, 이전에 별도 허용했던
     cell0 발자국도 이 fixture에서는 사라졌다. 다른 분기나 입력의 미분
     동등성으로 확대하지 않는다.

DA 소비 규칙(이 계약의 실무 귀결): 입력-0 저장고 필드는 σ_b=0/active_fields로
제어에서 제외하거나 one-sided임을 감수한다 — da_minimizer의 CVT σ=0 제외가
정확히 그 장치다.

게이트: 빌드된 dylib 필요 (없으면 skip; port-ci가 빌드 후 이 파일도 실행 가능).
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
from typing import Optional

import numpy as np
import pytest
import torch

from kdm6.runtime import kdm6_step, make_parameters
from kdm6.state import Forcing, State

_REPO = Path(__file__).resolve().parents[2]


def _built_library() -> Optional[Path]:
    """Return the real library produced by this checkout's CMake build.

    The explicit override is useful for CI and for consumers with an out of
    tree build.  Otherwise prefer the versioned real file over a development
    symlink, on both ELF and Mach-O platforms; this keeps the test tied to the
    artifact just built rather than an unrelated installed library.
    """
    override = os.environ.get("KDM6_C_LIBRARY")
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise RuntimeError(f"KDM6_C_LIBRARY does not name a file: {path}")
        return path.resolve()

    build = _REPO / "libtorch" / "build"
    names = (
        "libkdm6_c.so.2.0.0",       # Linux VERSION 2.0.0 real file
        "libkdm6_c.2.0.0.dylib",    # macOS VERSION 2.0.0 real file
        "libkdm6_c.so",
        "libkdm6_c.dylib",
    )
    for name in names:
        path = build / name
        if path.is_file():
            return path.resolve()
    return None


_LIBRARY = _built_library()
needs_library = pytest.mark.skipif(
    _LIBRARY is None,
    reason="libkdm6_c shared library is not built (set KDM6_C_LIBRARY to override)",
)

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
    assert _LIBRARY is not None
    lib = ctypes.CDLL(str(_LIBRARY))
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
    _assert_finite("C++ forward", xo)
    _assert_finite("C++ VJP", g)
    _assert_finite("C++ JVP", tg)
    return g, tg


def _oracle_products(dt: float, u_np: np.ndarray, v_np: np.ndarray):
    t2 = lambda ab: torch.tensor([list(ab)], dtype=torch.float64)
    leaves = State(**{k: t2(G_BASE[k]).requires_grad_(True) for k in FIELDS})
    fc = Forcing(**{k: t2(G_F[k]) for k in ("rho", "pii", "p", "delz")})
    out, hd = kdm6_step(leaves, fc, make_parameters(), dt, value_only=False)
    mk = lambda arr: State(*(torch.tensor(arr[i * N:(i + 1) * N],
                                          dtype=torch.float64).reshape(1, KME)
                             for i in range(12)))
    g = hd.vjp(mk(u_np), retain_graph=True)
    tg = hd.jvp(mk(v_np))
    hd.close()
    cat = lambda st: np.concatenate(
        [getattr(st, fld).detach().numpy().reshape(-1) for fld in FIELDS])
    forward = cat(out)
    vjp = cat(g)
    jvp = cat(tg)
    _assert_finite("oracle forward", forward)
    _assert_finite("oracle VJP", vjp)
    _assert_finite("oracle JVP", jvp)
    return vjp, jvp


def _assert_finite(label: str, values: np.ndarray) -> None:
    values = np.asarray(values)
    assert np.isfinite(values).all(), (
        f"{label} contains non-finite values at "
        f"{np.flatnonzero(~np.isfinite(values)).tolist()}")


def _rel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Symmetric relative error with explicit non-finite rejection.

    Scale before subtraction so finite extreme values cannot overflow in the
    denominator or numerator. Non-finite inputs are rejected before scoring.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"relative-error shape mismatch: {a.shape} != {b.shape}")
    _assert_finite("relative lhs", a)
    _assert_finite("relative rhs", b)
    r = np.zeros_like(a)
    scale = np.maximum(np.abs(a), np.abs(b))
    nonzero = scale > 0.0
    a_scaled = np.divide(a, scale, out=np.zeros_like(a), where=nonzero)
    b_scaled = np.divide(b, scale, out=np.zeros_like(b), where=nonzero)
    denom = np.abs(a_scaled) + np.abs(b_scaled)
    comparable = denom > 0.0
    r[comparable] = (np.abs(a_scaled[comparable] - b_scaled[comparable]) /
                      denom[comparable])
    return r


def _input_zero_mask() -> np.ndarray:
    """입력 상태가 정확히 0인 (field, cell) 성분 — kink 허용 집합."""
    x = np.concatenate([np.array(G_BASE[f], dtype=np.float64) for f in FIELDS])
    return x == 0.0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf],
                         ids=["nan", "posinf", "neginf"])
@pytest.mark.parametrize("side", ["left", "right"])
def test_relative_gate_rejects_nonfinite_injected_products(bad, side):
    """Non-finite injections must fail the gate without a native library."""
    left = np.array([1.0, -2.0, 0.0], dtype=np.float64)
    right = np.array([1.0, -2.0, 0.0], dtype=np.float64)
    (left if side == "left" else right)[1] = bad
    with pytest.raises(AssertionError, match="relative"):
        _rel(left, right)


def test_relative_gate_scales_finite_extremes_before_subtraction():
    """Finite 1e308 products remain comparable without intermediate overflow."""
    left = np.array([1.0e308, -1.0e308, 1.0e300, 0.0], dtype=np.float64)
    right = np.array([1.0e308, 1.0e308, 1.0, 0.0], dtype=np.float64)
    relative = _rel(left, right)
    assert np.isfinite(relative).all()
    assert relative[0] == 0.0
    assert relative[1] == 1.0
    assert 0.999999999999 < relative[2] <= 1.0
    assert relative[3] == 0.0


class _FakeCppLibrary:
    def __init__(self, kind, bad):
        self.kind = kind
        self.bad = bad

    @staticmethod
    def _array(pointer):
        return np.ctypeslib.as_array(pointer, shape=(12 * N,))

    def kdm6_step_ad_c(self, _x, _f, _im, _kme, _jme, _dt, _flag,
                       xo, handle, _aux, _a, _b):
        self._array(xo).fill(0.0)
        if self.kind == "forward":
            self._array(xo)[0] = self.bad
        handle._obj.value = 1
        return 0

    def kdm6_handle_vjp_c(self, _handle, _u, gradient):
        self._array(gradient).fill(0.0)
        if self.kind == "vjp":
            self._array(gradient)[0] = self.bad
        return 0

    def kdm6_handle_jvp_c(self, _handle, _v, tangent):
        self._array(tangent).fill(0.0)
        if self.kind == "jvp":
            self._array(tangent)[0] = self.bad
        return 0

    @staticmethod
    def kdm6_handle_closep_c(handle):
        handle._obj.value = None
        return 0


def _fake_state(value=0.0):
    fields = []
    for _ in FIELDS:
        value_field = torch.zeros((1, KME), dtype=torch.float64)
        value_field[0, 0] = value
        fields.append(value_field)
    return State(*fields)


class _FakeOracleHandle:
    def __init__(self, kind, bad):
        self.kind = kind
        self.bad = bad

    def vjp(self, _seed, retain_graph=True):
        del retain_graph
        return _fake_state(self.bad if self.kind == "vjp" else 0.0)

    def jvp(self, _tangent):
        return _fake_state(self.bad if self.kind == "jvp" else 0.0)

    def close(self):
        return None


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf],
                         ids=["nan", "posinf", "neginf"])
@pytest.mark.parametrize("kind", ["forward", "vjp", "jvp"])
@pytest.mark.parametrize("backend", ["cpp", "oracle"])
def test_product_boundaries_reject_nonfinite_without_native_library(
        monkeypatch, bad, kind, backend):
    """Each real product boundary rejects injected non-finite output."""
    if backend == "cpp":
        fake = _FakeCppLibrary(kind, bad)
        monkeypatch.setattr(
            sys.modules[__name__], "_lib",
            lambda: (fake, ctypes.POINTER(ctypes.c_double)),
        )
        with pytest.raises(AssertionError, match="non-finite"):
            _cpp_products(20.0, np.zeros(12 * N), np.zeros(12 * N))
    else:
        fake = _FakeOracleHandle(kind, bad)
        monkeypatch.setattr(
            sys.modules[__name__], "kdm6_step",
            lambda *_args, **_kwargs: (
                _fake_state(bad if kind == "forward" else 0.0), fake),
        )
        with pytest.raises(AssertionError, match="non-finite"):
            _oracle_products(20.0, np.zeros(12 * N), np.zeros(12 * N))


@needs_library
def test_cross_tree_parity_smooth_point():
    """dt=20 (단일 subcycle): 전 성분 VJP/JVP cross-tree < 1e-6 (실측 ~5e-8)."""
    rng = np.random.default_rng(7)
    u, v = rng.standard_normal(12 * N), rng.standard_normal(12 * N)
    g_c, t_c = _cpp_products(20.0, u, v)
    g_o, t_o = _oracle_products(20.0, u, v)
    assert _rel(g_c, g_o).max() < TOL, f"vjp worst_rel {_rel(g_c, g_o).max():.3e}"
    assert _rel(t_c, t_o).max() < TOL, f"jvp worst_rel {_rel(t_c, t_o).max():.3e}"


@needs_library
def test_cross_tree_parity_three_subcycles():
    """All state VJP/JVP components agree on the fixed dt=300 fixture."""
    rng = np.random.default_rng(7)
    u, v = rng.standard_normal(12 * N), rng.standard_normal(12 * N)
    g_c, t_c = _cpp_products(300.0, u, v)
    g_o, t_o = _oracle_products(300.0, u, v)
    assert _rel(g_c, g_o).max() < TOL, f"vjp worst_rel {_rel(g_c, g_o).max():.3e}"
    assert _rel(t_c, t_o).max() < TOL, f"jvp worst_rel {_rel(t_c, t_o).max():.3e}"
