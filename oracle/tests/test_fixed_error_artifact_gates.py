"""Numerical acceptance must use the caller-declared objective policy."""
import copy

import pytest
import torch

from kdm6.da_fulldomain import _part_loss, evaluate_artifact_gates


def fixed_report(y, bias, sigma, background, analysis):
    active_count = len(y)
    y, bias, sigma, background, analysis = (
        torch.tensor([x + [padding] * (9 - active_count)], dtype=torch.float64)
        for x, padding in zip((y, bias, sigma, background, analysis),
                              (280., 0., 1., 280., 280.)))
    mask = torch.zeros_like(y)
    mask[:, :active_count] = 1.
    jb = float(_part_loss(background, y, mask, 1., obs_sigma=sigma[0], obs_bias=bias))
    ja = float(_part_loss(analysis, y, mask, 1., obs_sigma=sigma[0], obs_bias=bias))
    tail = dict(total=0.1 + ja, j_state=0.1, j_theta=0., j_obs=ja)
    return dict(
        fixed_obs_errors=True, obs_error_source="synthetic counterexample",
        normalized_dry=True, bt_coordinate="kma_v3_0", observation_coordinate="kma_v3_0",
        n_subspace=1,
        obs_sigma_K=sigma[0].tolist(), obs_bias_shape=list(bias.shape),
        obs_bias_signature="a" * 64, obs_bias_definition="added_to_observation",
        huber_delta_coordinate="standardized_residual",
        omb=float((mask*(background-y).abs()).sum()/active_count),
        oma=float((mask*(analysis-y).abs()).sum()/active_count),
        omb_corrected=float((mask*(background-y-bias).abs()).sum()/active_count),
        oma_corrected=float((mask*(analysis-y-bias).abs()).sum()/active_count),
        omb_standardized=float((mask*((background-y-bias)/sigma).abs()).sum()/active_count),
        oma_standardized=float((mask*((analysis-y-bias)/sigma).abs()).sum()/active_count),
        j_trace=[dict(total=jb), tail], jb_final=.1, jobs_final=ja, jtheta_final=0.,
        n_window_evals=1, n_audit_evals=1, grad_norm_final=1., grad_theta_norm_final=0.,
        pathology_t0={}, pathology_slot={}, nonfinite_fields_t0=[], nonfinite_fields_slot=[])


@pytest.mark.parametrize("args, expected_raw, expected_final", [
    (([280.], [2.], [1.], [280.], [282.]), (0., 2.), .1),
    (([280., 280.], [0., 0.], [1., 10.], [282., 280.], [280., 283.]), (1., 1.5), .145),
])
def test_descending_fixed_objective_does_not_require_raw_mae_descent(args, expected_raw, expected_final):
    report = fixed_report(*args)
    assert (report["omb"], report["oma"]) == expected_raw
    assert report["j_trace"][0]["total"] == 1.5
    assert report["j_trace"][-1]["total"] == pytest.approx(expected_final)
    legacy = evaluate_artifact_gates(report)
    assert not legacy["oma_le_omb"] and not legacy["accepted"]
    fixed = evaluate_artifact_gates(report, expected_fixed_obs_errors=True)
    assert fixed["accepted"] and fixed["j_descended"]
    assert "oma_le_omb" not in fixed


@pytest.mark.parametrize("change, failed", [
    ({"fixed_obs_errors": False}, "fixed_error_marker"),
    ({"normalized_dry": False}, "fixed_error_metadata"),
    ({"bt_coordinate": "native"}, "fixed_error_metadata"),
    ({"observation_coordinate": "native"}, "fixed_error_metadata"),
    ({"obs_error_source": ""}, "fixed_error_metadata"),
    ({"obs_sigma_K": [True]}, "fixed_error_metadata"),
    ({"obs_bias_shape": [1, 2]}, "fixed_error_metadata"),
    ({"obs_bias_shape": [2, 9]}, "fixed_error_metadata"),
    ({"n_subspace": True}, "fixed_error_metadata"),
    ({"obs_bias_signature": ""}, "fixed_error_metadata"),
    ({"oma": float("nan")}, "finite_innovation_diagnostics"),
    ({"oma_corrected": -1.}, "finite_innovation_diagnostics"),
    ({"oma_standardized": float("inf")}, "finite_innovation_diagnostics"),
    ({"pathology_slot": {"qc": "invalid"}}, "pathology_slot_empty"),
    ({"n_audit_evals": None}, "final_audited"),
    ({"grad_norm_final": float("nan")}, "final_audited"),
])
def test_fixed_policy_keeps_existing_and_metadata_gates_fail_closed(change, failed):
    report = fixed_report([280.], [2.], [1.], [280.], [282.])
    report.update(change)
    gates = evaluate_artifact_gates(report, expected_fixed_obs_errors=True)
    assert not gates[failed] and not gates["accepted"]


def test_report_cannot_switch_legacy_runner_policy_by_its_own_marker():
    report = fixed_report([280.], [2.], [1.], [280.], [282.])
    report["omb"], report["oma"] = 2., 1.
    gates = evaluate_artifact_gates(report, expected_fixed_obs_errors=False)
    assert gates["oma_le_omb"] and not gates["fixed_error_marker"] and not gates["accepted"]


def test_fixed_policy_requires_final_audit_and_total_descent():
    report = fixed_report([280.], [2.], [1.], [280.], [282.])
    del report["n_audit_evals"]
    assert not evaluate_artifact_gates(report, expected_fixed_obs_errors=True)["final_audited"]
    report = fixed_report([280.], [2.], [1.], [280.], [282.])
    report["jb_final"] = 2.
    report["j_trace"][-1].update(j_state=2., total=2.)
    assert not evaluate_artifact_gates(report, expected_fixed_obs_errors=True)["j_descended"]


def test_legacy_reports_keep_original_gate_set_and_result():
    report = dict(j_trace=[dict(total=2.), dict(total=1.)], omb=2., oma=1.,
                  pathology_t0={}, pathology_slot={}, nonfinite_fields_t0=[],
                  nonfinite_fields_slot=[], grad_theta_norm_final=0.)
    old = evaluate_artifact_gates(report)
    assert old["accepted"] and old["oma_le_omb"]
    assert "fixed_error_marker" not in old and "fixed_error_metadata" not in old
    assert evaluate_artifact_gates(copy.deepcopy(report), expected_fixed_obs_errors=False)["accepted"]
