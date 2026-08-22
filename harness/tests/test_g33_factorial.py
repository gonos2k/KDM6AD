"""The factorial's coefficients, and the two readings that got them wrong.

The first version of this analysis declared the three corrections orthogonal
from a table of ABSOLUTE residuals. Both halves of that sentence were a defect:
the absolute value is the wrong response, and marginal selectivity is not
orthogonality. Each has a test here.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_factorial as fc  # noqa: E402


def _table(fn, invalid=()):
    """A response table from a function of the 0/1 factor levels.

    Rows carry the full record now -- value, validity and the reason -- because
    a response is only scored where it is valid in ALL EIGHT arms.
    """
    return {arm: {r: {"value": fn(*fc.ALGO_FACTORS[arm]),
                      "valid": arm not in invalid,
                      "reason": "control failed" if arm in invalid else "",
                      "screening_bound": 0.0}
                  for r in fc.RESPONSES}
            for arm in fc.ALGO_FACTORS}


def test_an_additive_response_has_exactly_zero_cross_terms():
    """The claim the first version made -- true only of an additive response.

    On +/-1 coding beta is the HALF-effect: a factor whose 0->1 step moves the
    response by 2 has beta 1. Reading beta as the step doubles every effect in
    the table, which is how a coefficient gets compared against the wrong scale.
    """
    beta = fc.coefficients(_table(lambda n, c, l: 5.0 + 2 * n + 3 * c + 7 * l))
    b = beta["R_ni"]
    assert (b[""], b["N"], b["C"], b["L"]) == (5.0 + 6.0, 1.0, 1.5, 3.5)
    for term in ("NC", "NL", "CL", "NCL"):
        assert b[term] == 0.0


def test_masking_shows_as_main_effect_and_interaction_cancelling():
    """C acts only where N has not already removed the residual.

    This is the shape the measurement found, and its signature is exact:
    `beta_C == -beta_NC`. An additive reading of the same table would report
    C as half as strong and no interaction at all.
    """
    beta = fc.coefficients(_table(lambda n, c, l: -0.5 * c * (1 - n)))
    b = beta["R_ni"]
    assert b["C"] == -b["NC"] != 0.0


def test_beta_nc_is_the_owners_interaction_over_four():
    """`I_NC = Y11 - Y10 - Y01 + Y00` at fixed L, the review's own arithmetic."""
    table = _table(lambda n, c, l: -0.5 * c * (1 - n))
    y = {(n, c): table[a]["R_ni"]["value"]
         for a, (n, c, l) in fc.ALGO_FACTORS.items()}
    i_nc = y[(1, 1)] - y[(1, 0)] - y[(0, 1)] + y[(0, 0)]
    assert fc.coefficients(table)["R_ni"]["NC"] == pytest.approx(i_nc / 4)


def test_the_absolute_value_distorts_a_sign_reversing_response():
    """Why the response is signed.

    The cap term reverses sign under C. Taking `|Y|` turns a large real effect
    into a small apparent one -- the reading that produced the withdrawn claim.
    """
    signed = fc.coefficients(_table(lambda n, c, l: 2.4 - 5.8 * c))
    folded = fc.coefficients(_table(lambda n, c, l: abs(2.4 - 5.8 * c)))
    assert signed["cap_ice_signed"]["C"] == pytest.approx(-2.9)
    assert folded["cap_ice_signed"]["C"] == pytest.approx(0.5)


def test_a_partial_factorial_is_refused_not_averaged():
    """Seven arms are not a 2^3 design, and a coefficient off seven is fiction."""
    table = _table(lambda n, c, l: float(n + c + l))
    table.pop("cons_nmasslncmin")
    with pytest.raises(fc.FactorialError):
        fc.coefficients(table)


def test_terms_are_named_in_factor_order():
    """`CN` and `NC` name one term and read as two. Regression: sorted() gave both."""
    assert fc._subsets("NCL", 2) == ["NC", "NL", "CL"]
    assert fc._subsets("NCL", 3) == ["NCL"]


