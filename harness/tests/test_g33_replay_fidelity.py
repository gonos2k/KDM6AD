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
    report = rp.replay_report(RUN)
    # EXACT coverage, not "more than N": a count cannot tell a full ladder from one
    # whose INFLOW family vanished, and a thinner check must not read as a pass.
    assert set(report) == rp.RELATION_COVERAGE["legacy"]
    assert sum(report.values()) == 516


def _with_raw_metric(bits_xor):
    """Attach a raw metric to the run. The reference emits no raw/safe distinction,
    so this exercises the RELATION, not the Fortran producer: only a C++ leg carries
    these, and its bundle layer already requires them to be present."""
    st = next(x for x in RUN["stages"] if x["field"] == "dend_safe")
    m = copy.deepcopy(RUN)
    m["raw_metrics"] = {(st["loop"], st["chain"], st["n"], st["col"], st["k"],
                         "dend_raw"): st["bits"] ^ bits_xor}
    return m


def test_an_unfloored_raw_metric_passes():
    assert rp.replay_run(_with_raw_metric(0)) == 517      # 516 + the one metric rung


def test_a_floored_metric_dies_at_the_fidelity_gate():
    # a floored metric silently changes the divisor the whole ladder uses
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(_with_raw_metric(1))
    assert str(e.value).startswith("METRIC.dend_safe==dend_raw at ")


def test_a_dumped_value_no_relation_reads_is_a_coverage_hole():
    # Comparing relation NAMES cannot see a value nothing checks: the name still
    # appears from every other cell. Coverage is a per-VALUE property.
    m = copy.deepcopy(RUN)
    extra = dict(m["ops"][0], field="unwatched_rung", bits=0x3F800000)
    m["ops"].append(extra)
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(m)
    assert "never checked by any relation" in str(e.value)


def test_branch_flags_are_exempt_because_another_gate_owns_them():
    # they are recomputed by validate_gate_semantics._check_branch, not by a rung
    assert rp._EXEMPT_FIELDS == {"cap_active", "inflow_cap_active", "clamp_active"}


def test_coverage_shrink_is_a_fidelity_failure():
    thin = copy.deepcopy(RUN)
    thin["ops"] = [o for o in thin["ops"] if "INFLOW" not in o["op_id"]]
    with pytest.raises(rp.FidelityError):
        rp.replay_run(thin)


def _mutate(op_id, field, k=None):
    m = copy.deepcopy(RUN)
    for o in m["ops"]:
        if o["op_id"] == op_id and o["field"] == field and (k is None or o["k"] == k):
            o["bits"] ^= 1                  # 1 ULP is enough
            return m
    raise AssertionError(f"no {op_id}.{field} (k={k}) in the sample")


# Every row was measured against the real sample, including WHICH relation kills it:
# a mutation that merely "fails somewhere" would not prove the intended rung is gated.
@pytest.mark.parametrize("op_id,field,k,relation", [
    ("QR_FALK", "shadow_falk_f32", None, "FALK.shadow_falk_f32"),
    ("QR_FALK", "falk_f32", None, "FALK.actual==shadow"),   # the value transport used
    ("QR_FALK", "mul_dend_q", None, "FALK.mul_dend_q"),
    ("QR_FALK", "mul_work1", None, "FALK.mul_work1"),
    ("QR_FALK", "div_mstep", None, "FALK.div_mstep"),
    ("QR_FALK", "falk_precast", None, "FALK.falk_precast"),
    ("NR_FALK", "mul_workn", None, "FALK.mul_workn"),
    ("QR_OUTFLOW", "mul_dt", None, "OUTFLOW.mul_dt"),
    ("QR_OUTFLOW", "outflow_pre_cap", None, "OUTFLOW.outflow_pre_cap"),
    ("QR_OUTFLOW", "dq_out", None, "OUTFLOW.dq_out"),
    ("NR_OUTFLOW", "dn_out", None, "OUTFLOW.dn_out"),
    # the cap operands: inert when the cap does not bind, so they need their own rung
    ("QR_OUTFLOW", "source_reservoir", None, "OUTFLOW.source_reservoir(state)"),
    ("NR_OUTFLOW", "source_reservoir", None, "OUTFLOW.source_reservoir(state)"),
    ("QR_INFLOW", "source_reservoir", None, "INFLOW.source_reservoir(state)"),
    ("QR_INFLOW", "mul_delz_src", None, "INFLOW.mul_delz_src"),
    ("QR_INFLOW", "div_delz_dst", None, "INFLOW.div_delz_dst"),
    ("QR_INFLOW", "inflow_pre_cap", None, "INFLOW.inflow_pre_cap"),
    ("QR_INFLOW", "inflow_final", None, "INFLOW.inflow_final"),
    ("QR_INFLOW", "stored_falk_prev", None, "INFLOW.stored_falk_prev(carry)"),
    ("NR_INFLOW", "stored_falk_nr_prev", None, "INFLOW.stored_falk_nr_prev(carry)"),
    ("QR_FALLACC", "fall_increment", None, "FALLACC.fall_increment"),
    ("NR_FALLACC", "fall_increment", None, "FALLACC.fall_increment"),
    ("QR_FALLACC", "fall_after", None, "FALLACC.fall_after"),
    ("QR_UPDATE", "q_minus_out", 0, "UPDATE.q_minus_out(raw depletion)"),   # TOP cell
    ("NR_UPDATE", "n_minus_out", 0, "UPDATE.n_minus_out(raw depletion)"),
    ("QR_UPDATE", "q_minus_out", 2, "UPDATE.q_minus_out"),                  # capped
    ("QR_UPDATE", "q_plus_in_preclamp", None, "UPDATE.q_plus_in_preclamp"),
    ("QR_UPDATE", "q_post", None, "UPDATE.q_post"),
    ("NR_UPDATE", "n_post", None, "UPDATE.n_post"),
])
def test_every_rung_mutant_dies_at_the_fidelity_gate(op_id, field, k, relation):
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(_mutate(op_id, field, k))
    assert str(e.value).startswith(relation + " at ")


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
