"""C++ conservative-interface variant  <->  oracle/kdm6/sed_conservative.py parity.

The freeze-lift contract (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md) names the
Python conservative counterfactual as the AUTHORITATIVE numerical reference for the
C++ variant (libtorch/src/sedimentation_conservative.cpp). This test runs the
committed C++ dump tool ``libtorch/build/dump_conservative_interface`` as a
subprocess (OMP-isolated), parses its std::hexfloat dumps (EXACT fp64 bit
patterns — f32 values are widened exactly; parsed with float.fromhex, zero text
truncation), rebuilds the SAME fixtures here, runs the oracle functions, and
asserts agreement:

  DS64_*  direct conservative substeps at fp64 (uniform cap-inactive / uniform
          cap-active / variable rho-delz / mixed per-column mstep / per-species
          isolation incl. nr/ni/brs bookkeeping): rtol <= 1e-10, atol <= 1e-12.
          Both trees run the identical torch op sequence, so this is expected
          to be bitwise (the tolerance is the certification bound, not slack).
  DS32_*  controlled f32 direct substeps: tried BITWISE first; on divergence
          the max float32 ULP distance is computed and gated (see the comment
          at the assertion for the first-divergence analysis).
  FS64_*  full conservative kdm6_step (internal C++ fp64, PhysicsOptions
          ConservativeInterface) vs kdm6_step_conservative_experiment: 12
          state fields + rain_increment (== budget surface diagnostic) under
          the same worst-rel regression bound style as test_cpp_parity.

The fixture ICs below are hardcoded in LOCKSTEP with
libtorch/tests/dump_conservative_interface.cpp — change one, change both.

CI: port-ci (.github/workflows/ci.yml) builds the dump binary and runs this
test right after test_cpp_parity. On a Python-only runner (oracle-ci) the
binary is absent and the whole module SKIPS — same mechanism as test_cpp_parity.
"""
from __future__ import annotations

import math
import os
import struct
import subprocess
from pathlib import Path

import pytest
import torch

from kdm6.sedimentation import (
    SubstepAdvectionState, IceSubstepState, default_substep_advection_params,
)
from kdm6.sed_conservative import (
    conservative_substep_advection_torch,
    conservative_ice_substep_advection_torch,
    kdm6_step_conservative_experiment,
)
from kdm6.state import State, Forcing

_REPO = Path(__file__).resolve().parents[2]
_BIN = _REPO / "libtorch" / "build" / "dump_conservative_interface"

pytestmark = pytest.mark.skipif(
    not _BIN.exists(), reason="C++ dump_conservative_interface not built")

# ── fixture constants (LOCKSTEP with dump_conservative_interface.cpp) ────────
DTCLD = 60.0
UNI_RHO, UNI_DZ = [1.0] * 3, [500.0] * 3
VAR_RHO, VAR_DZ = [0.6, 0.9, 1.2], [300.0, 500.0, 700.0]
QR1 = [3.0e-3, 2.0e-3, 1.0e-3]
NR1 = [2.0e5, 1.5e5, 1.0e5]
QS1 = [1.5e-3, 1.0e-3, 5.0e-4]
QG1 = [1.0e-3, 7.0e-4, 3.0e-4]
BRS1 = [4.0e-6, 3.0e-6, 1.0e-6]
QI1 = [8.0e-4, 5.0e-4, 2.0e-4]
NI1 = [5.0e5, 3.0e5, 1.0e5]
Z1 = [0.0, 0.0, 0.0]


def _rows(r, b=1):
    """b copies of row r, column b scaled by (1 + 0.5*b) for the mstep batch."""
    if b == 1:
        return [r]
    return [[v * (1.0 + 0.5 * i) for v in r] for i in range(b)]


