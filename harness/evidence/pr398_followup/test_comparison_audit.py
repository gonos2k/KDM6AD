from __future__ import annotations

from comparison_audit import build_comparison_audit


def test_path_sensitive_signature_does_not_fail_input_configuration_comparison():
    result, baseline, baseline_driver, preflight, source = _synthetic_case()
    audit = build_comparison_audit(
        result, baseline, baseline_driver, preflight, source,
        current_driver_checks={"same_pr397_initial_signature": False})

    assert audit["checks"]["raw_cross_run_signature_equal"] is False
    assert audit["checks"]["within_run_trace_signatures_stable"] is True
    assert audit["checks"]["effective_h_config_equal_except_fixture_path"] is True
    assert audit["status"] == "SAME_FIXED_H_INPUTS_PATH_SENSITIVE_RAW_SIGNATURE_DIFFERENCE"
    assert audit["driver_original_failed_checks"] == ["same_pr397_initial_signature"]


def test_actual_h_configuration_change_is_not_accepted_as_path_scoped():
    audit = _synthetic_audit()
    assert audit["status"] == "SAME_FIXED_H_INPUTS_PATH_SENSITIVE_RAW_SIGNATURE_DIFFERENCE"
    result, baseline, baseline_driver, preflight, source = _synthetic_case()
    result["effective_h_configuration"]["channels"] = [10, 12]
    changed = build_comparison_audit(result, baseline, baseline_driver,
                                     preflight, source)
    assert changed["checks"]["effective_h_config_equal_except_fixture_path"] is False
    assert changed["status"] == "COMPARISON_INCOMPLETE_OR_DIFFERENT"


def test_changed_assets_or_unstable_within_run_signature_are_rejected():
    result, baseline, baseline_driver, preflight, source = _synthetic_case()
    preflight["template_hashes"]["execution_assets"]["coefficient"]["sha256"] = "changed"
    changed_asset = build_comparison_audit(
        result, baseline, baseline_driver, preflight, source)
    assert changed_asset["checks"]["coefficient_matches_pr397"] is False
    assert changed_asset["status"] == "COMPARISON_INCOMPLETE_OR_DIFFERENT"

    result, baseline, baseline_driver, preflight, source = _synthetic_case()
    result["objective"]["final_audit_signature"]["all_trace_signatures_match"] = False
    unstable = build_comparison_audit(
        result, baseline, baseline_driver, preflight, source)
    assert unstable["checks"]["within_run_trace_signatures_stable"] is False
    assert unstable["status"] == "COMPARISON_INCOMPLETE_OR_DIFFERENT"


def _synthetic_case():
    mask = {"sha256_f64": "mask"}
    baseline = {
        "effective_h_configuration": {"channels": [10, 11], "fixture_case_dir": "/run/pr397"},
        "objective": {"initial_zero_control_closure": {
            "Jo": 12.0, "n_valid": 2, "frozen_mask": mask,
            "operator_signature_sha256": "baseline-signature"}},
    }
    baseline_driver = {
        "rttov_fixture_immutable_during_analysis": True,
        "rttov_execution_assets_stable_during_analysis": True,
        "fixture_hashes_before": {"skin.txt": "skin"},
        "fixture_hashes_after": {"skin.txt": "skin"},
        "rttov_execution_assets_before": {
            "executable": {"sha256": "exe"}, "coefficient": {"sha256": "coef"}},
        "rttov_execution_assets_after": {
            "executable": {"sha256": "exe"}, "coefficient": {"sha256": "coef"}},
    }
    preflight = {
        "template_hashes": {
            "fixture_files": {"skin.txt": "skin"},
            "execution_assets": {"executable": {"sha256": "exe"},
                                 "coefficient": {"sha256": "coef"}},
        },
    }
    result = {
        "status": "RETURNED_DIAGNOSTIC_ONLY",
        "effective_h_configuration": {"channels": [10, 11], "fixture_case_dir": "/run/pr398"},
        "objective": {
            "initial_zero_control_closure": {
                "Jo": 12.0, "n_valid": 2, "frozen_mask": mask,
                "operator_signature_sha256": "isolated-path-signature",
                "signature_matches_final_accepted_audit": True,
            },
            "final_audit_signature": {
                "sha256": "isolated-path-signature",
                "all_trace_signatures_match": True,
            },
        },
        "physical_matchup_and_science_acceptance": {"status": "NOT_ASSESSED"},
    }
    source = "_h_signature(..., rttov_cfg=rttov_cfg, ...)"
    return result, baseline, baseline_driver, preflight, source


def _synthetic_audit():
    result, baseline, baseline_driver, preflight, source = _synthetic_case()
    return build_comparison_audit(
        result, baseline, baseline_driver, preflight, source,
        current_driver_checks={"same_pr397_initial_signature": False})
