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
    return {arm: {r: fn(*fc.ALGO_FACTORS[arm]) for r, _ in fc.RESPONSES}
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

    `cap_sink` reverses sign under C. Taking `|Y|` turns a large real effect
    into a small apparent one -- the reading that produced the withdrawn claim.
    """
    signed = fc.coefficients(_table(lambda n, c, l: 2.4 - 5.8 * c))
    folded = fc.coefficients(_table(lambda n, c, l: abs(2.4 - 5.8 * c)))
    assert signed["cap_sink"]["C"] == pytest.approx(-2.9)
    assert folded["cap_sink"]["C"] == pytest.approx(0.5)


def test_a_partial_factorial_is_refused_not_averaged():
    """Seven arms are not a 2^3 design, and a coefficient off seven is fiction."""
    table = _table(lambda n, c, l: float(n + c + l))
    table.pop("cons_nmasslncmin")
    with pytest.raises(SystemExit):
        fc.coefficients(table)


def test_terms_are_named_in_factor_order():
    """`CN` and `NC` name one term and read as two. Regression: sorted() gave both."""
    assert fc._subsets("NCL", 2) == ["NC", "NL", "CL"]
    assert fc._subsets("NCL", 3) == ["NCL"]


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