def test_conditional_effects_tell_the_two_interaction_shapes_apart():
    """One `beta_XY` cannot say WHICH factor is conditioned on the other.

    "C acts only while N is off" and "N acts only while C is on" are both
    N x C interactions and are different sentences. The published finding
    called them "the same shape"; conditional effects separate them, and this
    is the test that keeps them separated.
    """
    masked = fc.conditionals(_table(lambda n, c, l: -0.5 * c * (1 - n)))["R_ni"]
    assert masked["C_at_N0"] != 0 and masked["C_at_N1"] == 0

    gated = fc.conditionals(_table(lambda n, c, l: 0.3 * n * c))["R_ni"]
    assert gated["N_at_C0"] == 0 and gated["N_at_C1"] != 0

    # Same |beta_NC| for both, which is exactly why beta alone cannot say.
    a = fc.coefficients(_table(lambda n, c, l: -0.5 * c * (1 - n)))["R_ni"]["NC"]
    b = fc.coefficients(_table(lambda n, c, l: 0.5 * n * c))["R_ni"]["NC"]
    assert abs(a) == pytest.approx(abs(b))


def test_a_coefficient_is_reported_against_its_own_screening_scale():
    """A response's resolution is its magnitude and operation count, not an
    epsilon. An f32-derived sum of large terms does not resolve a small one."""
    assert fc._screen(1.0e8, 100) > 1.0
    assert fc._screen(1.0e-6, 4) < 1.0e-12
    # An integer count is exact: screening it would licence calling a real
    # difference of one state "unresolved".
    table = _table(lambda n, c, l: float(l))
    screens = {a: {r: 0.0 for r in fc.RESPONSES} for a in fc.ALGO_FACTORS}
    assert fc.coefficients(table, screens)["partition_path_cells"]["_bound"] == 0.0


