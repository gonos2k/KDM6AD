import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "evidence/s10_czeroqg_prelink_plan_2026-09-26.json"
REPORT_PATH = ROOT / "evidence/s10_resource_capacity_command_gap_2026-09-27.json"


def test_s10_resource_report_arithmetic_and_blocked_gates_are_consistent():
    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    estimate = report["component_estimate_proposal"]
    capacity = estimate["capacity_calculation"]

    current_plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    assert report["prelink_plan_sha256"] == plan["resource_gate"][
        "resource_report_parent_plan_sha256"]
    assert report["prelink_plan_sha256"] != current_plan_sha
    estimate_path = ROOT / "evidence/s10_build_preparation_estimate_2026-09-27.json"
    assert plan["resource_gate"]["build_preparation"]["estimate_sha256"] == \
        hashlib.sha256(estimate_path.read_bytes()).hexdigest()
    component_total = sum(estimate["components_across_all_four_variants"].values())
    shared_total = sum(estimate["shared_staging_components"].values())
    assert component_total + shared_total == estimate["estimated_total_bytes_including_existing_case_tree"]
    assert (estimate["estimated_total_bytes_including_existing_case_tree"]
            - estimate["shared_staging_components"]["selected_case_tree_copy_bytes"]
            == estimate["estimated_future_incremental_bytes_excluding_already_staged_case_tree"])

    safety = capacity["safety_factor"]
    reserve = capacity["proposed_reserve_free_bytes"]
    assert (safety * estimate["estimated_total_bytes_including_existing_case_tree"] + reserve
            == capacity["required_free_bytes_using_total"])
    assert (safety * estimate["estimated_future_incremental_bytes_excluding_already_staged_case_tree"] + reserve
            == capacity["required_free_bytes_using_future_incremental"])
    assert (capacity["required_free_bytes_using_total"] - capacity["observed_free_bytes"]
            == capacity["shortfall_bytes_using_total"])
    assert (capacity["required_free_bytes_using_future_incremental"]
            - capacity["observed_free_bytes"]
            == capacity["shortfall_bytes_using_future_incremental"])
    assert capacity["shortfall_bytes_using_total"] > 0
    assert capacity["shortfall_bytes_using_future_incremental"] > 0
    assert (report["selected_case_tree"]["logical_bytes"]
            >= plan["resource_gate"]["build"]["planned_run_layout_reference"][
                "selected_case_logical_bytes"])

    assert estimate["approval_readiness"]["finite_s10_logging_on_upper_bound"] is False
    assert estimate["approval_readiness"]["final_estimate_valid_for_resource_gate"] is False
    assert estimate["approval_readiness"]["resource_gate_must_remain_blocked"] is True
    assert plan["resource_gate"]["status"] == "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
    assert plan["resource_gate"]["full_matrix_build_or_link_allowed"] is False
    assert report["status"]["preprocess_build_link_or_model_run_executed"] is False
    assert report["status"]["evidence_deleted_or_modified"] is False