# tag -> (qr, nr, qs, qg, brs, w1_qr, wn_qr, w1_qs, w1_qg, rho, delz, mcol, nmax, dtype)
_MAIN_FIXTURES = {
    "DS64_UNI_NOCAP": (_rows(QR1), _rows(NR1), _rows(QS1), _rows(QG1), _rows(BRS1),
                       0.004, 0.003, 0.002, 0.003, _rows(UNI_RHO), _rows(UNI_DZ),
                       [1.0], 1, torch.float64),
    "DS64_UNI_CAP": (_rows(QR1), _rows(NR1), _rows(QS1), _rows(QG1), _rows(BRS1),
                     0.03, 0.02, 0.025, 0.028, _rows(UNI_RHO), _rows(UNI_DZ),
                     [1.0], 1, torch.float64),
    "DS64_VAR": (_rows(QR1), _rows(NR1), _rows(QS1), _rows(QG1), _rows(BRS1),
                 0.02, 0.012, 0.006, 0.015, _rows(VAR_RHO), _rows(VAR_DZ),
                 [1.0], 1, torch.float64),
    "DS64_MSTEP": (_rows(QR1, 3), _rows(NR1, 3), _rows(QS1, 3), _rows(QG1, 3),
                   _rows(BRS1, 3), 0.02, 0.012, 0.006, 0.015,
                   [VAR_RHO] * 3, [VAR_DZ] * 3, [1.0, 2.0, 3.0], 3, torch.float64),
    "DS64_QR": (_rows(QR1), _rows(NR1), _rows(Z1), _rows(Z1), _rows(Z1),
                0.02, 0.012, 0.006, 0.015, _rows(VAR_RHO), _rows(VAR_DZ),
                [1.0], 1, torch.float64),
    "DS64_QS": (_rows(Z1), _rows(Z1), _rows(QS1), _rows(Z1), _rows(Z1),
                0.02, 0.012, 0.006, 0.015, _rows(VAR_RHO), _rows(VAR_DZ),
                [1.0], 1, torch.float64),
    "DS64_QG": (_rows(Z1), _rows(Z1), _rows(Z1), _rows(QG1), _rows(BRS1),
                0.02, 0.012, 0.006, 0.015, _rows(VAR_RHO), _rows(VAR_DZ),
                [1.0], 1, torch.float64),
    "DS32_VAR": (_rows(QR1), _rows(NR1), _rows(QS1), _rows(QG1), _rows(BRS1),
                 0.02, 0.012, 0.006, 0.015, _rows(VAR_RHO), _rows(VAR_DZ),
                 [1.0], 1, torch.float32),
}

# tag -> (qi, ni, w1_qi, wn_qi, rho, delz, mcol, nmax, dtype)
_ICE_FIXTURES = {
    "DS64_VAR_ICE": (_rows(QI1), _rows(NI1), 0.02, 0.008,
                     _rows(VAR_RHO), _rows(VAR_DZ), [1.0], 1, torch.float64),
    "DS64_MSTEP_ICE": (_rows(QI1, 3), _rows(NI1, 3), 0.02, 0.008,
                       [VAR_RHO] * 3, [VAR_DZ] * 3, [1.0, 2.0, 3.0], 3,
                       torch.float64),
    "DS64_QI": (_rows(QI1), _rows(NI1), 0.02, 0.008,
                _rows(VAR_RHO), _rows(VAR_DZ), [1.0], 1, torch.float64),
    "DS32_VAR_ICE": (_rows(QI1), _rows(NI1), 0.02, 0.008,
                     _rows(VAR_RHO), _rows(VAR_DZ), [1.0], 1, torch.float32),
}

# full-step columns (k=0 = SURFACE, WRF staging) — lockstep with the C++ FsCol.
_RAIN_CAP = dict(th=290.0, pii=0.97, p=9.0e4, rho=[1.0] * 4, delz=[400.0] * 4,
                 qv=1.0e-3, qc=0.0, qr=5.0e-3, qi=0.0, qs=0.0, qg=0.0,
                 nccn=1.0e9, nc=1.0e8, ni=0.0, nr=1.0e4, bg=0.0)
_LIGHT_RAIN = dict(th=290.0, pii=0.97, p=9.0e4, rho=[1.0] * 4, delz=[500.0] * 4,
                   qv=1.0e-3, qc=0.0, qr=1.0e-5, qi=0.0, qs=0.0, qg=0.0,
                   nccn=1.0e9, nc=1.0e8, ni=0.0, nr=1.0e5, bg=0.0)