def test_the_window_is_a_different_question_not_a_longer_first_call():
    """`window=True` accumulates over the run; the first call is the MATCHED one.

    Both spans are offered because they answer different things: on call one
    every arm meets the same initial state, so a difference is the arm; after it
    the arms hold different fields, so the window measures the operator over its
    own trajectory. A test that treated the second as a better version of the
    first would licence quoting either for the other's claim.
    """
    import inspect
    sig = inspect.signature(fc.responses)
    assert sig.parameters["window"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["window"].default is False      # matched span is default


# ---------------------------------------------------------------------------
# The three gates the mixed-span table had no way to fail.

def test_the_cap_response_is_taken_over_the_SPAN_it_is_asked_for(monkeypatch):
    """`cap_sink()` walks the whole stream and cannot select a call.

    That is why the first-call table carried a whole-window cap: the flag chose
    the span for four responses and this one ignored it. `Interface` carries its
    own 1-based call, so the span is applied where it belongs.
    """
    class F:
        def __init__(self, chain, call, term):
            self.chain, self.call, self.mass_term = chain, call, term
    faces = [F("ice", 1, -2.0), F("ice", 2, -5.0), F("main", 1, 3.0)]
    monkeypatch.setattr("g33_cap_interface._walk", lambda s, b: iter(faces),
                        raising=False)
    first = fc._cap("", frozenset({1}))
    whole = fc._cap("", frozenset({1, 2}))
    assert first["ice"]["signed"] == 2.0            # call 1 only
    assert whole["ice"]["signed"] == 7.0            # both calls
    assert first["main"]["signed"] == -3.0


def test_destruction_and_creation_are_not_one_signed_number(monkeypatch):
    """`Sink.signed` says in its own docstring that it is a signed DEFECT.

    An arm that turns destruction into creation of the same size leaves the
    signed sum looking like a reversal and the gross activity unchanged. Only
    the split says which happened.
    """
    class F:
        def __init__(self, chain, call, term):
            self.chain, self.call, self.mass_term = chain, call, term
    monkeypatch.setattr("g33_cap_interface._walk",
                        lambda s, b: iter([F("ice", 1, -3.0), F("ice", 1, 3.0)]),
                        raising=False)
    got = fc._cap("", frozenset({1}))["ice"]
    assert got["signed"] == 0.0                     # cancels
    assert got["destroyed"] == 3.0 and got["created"] == 3.0   # does not


def test_a_partition_universe_mismatch_is_refused_not_intersected(monkeypatch):
    """Comparing the intersection is fail-open.

    A split stream missing a column compares fewer states and reports BETTER
    invariance -- the count a missing state removes is the count the response
    is.
    """
    a = {(1, 1, 0): ("x",), (1, 2, 0): ("y",)}
    b = {(1, 1, 0): ("x",)}
    monkeypatch.setattr(fc, "_segment_states", lambda t: a if t == "A" else b)
    monkeypatch.setattr(fc, "_window_final", lambda t: {})
    with pytest.raises(fc.FactorialError, match="same segment states"):
        fc._partition("A", "B")


def test_partition_is_four_questions_not_one_count(monkeypatch):
    """First segment, last segment, the WINDOW FINAL state, and the path.

    The last post-sedimentation segment is not the window final state: other
    microphysical processes run after sedimentation in the same call. Reading
    the segment count as "what the forecast carries" is the confusion this
    separation removes.
    """
    a = {(1, 1, 0): (("qv", 1.0),), (2, 1, 0): (("qv", 1.0),),
         (3, 1, 0): (("qv", 1.0),)}
    b = {(1, 1, 0): (("qv", 1.0),), (2, 1, 0): (("qv", 9.0),),
         (3, 1, 0): (("qv", 9.0),)}
    fa = {("qv", 1, 0): 1.0, ("qv", 1, 1): 2.0}
    fb = {("qv", 1, 0): 1.0, ("qv", 1, 1): 9.0}
    monkeypatch.setattr(fc, "_segment_states", lambda t: a if t == "A" else b)
    monkeypatch.setattr(fc, "_window_final", lambda t: fa if t == "A" else fb)
    got = fc._partition("A", "B")
    assert got["partition_first_cells"] == 0.0            # agree after one
    assert got["partition_last_segment_cells"] == 1.0     # differ at the last
    assert got["partition_window_final_cells"] == 1.0     # a DIFFERENT quantity
    assert got["partition_path_cells"] == 2.0             # having differed twice


def test_an_unrecoverable_row_invalidates_ITS_response_and_no_other(monkeypatch):
    """`column()` refuses mstep > 1, and `0.0` then means two different things.

    "the residual vanished" and "nothing in this span could be measured" are
    the same number under the old code. Coverage is checked -- and it
    invalidates the recovered metric diagnostic ONLY, because the matched
    budget rows and the partition responses never needed that reader.
    """
    import g33_number_transport as nt
    call = {"outer_pre_sed": {(1, 1, 0): {}}, "loops": {1}}
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    monkeypatch.setattr(nt, "column", lambda c, col, sp: None)
    got = fc._recovered_ratio([call], "nr")
    assert got["eligible"] == 0 and got["expected"] == 1


def test_one_chains_failed_control_does_not_delete_the_other_responses():
    """Paired control, not global rejection.

    An ice mass control failure invalidates `R_ni` -- the number response whose
    interpretation depends on it -- and nothing else. Scoring every response off
    the arms whose control happened to close is not a contrast, so a response is
    scored only where it is valid in ALL EIGHT arms.
    """
    table = _table(lambda n, c, l: float(n), invalid={"legacy"})
    for arm in fc.ALGO_FACTORS:
        for r in ("R_nr", "R_qi"):
            table[arm][r] = dict(table[arm][r], valid=True, reason="")
    beta = fc.coefficients(table)
    assert beta["R_nr"]["_valid"] and beta["R_qi"]["_valid"]
    assert not beta["R_ni"]["_valid"]
    assert "legacy" in beta["R_ni"]["_invalid"]


def test_a_failing_mass_row_is_a_RESPONSE_not_a_reason_to_drop_the_arm():
    """C exists to remove a mass defect, so rejecting an arm for having one
    deletes the C response from the C experiment."""
    unit, owner, reader, ctrl, span = fc.RESPONSES["R_qi"]
    assert reader == "matched" and ctrl is None
    unit, owner, reader, ctrl, span = fc.RESPONSES["R_ni"]
    assert ctrl == ("ice", "qi")            # the NUMBER row is the one gated


def test_the_mass_rows_are_marked_reader_dependent():
    """`column()` inverts the update, so its mass budget cannot fail to close.

    Measured on the factorial's own fixture, first call, legacy ice: -8.83e-17
    recovered against -6.006e-01 from the actual XFER records. A table that
    prints the first without saying which reader produced it invites the
    sentence "the mass closes", which the second refutes.
    """
    src = (ROOT / "g33_factorial.py").read_text()
    assert "close by construction" in src
    # ... and the diagnostic carries a name that cannot be mistaken for a budget
    assert "D_ni_metric" in fc.RESPONSES and "R_ni" in fc.RESPONSES
    assert fc.RESPONSES["D_ni_metric"][2] == "recovered"
    assert fc.RESPONSES["R_ni"][2] == "matched"


def test_the_mass_control_is_cut_to_the_SPAN_it_is_asked_about(monkeypatch):
    """A row that closes on call 1 and fails on call 7 failed a FIRST-CALL
    table too, because `usable()` reads every per-call record.

    The control is a property of the span the response is taken over.
    """
    import g33_matched_closure as mc
    good = {"call": 1, "residual": 0.0, "out": 1.0, "start": 1.0,
            "scale": 1.0, "ops": 8}
    bad = {"call": 7, "residual": 1.0, "out": 1.0, "start": 1.0,
           "scale": 1.0, "ops": 8}
    row = {"per_call": [good, bad], "residual": 1.0, "out": 1.0, "calls": 2}
    monkeypatch.setattr(mc, "closures", lambda s, b: {("ice", "qi", 1): row})
    _rows, first = fc._matched_rows("", frozenset({1}))
    _rows, whole = fc._matched_rows("", frozenset({1, 7}))
    assert first[("ice", 1)][0] is True          # the first call closed
    assert whole[("ice", 1)][0] is False         # the window did not


def test_same_atmosphere_compares_RAW_state_not_four_integrals(monkeypatch):
    """Two different vertical profiles can share a column integral.

    `sum m_k x_k` is equal for many `x_k`, so denominator equality is necessary
    and not sufficient -- and a factorial that accepts it can attribute a
    difference to the factor naming the arm when the arms did not start level.
    """
    import g33_refine_analyze as ra
    a = {("initial", "qv", 1, 0): 1.0, ("initial", "qv", 1, 1): 3.0,
         ("forcing", "rho", 1, 0): 1.0, ("state", "qv", 1, 0): 9.0}
    # same column integral (1+3 == 2+2), different profile
    b = dict(a)
    b[("initial", "qv", 1, 0)] = 2.0
    b[("initial", "qv", 1, 1)] = 2.0
    monkeypatch.setattr(ra, "read_text", lambda t: a if t == "A" else b)
    with pytest.raises(fc.FactorialError, match="same atmosphere"):
        fc.same_atmosphere({"legacy": "A", "nmass": "B"})
    monkeypatch.setattr(ra, "read_text", lambda t: a)
    fc.same_atmosphere({"legacy": "A", "nmass": "B"})    # identical: passes


def test_the_final_state_is_not_compared_by_the_same_atmosphere_gate(monkeypatch):
    """It compares what each arm was HANDED, not what it produced.

    Including `state` would make every working arm fail the control that is
    supposed to prove the arms were comparable.
    """
    import g33_refine_analyze as ra
    a = {("initial", "qv", 1, 0): 1.0, ("state", "qv", 1, 0): 9.0}
    b = {("initial", "qv", 1, 0): 1.0, ("state", "qv", 1, 0): 4.0}
    monkeypatch.setattr(ra, "read_text", lambda t: a if t == "A" else b)
    fc.same_atmosphere({"legacy": "A", "nmass": "B"})


def test_a_conditional_over_an_invalid_arm_is_null_not_a_number():
    """The validity discipline must not leak through the conditionals.

    A conditional is a mean over four arms; if one of them is not evidence, the
    conditional is not either. Reporting it anyway would let a number the
    contrast refused to score reappear one table down.
    """
    table = _table(lambda n, c, l: float(n), invalid={"legacy", "nmass"})
    got = fc.conditionals(table)["R_ni"]
    assert got["N_at_C0"] is None            # legacy and nmass are in this half
    assert got["N_at_C1"] == pytest.approx(1.0)   # ... and this one is clean


# ---------------------------------------------------------------------------
# The validity contract: a refusal that still hands over the answer is not one.

def test_an_invalid_contrast_carries_no_numbers():
    """The module promises a contrast is computed only where every arm is
    valid, and the previous version computed it anyway and attached
    `_valid: false` -- so the JSON carried a beta a reader, a binding or a
    notebook could pick up without ever consulting the flag."""
    table = _table(lambda n, c, l: float(n), invalid={"legacy"})
    b = fc.coefficients(table)["R_ni"]
    assert b["_valid"] is False and "legacy" in b["_invalid"]
    for term in ("", "N", "C", "L", "NC", "NL", "CL", "NCL", "_bound"):
        assert b[term] is None, term


def test_the_denominator_is_not_gated_by_a_mass_control():
    """It is the starting inventory, a state quantity. Gating it deleted the
    inventory half that numerator/denominator separation exists to expose."""
    assert fc.RESPONSES["R_ni_den"][3] is None
    assert fc.RESPONSES["R_ni_num"][3] == ("ice", "qi")
    assert fc.RESPONSES["R_ni"][3] == ("ice", "qi")


def test_a_zero_denominator_makes_the_ratio_invalid_not_zero(monkeypatch):
    """A/0 is undefined. Reporting 0.0 makes an unmeasurable ratio look like a
    residual that vanished -- the same shape as the coverage defect."""
    import g33_matched_closure as mc
    import g33_number_transport as nt
    pc = {"call": 1, "residual": 5.0, "out": 0.0, "start": 0.0,
          "scale": 1.0, "ops": 8}
    monkeypatch.setattr(mc, "closures", lambda s, b: {
        ("main", sp, 1): {"per_call": [dict(pc)], "residual": 5.0, "out": 0.0,
                          "calls": 1} for sp in ("qr", "nr")})
    monkeypatch.setattr(nt, "calls", lambda s: [{"outer_pre_sed": {}, "loops": {1}}])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    monkeypatch.setattr(fc, "_cap", lambda s, sc: {
        c: {"signed": 0.0, "destroyed": 0.0, "created": 0.0,
            "sum_abs": 0.0, "terms": 0} for c in ("main", "ice")})
    monkeypatch.setattr(fc, "_partition", lambda a, b: {
        k: 0.0 for k in fc.RESPONSES if k.startswith("partition_")})
    got = fc.responses("", "")
    assert got["R_qr_num"]["valid"] is True and got["R_qr_num"]["value"] == 5.0
    assert got["R_qr"]["valid"] is False
    assert "zero denominator" in got["R_qr"]["reason"]


def test_the_two_decompositions_are_checked_for_the_same_input(monkeypatch):
    """`check_identity` compared metadata and never state. Two streams can
    agree on nsplit, mode, rho, width, levels, delt and dtcld and still start
    from different atmospheres -- and then every partition count reads as a
    decomposition effect."""
    import g33_refine_analyze as ra
    a = {("initial", "qv", 1, 0): 1.0, ("forcing", "xland", 1, 0): 1.0}
    b = {("initial", "qv", 1, 0): 2.0, ("forcing", "xland", 1, 0): 1.0}
    monkeypatch.setattr(ra, "read_text", lambda t: a if t == "A" else b)
    with pytest.raises(fc.FactorialError, match="different inputs"):
        fc.same_input("legacy", "A", "B")
    monkeypatch.setattr(ra, "read_text", lambda t: a)
    fc.same_input("legacy", "A", "B")


def test_the_land_mask_is_part_of_what_is_compared():
    """`ncmin` branches on it and Arm L is the correction to that branch, so it
    is the one input L's causal story rests on."""
    import g33_refine_analyze as ra
    assert "xland" in ra._FORCING_NAMES
    assert ra._FORCING.match("G33R FORCING xland 1 3 3F800000")
    # ... and a name outside the set is still refused, so a typo cannot enter
    # as a silent new quantity.
    assert not ra._FORCING.match("G33R FORCING xlnd 1 3 3F800000")


def test_cross_arm_identity_carries_the_timestep():
    """delt/dtcld/loops were compared between the two decompositions and then
    dropped, so the cross-arm gate reading this dict could not see them."""
    import inspect
    src = inspect.getsource(fc.check_identity)
    ret = src[src.index("return {"):]
    for key in ("delt", "dtcld", "loops"):
        assert f'"{key}"' in ret, key


def test_simple_effects_say_whether_the_conditional_average_is_safe():
    """`N_at_C1` averages over L, so an N x L interaction inside that half is
    hidden in the mean. The two halves it is a mean of are reported."""
    row = fc.conditionals(_table(lambda n, c, l: float(n * c * (1 + l))))["R_ni"]
    assert row["N_at_C1_L0"] != row["N_at_C1_L1"]        # the mean would hide it
    flat = fc.conditionals(_table(lambda n, c, l: float(n * c)))["R_ni"]
    assert flat["N_at_C1_L0"] == flat["N_at_C1_L1"]
