"""Verdict-matrix unit tests for the four-case comparator core (public CI — no
build). Synthetic normalized runs exercise PASS / FAIL / INCONCLUSIVE /
INVALID_EVIDENCE; the real bundle readers are integration-tested separately."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fourcase_comparator as cmp  # noqa: E402

# op ladders (scalar_seq -> record). seq 0 is a SHARED rung; seq 2 differs by
# variant: legacy carries a legacy-only field, conservative a conservative-only one.
SHARED0 = ("QR_FALK", "mul_dend_q", "TOP", 0, "qr", "f32")
SHARED1 = ("QR_FALK", "mul_work1", "TOP", 0, "qr", "f64")
LEG_ONLY = ("QR_INFLOW", "stored_falk_prev", "INTERIOR", 1, "qr", "f32")
CON_ONLY = ("QR_INFLOW", "src_metric", "INTERIOR", 1, "qr", "f32")
STAGE = ("outer_pre_sed", 0, "qr", 0, 1)


def _run(seq2, bits):
    """A run: 3 op rungs + one stage; `bits` overrides {scalar_seq: value} and
    {stage_key: value}."""
    ops = {0: (*SHARED0, bits.get(0, 100)),
           1: (*SHARED1, bits.get(1, 200)),
           2: (*seq2, bits.get(2, 300))}
    stages = {STAGE: bits.get(STAGE, 500)}
    return {"ops": ops, "stages": stages}


def _leg(bits=None):
    return _run(LEG_ONLY, bits or {})


def _con(bits=None):
    return _run(CON_ONLY, bits or {})


def test_no_divergence_is_inconclusive():
    v, _ = cmp.classify(cmp.compare_pair(_leg(), _leg()),
                        cmp.compare_pair(_con(), _con()))
    assert v == "INCONCLUSIVE"


def test_shared_first_divergence_is_pass():
    # both pairs first differ at the SHARED rung seq 0.
    leg = cmp.compare_pair(_leg(), _leg({0: 999}))
    con = cmp.compare_pair(_con(), _con({0: 999}))
    v, reason = cmp.classify(leg, con)
    assert v == "PASS", reason


def test_conservative_only_divergence_is_fail():
    # legacy pair identical; conservative pair first differs at the ρΔz rung seq 2.
    leg = cmp.compare_pair(_leg(), _leg())
    con = cmp.compare_pair(_con(), _con({2: 999}))
    v, reason = cmp.classify(leg, con)
    assert v == "FAIL" and "src_metric" in reason


def test_presed_divergence_is_inconclusive():
    # an outer_pre_sed mismatch — the sed-entry state already differs.
    leg = cmp.compare_pair(_leg(), _leg({STAGE: 777}))
    con = cmp.compare_pair(_con(), _con({0: 999}))
    v, reason = cmp.classify(leg, con)
    assert v == "INCONCLUSIVE" and "pre-sed" in reason


def test_universe_mismatch_is_invalid_evidence():
    a = _con()
    b = _con()
    del b["ops"][2]                       # C++ dropped a record
    v, _ = cmp.classify(cmp.compare_pair(_leg(), _leg()), cmp.compare_pair(a, b))
    assert v == "INVALID_EVIDENCE"


def test_different_ops_is_inconclusive():
    # legacy first-diverges at seq 0, conservative at the shared seq 1 — not the
    # same op, and seq 1 is not conservative-only, so it cannot be adjudicated.
    leg = cmp.compare_pair(_leg(), _leg({0: 999}))
    con = cmp.compare_pair(_con(), _con({1: 999}))
    v, _ = cmp.classify(leg, con)
    assert v == "INCONCLUSIVE"


def test_conservative_only_set_is_schema_derived():
    co = cmp.conservative_only_ops()
    assert ("QR_INFLOW", "src_metric") in co and ("QR_INFLOW", "dst_metric") in co
    assert ("QR_FALK", "mul_dend_q") not in co        # shared rung, not conservative-only
    assert ("QR_INFLOW", "stored_falk_prev") not in co  # legacy-only, not conservative-only
