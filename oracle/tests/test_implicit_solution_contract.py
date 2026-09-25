"""A differentiable Newton step can still be the wrong physical solution."""

from dataclasses import replace
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from implicit_solution_contract import (  # noqa: E402
    NewtonResult, audit_positive_sqrt, newton_positive_sqrt,
)


def test_one_newton_step_has_correct_algorithmic_derivative_but_wrong_root():
    one = newton_positive_sqrt(4., 1., 1)
    assert one.value == 2.5
    assert one.algorithmic_tangent == .5
    h = 1e-5
    fd = (newton_positive_sqrt(4. + h, 1., 1).value
          - newton_positive_sqrt(4. - h, 1., 1).value) / (2 * h)
    assert fd == pytest.approx(.5, rel=1e-10)
    assert one.value * one.value - 4. == 2.25
    with pytest.raises(ValueError, match="state solve"):
        audit_positive_sqrt(4., one)


def test_converged_state_and_algorithmic_jvp_match_implicit_tangent():
    result = newton_positive_sqrt(4., 1., 7)
    audit = audit_positive_sqrt(4., result)
    assert result.value == pytest.approx(2.)
    assert audit.implicit_tangent == pytest.approx(.25)
    assert result.algorithmic_tangent == pytest.approx(.25, abs=1e-12)
    h = 1e-5
    fd = (newton_positive_sqrt(4. + h, 1., 7).value
          - newton_positive_sqrt(4. - h, 1., 7).value) / (2 * h)
    assert fd == pytest.approx(result.algorithmic_tangent, rel=1e-9)
    assert audit.scaled_state_residual < 1e-12
    assert abs(audit.tangent_residual) < 1e-10


def test_status_and_tangent_residual_are_separate_acceptance_gates():
    good = newton_positive_sqrt(4., 1., 7)
    with pytest.raises(ValueError, match="executed Newton iterations"):
        audit_positive_sqrt(4., replace(good, solver_converged=False))
    with pytest.raises(ValueError, match="executed Newton iterations"):
        audit_positive_sqrt(4., replace(good, algorithmic_tangent=.5))
    with pytest.raises(ValueError, match="active-set change"):
        audit_positive_sqrt(4., replace(good, active_set_changed=True))
    with pytest.raises(ValueError, match="executed Newton iterations"):
        audit_positive_sqrt(4., replace(good, value=2.00001, solver_converged=True))


def test_near_singular_and_nonfinite_inputs_are_not_called_converged():
    with pytest.raises(ValueError, match="too small"):
        audit_positive_sqrt(1e-24, NewtonResult(1e-12, 5e11, 1, True, 1e-12))
    with pytest.raises(ValueError, match="finite real"):
        newton_positive_sqrt(math.nan, 1., 1)
    with pytest.raises(ValueError, match="integer iteration"):
        newton_positive_sqrt(4., 1., True)
    with pytest.raises(ValueError, match="positive-root result"):
        audit_positive_sqrt(4., NewtonResult(-2., -.25, 7, True, 1.))


def test_zero_iteration_exact_root_needs_an_implicit_tangent():
    same_value = newton_positive_sqrt(4., 2., 0)
    assert same_value.solver_converged
    assert same_value.algorithmic_tangent == 0.
    with pytest.raises(ValueError, match="tangent equation"):
        audit_positive_sqrt(4., same_value)


def test_mathematically_consistent_fabrication_is_not_an_executed_derivative():
    with pytest.raises(ValueError, match="executed Newton iterations"):
        audit_positive_sqrt(4., NewtonResult(2., .25, 0, True, 2.))
    with pytest.raises(ValueError, match="executed Newton iterations"):
        audit_positive_sqrt(4., NewtonResult(2., .25, 1, True, 1.))
