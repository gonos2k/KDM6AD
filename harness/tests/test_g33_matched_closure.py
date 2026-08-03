"""The matched closure, and the control that decides whether a row is evidence."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import g33_matched_closure as mc  # noqa: E402


def _xfer(call=1, loop=1, n=1, col=1, chain="main", dq="3F800000", dn="40000000"):
    return f"G33F XFER {loop} {n} {col} {chain} f32 {dq} {dn}\n"


def test_transfers_are_summed_over_substeps_within_one_call():
    """The bottom cell exports once per sub-step; the segment budget spans them
    all, so a single-sub-step read would understate the outflow."""
    s = ("G33N CALL_BEGIN 1 1 1 1 1 2 42C80000\n"
         + _xfer(n=1) + _xfer(n=2) + "G33N CALL_END 1 1 1\n")
    got = mc.transfers(s)
    assert got[(1, 1, 1, "main")] == (2.0, 4.0)


def test_transfers_are_not_pooled_across_calls():
    """Keyed by the call's ordinal: pooling would attribute one call's outflow to
    another, which is the defect the G33N framing exists to stop."""
    s = ("G33N CALL_BEGIN 1 1 1 1 1 2 42C80000\n" + _xfer() + "G33N CALL_END 1 1 1\n"
         "G33N CALL_BEGIN 2 2 1 1 1 2 42C80000\n" + _xfer() + "G33N CALL_END 2 2 1\n")
    got = mc.transfers(s)
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
    assert "!! ice/qi col 2: mass control fails" in out
    assert "!! main/qr" not in out, "a control that closes must not be flagged"
