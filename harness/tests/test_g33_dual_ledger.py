"""Both column measures, and the claim that ratios do not care which (owner §9).

`den` is MOIST density (rho_m = rho_d(1+qv)) while the mixing ratios are per
DRY-air kg, so the operator's own budget and the physically conserved one are
different integrals. "Absolute values shift but ratios are unaffected" holds only
where 1+qv is vertically CONSTANT -- which is a property of a fixture, not of the
quantity. These build that dependence explicitly rather than arguing about it.
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_dual_ledger as dl  # noqa: E402
import g33_matched_closure as mc  # noqa: E402

RHO = [0.4, 0.6, 0.8, 1.2]          # top-first: density increases downward
DZ = 150.0
XFER = [1.0, 2.0, 3.0, 4.0]         # per-cell transfers


def _hex(x):
    return struct.pack(">f", x).hex().upper()


def _stream(qv, qr=0.0):
    """One call whose only free variable is the humidity profile.

    `qr` is optional mass, so a caller needing a mean particle mass (q/N)
    can have one; the humidity tests do not care and leave it zero.
    """
    pre = [10.0, 20.0, 30.0, 40.0]
    post = [pre[t] - XFER[t] + (XFER[t - 1] if t else 0.0) for t in range(4)]
    L = ["G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep,mstepi,nflux,xfer as-is",
         f"G33N CALL_BEGIN 1 1 1 1 1 {len(RHO)} 42C80000"]
    for stage, vals in (("outer_pre_sed", pre), ("outer_post_sed", post)):
        for k in range(len(RHO)):
            for f, v in (("nr", vals[k]), ("ni", 0.0), ("qr", qr), ("qi", 0.0),
                         ("qv", qv[k]), ("rho", RHO[k]), ("delz", DZ)):
                if stage == "outer_post_sed" and f in ("rho", "delz"):
                    continue
                L.append(f"G33F STAGE 1 - {stage} 0 {f} 1 {k} f32 {_hex(v)}")
    L += ["G33F MSTEP 1 main 1 i32 00000001", "G33F MSTEPI 1 1 i32 00000001"]
    # den/delz restate the bottom cell and dtcld restates delt/loops -- the
    # parser compares those duplicates now, so the fixture must be one
    # consistent run (delt = 100, loops = 1).
    L += [f"G33F NFLUX 1 1 {f} f32 "
          f"{_hex({'nflux_den': RHO[-1], 'nflux_delz': DZ, 'nflux_dtcld': 100.0}.get(f, 1.0))}"
          for f in mc.nt.NFLUX_FIELDS]
    L += [f"G33F XFER 1 1 1 main f32 {_hex(0.0)} {_hex(XFER[-1])}",
          "G33F XFER 1 1 1 ice f32 00000000 00000000",
          "G33N CALL_END 1 1 1", "G33N STREAM_END"]
    return "\n".join(L) + "\n" + _g33r(qv, qr, pre, post)


def _g33r(qv, qr, pre, post, initial_qv=None):
    """The G33R block a real driver emits beside the G33N one.

    The physical measure takes its `qv` from `G33R INITIAL` -- the window's true
    start -- so a G33N-only fixture cannot express it at all. `initial_qv`
    defaults to the same profile the calls carry, which is what this fixture
    means; a test that needs the window start to DIFFER from the first call's
    pre-sed value passes its own.
    """
    iq = qv if initial_qv is None else initial_qv
    L = ["G33R BEGIN nsplit 1 rezero legacy delt 60.000000 loops 1 "
         "dtcld 60.000000"]
    for cls, vals, hum in (("INITIAL", pre, iq), ("STATE", post, qv)):
        for k in range(len(RHO)):
            for f in mc.ra.STATE_FIELDS:
                v = {"nr": vals[k], "qr": qr, "qv": hum[k]}.get(f, 0.0)
                L.append(f"G33R {cls} {f} 1 {k} {_hex(v)}")
    for k in range(len(RHO)):
        for name, v in (("rho", RHO[k]), ("delz", DZ), ("pii", 1.0)):
            L.append(f"G33R FORCING {name} 1 {k} {_hex(v)}")
    L += [f"G33R PREC {i} 1 00000000" for i in (1, 2, 3)] + ["G33R END"]
    return "\n".join(L) + "\n"


def _divergence(qv):
    return dl.analysis(_stream(qv))["rows"]["main/nr/1"]["ratio_divergence"]


def test_a_vertically_UNIFORM_humidity_makes_the_basis_cancel():
    """This is the only case in which "ratios are unaffected by the basis" is
    exactly true: 1+qv factors out of numerator and denominator alike."""
    assert _divergence([0.001] * 4) < 1e-12


def test_a_REALISTIC_humidity_profile_makes_the_ratios_DIVERGE():
    """qv 2e-5 aloft to 1.8e-2 at the surface -- an ordinary troposphere. The two
    ratios then differ by over a percent, so the invariance is a property of a
    near-dry fixture and must not be quoted as a property of the quantity
    (owner §9.3)."""
    assert _divergence([0.00002, 0.0015, 0.0080, 0.0180]) > 1e-2


def test_the_divergence_grows_with_the_humidity_SPREAD_not_its_mean():
    """The conversion is 1+qv; a constant offset cancels and only the vertical
    variation survives. Adding a large CONSTANT humidity must not change it."""
    spread = [0.0000, 0.0020, 0.0040, 0.0060]
    lifted = [q + 0.010 for q in spread]
    a, b = _divergence(spread), _divergence(lifted)
    assert a > 1e-4
    assert b == pytest.approx(a, rel=0.35), \
        "a uniform offset should barely move it; only the spread should"


def test_both_measures_are_always_reported():
    """A reader who is handed one number cannot tell which integral it is. The
    artifact carries both and says which is which."""
    a = dl.analysis(_stream([0.001] * 4))
    row = a["rows"]["main/nr/1"]
    assert set(row) >= {"operator", "physical", "ratio_divergence"}
    assert "rho_d = rho_m/(1+qv)" in a["basis_note"]


def test_the_physical_basis_is_the_DRY_one():
    """rho_d = rho_m/(1+qv) < rho_m, so the physical column integral is smaller."""
    a = dl.analysis(_stream([0.02] * 4))["rows"]["main/nr/1"]
    assert abs(a["physical"]["surface_out"]) < abs(a["operator"]["surface_out"])


def test_an_unknown_basis_is_refused_rather_than_silently_moist():
    with pytest.raises(ValueError, match="basis must be one of"):
        mc.closures(_stream([0.001] * 4), "dry-ish")
