"""Portable PR406 admission tests; private native/reference replay is local-only.

The evidence modules remain the single source of these test cases. This facade
exposes receipt, case-clock, pending-input, L1B and fixture admission to oracle CI.
It does not represent the private core or actual M/H/analysis as CI coverage.
"""
import importlib.util
from pathlib import Path


PACKET = Path(__file__).resolve().parents[2] / "harness/evidence/pr406_native_case_consumer_2026-10-11"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PACKET / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_intake_tests = _load("portable_case_intake_tests", "test_native_case_intake.py")
_private_reference_tests = {
    "test_actual_netcdf_selected_hyperslab_helper_uses_case_column_and_mask_checks",
    "test_parameterized_selected_frame_reads_expected_j_i_without_global_mutation",
    "test_core_intake_needs_only_background_and_optional_diagnostics_are_separate",
    "test_existing_declared_diagnostic_time_adds_only_that_exact_native_frame",
}
for _name, _function in vars(_intake_tests).items():
    if _name.startswith("test_") and _name not in _private_reference_tests:
        globals()[_name] = _function

_adapter_tests = _load("portable_case_adapter_tests", "test_case_analysis_adapter.py")
test_wrong_fixture_rejected_before_loading_or_creating_outputs = (
    _adapter_tests.test_wrong_fixture_rejected_before_loading_or_creating_outputs
)
