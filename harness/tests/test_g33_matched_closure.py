"""The matched closure, and the control that decides whether a row is evidence."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import g33_matched_closure as mc  # noqa: E402
from test_g33_number_transport import _call, _stream  # noqa: E402


def _with_xfer(cid, mstep=1, dq="3F800000", dn="40000000"):
    """A complete call whose XFER universe matches the declared mstep — the
    strict parser now requires exactly sub-steps 1..mstep."""
    body = _call(cid).replace(
        "G33F MSTEP 1 main 1 i32 00000001",
        f"G33F MSTEP 1 main 1 i32 {mstep:08X}")
    xf = "".join(f"G33F XFER 1 {n} 1 main f32 {dq} {dn}\n"
                 for n in range(1, mstep + 1))
    xf += "G33F XFER 1 1 1 ice f32 00000000 00000000\n"
    return body.replace("G33N CALL_END", xf + "G33N CALL_END")


def test_transfers_are_summed_over_substeps_within_one_call():
    """The bottom cell exports once per sub-step; the segment budget spans them
    all, so a single-sub-step read would understate the outflow."""
    got = mc.transfers(_stream(_with_xfer(1, mstep=2),
                               feats="mstep,mstepi,nflux,xfer"))
    assert got[(1, 1, 1, "main")] == (2.0, 4.0)


def test_transfers_are_not_pooled_across_calls():
    """Keyed by the call's ordinal: pooling would attribute one call's outflow to
    another, which is the defect the G33N framing exists to stop."""
    got = mc.transfers(_stream(_with_xfer(1), _with_xfer(2),
                               feats="mstep,mstepi,nflux,xfer"))
    assert got[(1, 1, 1, "main")] == (1.0, 2.0)
    assert got[(2, 1, 1, "main")] == (1.0, 2.0)


def test_the_chain_map_matches_the_kernel_sub_cycles():
    """mstep carries qr/nr and mstep_i carries qi/ni (F:1179-1180). Pairing qr
    with ni is the un-matched comparison this module replaces."""
    assert mc.CHAIN == {"main": ("qr", "nr"), "ice": ("qi", "ni")}


def test_a_failing_mass_control_is_flagged_not_reported_as_a_result(capsys):
    """A mass row that does not close means the accounting for that chain is
    missing a term, so NEITHER row of the pair is evidence."""
    def fake(_stream):
        return {("ice", "qi", 2): {"out": 1.0, "residual": -3.8, "start": 1.0,
                                   "calls": 12},
                ("ice", "ni", 2): {"out": 1.0, "residual": -1.6, "start": 1.0,
                                   "calls": 12},
                ("main", "qr", 1): {"out": 1.0, "residual": 1e-9, "start": 1.0,
                                    "calls": 12},
                ("main", "nr", 1): {"out": 1.0, "residual": 0.15, "start": 1.0,
                                    "calls": 12}}
    orig, mc.closures = mc.closures, fake
    try:
        mc.report("")
    finally:
        mc.closures = orig
    out = capsys.readouterr().out
    assert "!! ice/qi col 2: matched_mass_control_failed" in out
    assert "!! main/qr" not in out, "a control that closes must not be flagged"


def test_an_unusable_row_carries_a_null_number_result_in_the_JSON(monkeypatch):
    """A warning printed under a table is separated from it the moment someone
    copies the table. In the JSON the exclusion is structural (owner §6.2)."""
    def fake(_stream):
        return {("ice", "qi", 2): {"out": 1.0, "residual": -3.8, "start": 1.0,
                                   "calls": 1},
                ("ice", "ni", 2): {"out": 1.0, "residual": -1.6, "start": 1.0,
                                   "calls": 1},
                ("main", "qr", 1): {"out": 1.0, "residual": 1e-12, "start": 1.0,
                                    "calls": 1},
                ("main", "nr", 1): {"out": 1.0, "residual": 0.15, "start": 1.0,
                                    "calls": 1}}
    monkeypatch.setattr(mc, "closures", fake)
    a = mc.analysis("")
    assert a["ice/ni/2"]["usable"] is False
    assert a["ice/ni/2"]["number_result"] is None
    assert "matched_mass_control_failed" in a["ice/ni/2"]["reason"]
    assert a["main/nr/1"]["usable"] is True
    assert a["main/nr/1"]["number_result"] == pytest.approx(0.15)


def test_the_control_tolerance_is_derived_not_a_round_number():
    """1e-3 accepted a residual thousands of f32 eps as 'roundoff' (owner §6.1).
    gamma_n = n*eps/(1-n*eps) scales with the operation count."""
    small = mc.control_tolerance(8, 1.0)
    large = mc.control_tolerance(8000, 1.0)
    assert small < large < 1e-3
    assert small == pytest.approx(8 * 2.0 ** -24, rel=1e-6)


def test_the_interface_term_is_departure_minus_arrival():
    """dq(i,k+1) is written twice with different caps: as the cell's own outflow
    (pre-update) and as the inflow below (post-update). Pairing the two across an
    interface is what exposes the destroyed mass (P0-4b)."""
    ROOTB = ROOT / "g33_fortran"
    b = (ROOTB / "g33_fortran_bindings.py").read_text()
    assert "CAP_SITES" in b and "TOP_SITES" in b
    # each cap site emits BOTH of a cell's transfers, mass and number
    assert '"dqr(i,k)", "dqr(i,k+1)", "dnr(i,k)", "dnr(i,k+1)"' in b
    assert '"dqi(i,k)", "dqi(i,k+1)", "dni(i,k)", "dni(i,k+1)"' in b
    # the TOP cell is updated outside the interior loop, so it needs its own site
    assert "min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))" in b


def test_the_new_sites_stay_under_the_number_macro():
    """They must not reach the decision stream, like every emission before them."""
    ovl = (ROOT / "g33_fortran" / "make_fortran_overlay.py").read_text()
    for fn in ("_cap_inflow_lines", "_top_lines"):
        body = ovl.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "KDM6_G33_NUMBER_DUMP" in body
        assert "KDM6_G33_FORTRAN_DUMP" not in body


def test_instrumentation_sites_are_keyed_by_ALGORITHM():
    """The conservative variant rewrote the sedimentation update, so the legacy
    anchors do not exist in it. Keying the sites by algorithm is what let the
    overlay fail loudly on a missing anchor instead of instrumenting the wrong
    statement (owner §11)."""
    import sys
    sys.path.insert(0, str(ROOT / "g33_fortran"))
    import g33_fortran_bindings as fb
    for sites in (fb.XFER_SITES, fb.CAP_SITES, fb.TOP_SITES):
        assert set(sites) == {"legacy", "conservative"}
        assert sites["legacy"] != sites["conservative"]
    # conservative's number inflow keeps the dz-only ratio: that is the anchor
    assert any("delz(i,k+1)/delz(i,k)" in a
               for a, *_ in fb.XFER_SITES["conservative"])
