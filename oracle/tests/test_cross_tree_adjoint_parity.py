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
     zero-패턴까지 일치 — 순수 도함수-레벨 현상, 각 트리는 자기 경로의
     branch-local derivative를 반환한다. 이는 cross-tree subgradient 동등성의
     증거가 아니다.)
     이 fixture에서 발자국 밖 성분은 < 1e-6이다. 발자국의 축소·확대와
     허용 슬롯의 측정 부호·크기 변화 모두 회귀 실패로 재검토한다.

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

# Read-only RED baseline for this exact fixture, seed and dylib. These values
# are the measured branch footprint, not a physical tolerance or subgradient
# claim. Keep signs and scales pinned so a changed allowed branch is reviewed.
MEASURED_ALLOWED = {
    "vjp": {
        ("ni", 0): {"cpp": 0.0, "oracle": 0.0, "rel": 0.0},
        ("bg", 0): {"cpp": 48909422578990.82, "oracle": 0.0, "rel": 1.0},
    },
    "jvp": {
        ("th", 0): {"cpp": -2067.1913439583323,
                    "oracle": -2064.4295244888754,
                    "rel": 0.0006684590763273189},
        ("qv", 0): {"cpp": -1.727533464952994,
                    "oracle": -1.7258161125491709,
                    "rel": 0.0004973004803832738},
        ("qc", 0): {"cpp": -57.05733815982653,
                    "oracle": 1.095774627642209, "rel": 1.0},
        ("qr", 0): {"cpp": 36.01399733806218,
                    "oracle": -2.331352737248958, "rel": 1.0},
        ("nc", 0): {"cpp": -30127885847896.992,
                    "oracle": 1097358516434.8701, "rel": 1.0},
        ("nr", 0): {"cpp": -30725894546.339634,
                    "oracle": 1028565534.7053764, "rel": 1.0},
    },
}


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


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf],
                         ids=["nan", "posinf", "neginf"])
@pytest.mark.parametrize("side", ["cpp", "oracle"])
def test_allowed_huge_slot_injection_is_rejected(bad, side):
    """Non-finite values cannot hide in the measured large VJP footprint."""
    measured = MEASURED_ALLOWED["vjp"][("bg", 0)]
    left = np.array([measured["cpp"]], dtype=np.float64)
    right = np.array([measured["oracle"]], dtype=np.float64)
    (left if side == "cpp" else right)[0] = bad
    with pytest.raises(AssertionError, match="relative"):
        _rel(left, right)


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
def test_cross_tree_divergence_footprint_pinned():
    """dt=300 (3 subcycles): 미분-레벨 kink 발산의 **발자국 회귀 스냅샷**.

    실측 사실(이 IC/시드): forward 출력은 zero-패턴까지 두 트리 일치하지만,
    내부 subcycle 게이트의 분기 선택이 트리별로 달라(값 영향은 무시 가능,
    도함수 구조는 상이) 파생 산물이 cell 0에서 갈라진다:
      - VJP: 입력-0 저장고 성분 {ni, bg}@cell0 만 (one-sided branch derivative).
      - JVP: cell0의 {qc, qr, nc, nr} (이 snapshot에서 유한한 비영값끼리
        부호가 달라 rel=1) + {th, qv} (rel ~ 5e-4 — 셀 내 knock-on).
    forward-관측 가능한 판별자는 없다(zero-패턴 일치 확인됨) — 그래서 이
    테스트는 물리 법칙이 아니라 **발자국 고정**이다: 집합이 줄면(개선) 통과,
    늘거나 줄면(회귀) 실패해 재검토를 강제한다. 허용 슬롯의 측정 부호와
    크기도 함께 고정하며, 이 결과를 다른 fixture나 일반 subgradient 계약으로
    확장하지 않는다. 발자국 밖 전 성분은 이 fixture에서 < 1e-6이다.

    DA 소비 규칙: 사이클은 한 트리로 자기일관되게 (증분 계산과 적용을 같은
    트리에서); 이 fixture의 dt=20 smooth 측정만 cross-tree rel<1e-6으로
    확인되었으며, 다른 branch나 fixture에 대한 안전성 주장은 하지 않는다.
    """
    rng = np.random.default_rng(7)
    u, v = rng.standard_normal(12 * N), rng.standard_normal(12 * N)
    g_c, t_c = _cpp_products(300.0, u, v)
    g_o, t_o = _oracle_products(300.0, u, v)

    ALLOWED = {tag: set(values) for tag, values in MEASURED_ALLOWED.items()}
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
        for (field, cell), expected in MEASURED_ALLOWED[tag].items():
            index = FIELDS.index(field) * N + cell
            np.testing.assert_allclose(
                a[index], expected["cpp"], rtol=TOL, atol=1.0e-12,
                err_msg=f"{tag} {field}[{cell}] C++ measured magnitude changed")
            np.testing.assert_allclose(
                b[index], expected["oracle"], rtol=TOL, atol=1.0e-12,
                err_msg=f"{tag} {field}[{cell}] oracle measured magnitude changed")
            if expected["cpp"] != 0.0:
                assert np.signbit(a[index]) == np.signbit(expected["cpp"]), (
                    f"{tag} {field}[{cell}] C++ sign changed")
            if expected["oracle"] != 0.0:
                assert np.signbit(b[index]) == np.signbit(expected["oracle"]), (
                    f"{tag} {field}[{cell}] oracle sign changed")
            np.testing.assert_allclose(
                r[index], expected["rel"], rtol=TOL, atol=1.0e-12,
                err_msg=f"{tag} {field}[{cell}] measured relative scale changed")


@pytest.mark.parametrize("bad", [1.0e300, -48909422578990.82, 97818845157981.64],
                         ids=["huge_finite", "sign_flip", "double_magnitude"])
@pytest.mark.parametrize("backend", ["cpp", "oracle"])
def test_allowed_finite_corruption_fails_actual_footprint_gate(monkeypatch, bad, backend):
    """An unchanged allowed location cannot hide a changed finite product."""
    products = {name: {tag: np.zeros(12 * N) for tag in MEASURED_ALLOWED}
                for name in ("cpp", "oracle")}
    for tag, entries in MEASURED_ALLOWED.items():
        for (field, cell), values in entries.items():
            index = FIELDS.index(field) * N + cell
            for name in products:
                products[name][tag][index] = values[name]
    products[backend]["vjp"][FIELDS.index("bg") * N] = bad
    for name in products:
        monkeypatch.setattr(sys.modules[__name__], f"_{name}_products",
                            lambda *_args, name=name: (
                                products[name]["vjp"], products[name]["jvp"]))
    with pytest.raises(AssertionError, match="measured magnitude changed"):
        test_cross_tree_divergence_footprint_pinned()