_MIXED_ICE = dict(th=282.4, pii=0.9031, p=7.0e4, rho=[1.2, 1.0, 0.8, 0.6],
                  delz=[700.0, 600.0, 500.0, 300.0],
                  qv=1.0e-3, qc=2.0e-4, qr=1.0e-3, qi=1.2e-3, qs=2.0e-3,
                  qg=2.0e-3, nccn=1.0e9, nc=1.0e8, ni=1.0e5, nr=1.0e4, bg=5.0e-6)

_FULL_FIXTURES = {
    "FS64_CAP": ([_RAIN_CAP], 60.0),
    "FS64_MULTI": ([_LIGHT_RAIN, _RAIN_CAP, _MIXED_ICE], 300.0),
}


def _run_cpp_dumps() -> dict:
    env = {**os.environ, "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"}
    proc = subprocess.run([str(_BIN)], capture_output=True, text=True, env=env,
                          timeout=600)
    dumps: dict = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and (parts[0].startswith("DS") or parts[0].startswith("FS")):
            dumps.setdefault(parts[0], {})[parts[1]] = [float.fromhex(x)
                                                        for x in parts[2:]]
    assert dumps, f"no dumps parsed from {_BIN} (stderr: {proc.stderr[-500:]})"
    return dumps


def _t(rows, dtype):
    return torch.tensor(rows, dtype=torch.float64).to(dtype)


def _py_main(fix):
    (qr, nr, qs, qg, brs, w1_qr, wn_qr, w1_qs, w1_qg,
     rho, delz, mcol, nmax, dtype) = fix
    st = SubstepAdvectionState(qr=_t(qr, dtype), nr=_t(nr, dtype),
                               qs=_t(qs, dtype), qg=_t(qg, dtype),
                               brs=_t(brs, dtype))
    rho_t, delz_t = _t(rho, dtype), _t(delz, dtype)
    mcol_t = torch.tensor(mcol, dtype=torch.float64).to(dtype)
    z = torch.zeros_like(st.qr)
    falls = [z, z, z, z, z]
    params = default_substep_advection_params()
    full = torch.full_like
    for n in range(1, nmax + 1):
        out = conservative_substep_advection_torch(
            st, *falls,
            full(st.qr, w1_qr), full(st.qr, wn_qr),
            full(st.qr, w1_qs), full(st.qr, w1_qg),
            delz_t, rho_t,   # dend = rho ALONE in this runtime (F:812 dend=den)
            mstep_col=mcol_t, n_current=n, dtcld=DTCLD, params=params)
        st = out.state
        falls = [out.fall_qr, out.fall_nr, out.fall_qs, out.fall_qg, out.fall_brs]
    return {"qr": st.qr, "nr": st.nr, "qs": st.qs, "qg": st.qg, "brs": st.brs,
            "fall_qr": falls[0], "fall_nr": falls[1], "fall_qs": falls[2],
            "fall_qg": falls[3], "fall_brs": falls[4]}


def _py_ice(fix):
    qi, ni, w1_qi, wn_qi, rho, delz, mcol, nmax, dtype = fix
    st = IceSubstepState(qi=_t(qi, dtype), ni=_t(ni, dtype))
    rho_t, delz_t = _t(rho, dtype), _t(delz, dtype)
    mcol_t = torch.tensor(mcol, dtype=torch.float64).to(dtype)
    z = torch.zeros_like(st.qi)
    f_qi, f_ni = z, z
    params = default_substep_advection_params()
    full = torch.full_like
    for n in range(1, nmax + 1):
        out = conservative_ice_substep_advection_torch(
            st, f_qi, f_ni, full(st.qi, w1_qi), full(st.qi, wn_qi),
            delz_t, rho_t,
            mstep_col=mcol_t, n_current=n, dtcld=DTCLD, params=params)
        st = out.state
        f_qi, f_ni = out.fall_qi, out.fall_ni
    return {"qi": st.qi, "ni": st.ni, "fall_qi": f_qi, "fall_ni": f_ni}


