"""Read-only PR398-vs-PR397 evidence comparison; no model or H/M calls."""
from __future__ import annotations


def build_comparison_audit(result: dict, baseline_result: dict,
                           baseline_driver: dict, preflight: dict,
                           h_signature_source: str,
                           current_driver_checks: dict | None = None) -> dict:
    current_objective = result["objective"]
    baseline_objective = baseline_result["objective"]
    current_initial = current_objective["initial_zero_control_closure"]
    baseline_initial = baseline_objective["initial_zero_control_closure"]
    current_h = dict(result["effective_h_configuration"])
    baseline_h = dict(baseline_result["effective_h_configuration"])
    current_fixture_path = current_h.pop("fixture_case_dir", None)
    baseline_fixture_path = baseline_h.pop("fixture_case_dir", None)
    h_diff_fields = sorted(key for key in set(current_h) | set(baseline_h)
                           if current_h.get(key) != baseline_h.get(key))

    baseline_assets_stable = (
        baseline_driver.get("rttov_fixture_immutable_during_analysis") is True
        and baseline_driver.get("rttov_execution_assets_stable_during_analysis") is True
        and baseline_driver.get("fixture_hashes_before")
        == baseline_driver.get("fixture_hashes_after")
        and baseline_driver.get("rttov_execution_assets_before")
        == baseline_driver.get("rttov_execution_assets_after")
    )
    expected_baseline_hashes = baseline_driver.get("fixture_hashes_before", {})
    current_fixture_hashes = preflight["template_hashes"]["fixture_files"]
    current_assets = preflight["template_hashes"]["execution_assets"]
    baseline_assets = baseline_driver.get("rttov_execution_assets_before", {})
    fixture_files_match = current_fixture_hashes == expected_baseline_hashes
    executable_match = (current_assets.get("executable", {}).get("sha256")
                        == baseline_assets.get("executable", {}).get("sha256"))
    coefficient_match = (current_assets.get("coefficient", {}).get("sha256")
                         == baseline_assets.get("coefficient", {}).get("sha256"))

    baseline_mask_sha = baseline_initial["frozen_mask"]["sha256_f64"]
    current_mask_sha = current_initial["frozen_mask"]["sha256_f64"]
    initial_signature = current_initial["operator_signature_sha256"]
    final_signature = current_objective["final_audit_signature"]["sha256"]
    baseline_signature = baseline_initial["operator_signature_sha256"]
    source_covers_config_path = "rttov_cfg=rttov_cfg" in h_signature_source
    old_driver_failed = sorted(key for key, value in
                              (current_driver_checks or {}).items()
                              if value is False)

    checks = {
        "same_initial_zero_control_Jo": current_initial["Jo"] == baseline_initial["Jo"],
        "same_initial_frozen_mask": current_mask_sha == baseline_mask_sha,
        "same_initial_valid_count": current_initial["n_valid"] == baseline_initial["n_valid"],
        "within_run_trace_signatures_stable": (
            current_objective["final_audit_signature"]["all_trace_signatures_match"] is True),
        "within_run_initial_matches_accepted_signature": (
            current_initial["signature_matches_final_accepted_audit"] is True
            and initial_signature == final_signature),
        "effective_h_config_equal_except_fixture_path": not h_diff_fields,
        "baseline_fixture_assets_stable": baseline_assets_stable,
        "fixture_files_match_pr397": fixture_files_match,
        "executable_matches_pr397": executable_match,
        "coefficient_matches_pr397": coefficient_match,
        "signature_source_hashes_rttov_config": source_covers_config_path,
        "raw_cross_run_signature_equal": initial_signature == baseline_signature,
    }
    expected_path_sensitive_difference = (
        not checks["raw_cross_run_signature_equal"]
        and current_fixture_path != baseline_fixture_path
        and not h_diff_fields and baseline_assets_stable and fixture_files_match
        and executable_match and coefficient_match and source_covers_config_path
    )
    all_input_audit_checks_pass = all(
        value for key, value in checks.items() if key != "raw_cross_run_signature_equal")
    if all_input_audit_checks_pass and expected_path_sensitive_difference:
        status = "SAME_FIXED_H_INPUTS_PATH_SENSITIVE_RAW_SIGNATURE_DIFFERENCE"
    elif all_input_audit_checks_pass and checks["raw_cross_run_signature_equal"]:
        status = "SAME_FIXED_H_INPUTS_AND_RAW_SIGNATURE"
    else:
        status = "COMPARISON_INCOMPLETE_OR_DIFFERENT"

    return {
        "schema": "pr398_postrun_comparison_audit_v1",
        "status": status,
        "checks": checks,
        "driver_original_failed_checks": old_driver_failed,
        "raw_signature": {
            "pr397_initial_sha256": baseline_signature,
            "pr398_initial_sha256": initial_signature,
            "pr398_final_sha256": final_signature,
            "within_pr398_initial_equals_final": initial_signature == final_signature,
            "fixture_case_dir_pr397": baseline_fixture_path,
            "fixture_case_dir_pr398": current_fixture_path,
            "effective_h_configuration_differing_fields": h_diff_fields,
            "interpreted_difference": (
                "The raw signature differs because the signature hashes the full H configuration, "
                "which contains the distinct isolated fixture_case_dir; all remaining effective "
                "configuration values and the hash-bound assets match."
                if expected_path_sensitive_difference else "No path-only signature explanation was established."),
        },
        "preservation": {
            "capture_result_modified": False,
            "original_driver_receipt_modified": False,
            "private_checkpoint_modified": False,
            "additional_model_M_or_H_calls": 0,
            "retry": False,
        },
        "interpretation_boundary": {
            "capture_status": result.get("status"),
            "science_acceptance": result.get("physical_matchup_and_science_acceptance", {}).get("status"),
            "signature_interpretation_is_source_inference": True,
        },
    }
