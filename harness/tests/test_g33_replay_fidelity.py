"""Ladder-fidelity kill set (public CI — no build).

Every rung of the dumped ladder must equal a recomputation from the operands the
producer itself dumped. These tests mutate one rung at a time in the CHECKED-IN real
Fortran evidence and require it to die at the fidelity gate — before any verdict, so
a wrong instrumentation shadow can never be reported as a mechanism finding.
"""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "g33_legacy_sample.g33f"
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
sys.path.insert(0, str(ROOT / "harness"))
import g33_fortran_dump as fd            # noqa: E402
import g33_fourcase_comparator as cmp    # noqa: E402
import g33_normalize as nz               # noqa: E402
import g33_replay as rp                  # noqa: E402

RUN = nz.from_fortran_run(fd.parse_fortran_run(SAMPLE.read_text(), "legacy", 4, 3))


def test_real_fortran_ladder_replays_exactly():
    assert rp.replay_run(RUN) > 300         # the whole ladder, not a token check


def _mutate(op_id, field):
    m = copy.deepcopy(RUN)
    for o in m["ops"]:
        if o["op_id"] == op_id and o["field"] == field:
            o["bits"] ^= 1                  # 1 ULP is enough
            return m
    raise AssertionError(f"no {op_id}.{field} in the sample")


@pytest.mark.parametrize("op_id,field", [
    ("QR_FALK", "shadow_falk_f32"),     # the shadow itself
    ("QR_FALK", "falk_f32"),            # the ACTUAL value the transport used
    ("QR_FALK", "mul_work1"),
    ("QR_FALK", "div_mstep"),
    ("QR_FALK", "falk_precast"),
    ("NR_FALK", "mul_workn"),
    ("QR_OUTFLOW", "mul_dt"),
    ("QR_OUTFLOW", "outflow_pre_cap"),
    ("QR_OUTFLOW", "dq_out"),
    ("QR_INFLOW", "mul_delz_src"),
    ("QR_INFLOW", "div_delz_dst"),
    ("QR_INFLOW", "inflow_pre_cap"),
    ("QR_INFLOW", "inflow_final"),
    ("QR_FALLACC", "fall_after"),
    ("QR_UPDATE", "q_minus_out"),
    ("QR_UPDATE", "q_plus_in_preclamp"),
    ("QR_UPDATE", "q_post"),
])
def test_every_rung_mutant_dies_at_the_fidelity_gate(op_id, field):
    with pytest.raises(rp.FidelityError):
        rp.replay_run(_mutate(op_id, field))


def test_a_commonly_wrong_shadow_is_invalid_not_a_verdict():
    # The dangerous case: BOTH variants of one backend carry the same wrong shadow.
    # Pure comparison would align them on a shared rung and could read as PASS; the
    # decision entry must refuse the evidence instead.
    bad = _mutate("QR_FALK", "shadow_falk_f32")
    cons_bad = copy.deepcopy(bad)
    cons_bad["algorithm"] = "conservative"
    r = cmp.adjudicate_verified(bad, RUN, cons_bad, cons_bad)
    assert r["verdict"] == "INVALID_EVIDENCE" and "fidelity" in r["reason"]


def test_variant_mislabelled_evidence_is_rejected():
    # A legacy ladder labelled "conservative" replays against the conservative
    # relations (no positivity clamp, rho*dz inflow) and fails — so evidence whose
    # variant label does not match its own arithmetic cannot reach a verdict.
    mislabelled = copy.deepcopy(RUN)
    mislabelled["algorithm"] = "conservative"
    with pytest.raises(rp.FidelityError):
        rp.replay_run(mislabelled)
    r = cmp.adjudicate_verified(RUN, RUN, mislabelled, mislabelled)
    assert r["verdict"] == "INVALID_EVIDENCE" and "fidelity" in r["reason"]


def test_pure_comparator_still_reaches_a_verdict_on_the_real_pair():
    # the legacy pair compared against itself is clean (mstep=1 fixture)
    assert cmp.compare_pair(RUN, RUN).phase is None