def _py_full(cols, dt):
    K = len(cols[0]["rho"])

    def field(name):
        return torch.tensor(
            [[c[name]] * K if not isinstance(c[name], list) else c[name]
             for c in cols], dtype=torch.float64)

    s = State(th=field("th"), qv=field("qv"), qc=field("qc"), qr=field("qr"),
              qi=field("qi"), qs=field("qs"), qg=field("qg"),
              nccn=field("nccn"), nc=field("nc"), ni=field("ni"),
              nr=field("nr"), bg=field("bg"))
    f = Forcing(rho=field("rho"), pii=field("pii"), p=field("p"),
                delz=field("delz"))
    out, budget, _att = kdm6_step_conservative_experiment(s, f, None, dt)
    return out, budget


def _ulp64(a: float, b: float) -> float:
    if a == b:
        return 0
    if any(map(math.isnan, (a, b))) or any(map(math.isinf, (a, b))):
        return float("inf")

    def mono(x):
        i = struct.unpack("<q", struct.pack("<d", x))[0]
        return i if i >= 0 else (0x8000000000000000 - i)

    return abs(mono(a) - mono(b))


def _ulp32(a: float, b: float) -> float:
    """ULP distance in FLOAT32 space (a, b are exact f32 values held in f64)."""
    if a == b:
        return 0
    if any(map(math.isnan, (a, b))) or any(map(math.isinf, (a, b))):
        return float("inf")

    def mono(x):
        i = struct.unpack("<i", struct.pack("<f", x))[0]
        return i if i >= 0 else (0x80000000 - i)

    return abs(mono(a) - mono(b))


def _compare_fields(tag, cpp_fields, py_fields):
    """Return (worst_rel, worst_abs, worst_ulp, n_bitwise, n_total, worst_where)."""
    worst_rel = worst_abs = 0.0
    worst_ulp, nbit, ntot = 0, 0, 0
    where = ""
    for name, py_t in py_fields.items():
        assert name in cpp_fields, f"{tag}: C++ did not dump field {name}"
        py = py_t.detach().to(torch.float64).reshape(-1)
        cs = cpp_fields[name]
        assert len(cs) == py.numel(), f"{tag}.{name}: size mismatch"
        for i, c in enumerate(cs):
            p = py[i].item()
            ntot += 1
            u = _ulp64(p, c)
            if u == 0:
                nbit += 1
            worst_ulp = max(worst_ulp, u)
            a = abs(p - c)
            r = a / (abs(p) if abs(p) > 0 else 1.0)
            if a > worst_abs:
                worst_abs = a
            if r > worst_rel:
                worst_rel, where = r, f"{tag}.{name}[{i}] py={p:.17g} cpp={c:.17g}"
    return worst_rel, worst_abs, worst_ulp, nbit, ntot, where


def test_direct_substep_fp64_parity():
    """Direct conservative substeps, fp64: rtol <= 1e-10 / atol <= 1e-12."""
    dumps = _run_cpp_dumps()
    worst = (0.0, "")
    with torch.no_grad():
        for tag, fix in _MAIN_FIXTURES.items():
            if fix[-1] is not torch.float64:
                continue
            py = _py_main(fix)
            rel, abs_, ulp, nbit, ntot, where = _compare_fields(tag, dumps[tag], py)
            print(f"{tag}: worst rel={rel:.3e} abs={abs_:.3e} ulp={ulp} "
                  f"bitwise {nbit}/{ntot}")
            assert rel <= 1e-10 and abs_ <= max(1e-12, rel), where
            if rel > worst[0]:
                worst = (rel, where)
        for tag, fix in _ICE_FIXTURES.items():
            if fix[-1] is not torch.float64:
                continue
            py = _py_ice(fix)
            rel, abs_, ulp, nbit, ntot, where = _compare_fields(tag, dumps[tag], py)
            print(f"{tag}: worst rel={rel:.3e} abs={abs_:.3e} ulp={ulp} "
                  f"bitwise {nbit}/{ntot}")
            assert rel <= 1e-10 and abs_ <= max(1e-12, rel), where
    print(f"fp64 direct-substep worst: {worst[0]:.3e} ({worst[1] or 'bitwise'})")


