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


def _table(fn):
    """A response table from a function of the 0/1 factor levels."""
    return {arm: {r: fn(*fc.ALGO_FACTORS[arm]) for r in fc.RESPONSES}
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
    y = {(n, c): table[a]["R_ni"] for a, (n, c, l) in fc.ALGO_FACTORS.items()}
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
    assert fc.coefficients(table, screens)["partition_path"]["_bound"] == 0.0


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
    monkeypatch.setattr(fc, "_states", lambda t: a if t == "A" else b)
    with pytest.raises(fc.FactorialError, match="same states"):
        fc._partition("A", "B")


def test_partition_is_three_questions_not_one_count(monkeypatch):
    """First sub-step, final state, and how often they ever differed."""
    a = {(1, 1, 0): ("x",), (2, 1, 0): ("x",), (3, 1, 0): ("x",)}
    b = {(1, 1, 0): ("x",), (2, 1, 0): ("Z",), (3, 1, 0): ("Z",)}
    monkeypatch.setattr(fc, "_states", lambda t: a if t == "A" else b)
    got = fc._partition("A", "B")
    assert got["partition_first"] == 0.0        # they still agree after one
    assert got["partition_endpoint"] == 1.0     # and disagree at the end
    assert got["partition_path"] == 2.0         # having disagreed twice


def test_an_unrecoverable_row_is_a_refusal_not_a_zero_response(monkeypatch):
    """`column()` refuses mstep > 1, and `0.0` then means two different things.

    "the residual vanished" and "nothing in this span could be measured" are
    the same number under the old code. The span's coverage is checked against
    what it should have produced.
    """
    import g33_number_transport as nt
    call = {"outer_pre_sed": {(1, 1, 0): {}}, "loops": {1}}
    monkeypatch.setattr(nt, "calls", lambda s: [call])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    monkeypatch.setattr(nt, "column", lambda c, col, sp: None)
    with pytest.raises(fc.FactorialError, match="mstep"):
        fc.responses("", "")


def test_the_mass_rows_are_marked_reader_dependent():
    """`column()` inverts the update, so its mass budget cannot fail to close.

    Measured on the factorial's own fixture, first call, legacy ice: -8.83e-17
    recovered against -6.006e-01 from the actual XFER records. A table that
    prints the first without saying which reader produced it invites the
    sentence "the mass closes", which the second refutes.
    """
    src = (ROOT / "g33_factorial.py").read_text()
    assert "CLOSE BY CONSTRUCTION" in src
    assert "READER-DEPENDENT" in src
