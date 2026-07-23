"""Verdict-matrix unit tests for the four-case comparator core (public CI — no
build). Synthetic normalized runs exercise PASS / FAIL / INCONCLUSIVE /
INVALID_EVIDENCE and the canonical-order + mechanism-taxonomy fixes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fourcase_comparator as cmp  # noqa: E402
import g33_mechanism as mech           # noqa: E402


def _op(n, col, k, role, sp, opid, fld, dt, bits, seq):
    return {"n": n, "col": col, "k": k, "role": role, "species": sp,
            "op_id": opid, "field": fld, "dtype": dt, "bits": bits, "op_seq_id": seq}


def _st(stage, n, col, k, fld, dt, bits):
    return {"stage": stage, "n": n, "col": col, "k": k, "field": fld,
            "dtype": dt, "bits": bits}


def _run(algo, falk=100, inflow=200, outer=300, sub1=400, n2=False, sub2=None):
    ops = [_op(1, 1, 0, "TOP", "qr", "QR_FALK", "mul_work1", "f64", falk, 0),
           _op(1, 1, 1, "INTERIOR", "qr", "QR_INFLOW", "inflow_final", "f32", inflow, 5)]
    stages = [_st("outer_pre_sed", 0, 1, 0, "qr", "f32", outer),
              _st("substep_pre", 1, 1, 0, "work1_qr", "f64", sub1),
              _st("surface", 0, 1, -1, "bottom_fall_qr", "f32", 500)]
    if n2:
        ops.append(_op(2, 1, 0, "TOP", "qr", "QR_FALK", "mul_work1", "f64", falk, 10))
        stages.append(_st("substep_pre", 2, 1, 0, "work1_qr", "f64",
                          sub2 if sub2 is not None else sub1))
    return {"algorithm": algo, "ops": ops, "stages": stages}


def _verdict(lf, lc, cf, cc):
    return cmp.classify(cmp.compare_pair(lf, lc), cmp.compare_pair(cf, cc))[0]


def test_no_divergence_is_inconclusive():
    assert _verdict(_run("legacy"), _run("legacy"),
                    _run("conservative"), _run("conservative")) == "INCONCLUSIVE"


def test_shared_falk_divergence_is_pass():
    assert _verdict(_run("legacy"), _run("legacy", falk=999),
                    _run("conservative"), _run("conservative", falk=999)) == "PASS"


def test_conservative_inflow_divergence_is_fail():
    # legacy pair identical; conservative pair first-diverges at the ρΔz inflow.
    v, reason = cmp.classify(
        cmp.compare_pair(_run("legacy"), _run("legacy")),
        cmp.compare_pair(_run("conservative"), _run("conservative", inflow=999)))
    assert v == "FAIL" and "CONSERVATIVE_RHODZ_INFLOW" in reason


def test_outer_pre_sed_divergence_is_inconclusive():
    v, reason = cmp.classify(
        cmp.compare_pair(_run("legacy"), _run("legacy", outer=777)),
        cmp.compare_pair(_run("conservative"), _run("conservative", falk=999)))
    assert v == "INCONCLUSIVE" and "upstream" in reason


def test_identity_universe_mismatch_is_invalid_evidence():
    a = _run("conservative")
    b = _run("conservative")
    b["ops"] = b["ops"][:-1]                    # C++ dropped an op identity
    assert _verdict(_run("legacy"), _run("legacy"), a, b) == "INVALID_EVIDENCE"


def test_n1_op_divergence_not_misattributed_to_n2_stage():
    # P0-3: n=1 QR_FALK differs AND substep_pre(n=2) differs — the n=1 op wins
    # (execution order), NOT the later stage that the op perturbs.
    d = cmp.compare_pair(_run("legacy", n2=True),
                         _run("legacy", falk=999, n2=True, sub2=888))
    assert d.phase == "op" and d.identity[6] == "QR_FALK"


def test_mechanism_taxonomy_is_role_and_expression_aware():
    # P0-5: same op_id.field, DIFFERENT mechanism per variant; falk is shared.
    assert mech.mechanism("conservative", "QR_INFLOW", "inflow_final") == \
        mech.CONSERVATIVE_RHODZ_INFLOW
    assert mech.mechanism("legacy", "QR_INFLOW", "inflow_final") == \
        mech.LEGACY_DZ_CAPPED_INFLOW
    assert mech.mechanism("legacy", "QR_FALK", "mul_work1") == mech.SHARED_FALK
    assert mech.is_conservative_only(mech.CONSERVATIVE_RHODZ_INFLOW)
    assert not mech.is_conservative_only(mech.SHARED_FALK)