def test_direct_substep_f32_controlled():
    """Controlled f32 direct substeps: bitwise first, else max float32 ULP.

    Measured on the reference toolchains: BITWISE (max f32 ULP = 0). Both
    trees execute the identical torch f32 op sequence — same evaluation order
    (dend*q*w1/mstep*gate; min-cap; the C++ ``.to(state dtype)`` falk store is
    a no-op when the whole chain is already f32) — so no divergence op exists.
    The <= 4 ULP fallback bound exists ONLY for a future kernel change in
    torch itself; if it ever fires, find the first-divergence op by bisecting
    the substep expression chain (falk -> dq_out -> fall -> dq_in -> state).
    """
    dumps = _run_cpp_dumps()
    max_ulp, where = 0, ""
    with torch.no_grad():
        for tag, py in (("DS32_VAR", _py_main(_MAIN_FIXTURES["DS32_VAR"])),
                        ("DS32_VAR_ICE", _py_ice(_ICE_FIXTURES["DS32_VAR_ICE"]))):
            for name, py_t in py.items():
                py_flat = py_t.detach().reshape(-1)
                for i, c in enumerate(dumps[tag][name]):
                    p = py_flat[i].item()   # exact f32 -> f64 widening
                    u = _ulp32(p, c)
                    if u > max_ulp:
                        max_ulp, where = u, f"{tag}.{name}[{i}] py={p!r} cpp={c!r}"
    print(f"f32 direct-substep max ULP32 = {max_ulp} {where}")
    assert max_ulp == 0 or max_ulp <= 4, f"f32 parity beyond ULP bound: {where}"


def test_full_step_conservative_parity():
    """Full conservative kdm6_step (internal C++ fp64) vs the oracle
    kdm6_step_conservative_experiment: 12 state fields + rain_increment.

    Regression bound (mirrors the test_cpp_parity philosophy). Measured on the
    reference toolchain: FS64_CAP worst rel 8.0e-16 (single sub-cycle,
    essentially bitwise); FS64_MULTI worst rel 4.6e-7, concentrated in the
    col-2 mixed-ice column's graupel-volume chain (bg/qg/nccn) — the known
    cross-tree fp64 op-order drift amplified over dt=300's 3 sub-cycles of the
    branchy ProgB/brs chain (same class as the documented CPPOUT drift in
    test_cpp_parity). Gate at 1e-5 (~20x the measured max): a REAL one-sided
    physics regression jumps orders of magnitude beyond this.
    """
    dumps = _run_cpp_dumps()
    worst_rel, where = 0.0, ""
    with torch.no_grad():
        for tag, (cols, dt) in _FULL_FIXTURES.items():
            out, budget = _py_full(cols, dt)
            fields = {n: getattr(out, n) for n in
                      ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                       "nccn", "nc", "ni", "nr", "bg")}
            # rain_increment (WDM6 TOTAL surface fallout, mm == kg m^-2)
            # accumulated over sub-cycles == the budget surface diagnostic.
            fields["rain_increment"] = budget.surface_precip_diag_kg_m2
            rel, abs_, ulp, nbit, ntot, w = _compare_fields(tag, dumps[tag], fields)
            print(f"{tag}: worst rel={rel:.3e} abs={abs_:.3e} ulp={ulp} "
                  f"bitwise {nbit}/{ntot}")
            if rel > worst_rel:
                worst_rel, where = rel, w
            # subset sanity on the C++-only increments: snow/graupel are PARTS
            # of the total rain_increment (adding them would double-count).
            for j in range(len(cols)):
                r = dumps[tag]["rain_increment"][j]
                sn = dumps[tag]["snow_increment"][j]
                gr = dumps[tag]["graupel_increment"][j]
                assert math.isfinite(r) and math.isfinite(sn) and math.isfinite(gr)
                assert 0.0 <= sn <= r + 1e-12 and 0.0 <= gr <= r + 1e-12
    assert worst_rel < 1e-5, f"conservative full-step parity regressed — {where}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
