"""Portable PR406 admission tests; private native/reference replay is local-only.

The evidence modules remain the single source of these test cases. This facade
exposes receipt, case-clock, pending-input, L1B and fixture admission to oracle CI.
It does not represent the private core or actual M/H/analysis as CI coverage.
"""
import importlib.util
import json
from pathlib import Path

import pytest


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
    "test_observation_source_binding_checks_metadata_payload_slot_and_seven_dqf",
}
for _name, _function in vars(_intake_tests).items():
    if _name.startswith("test_") and _name not in _private_reference_tests:
        globals()[_name] = _function

_adapter_tests = _load("portable_case_adapter_tests", "test_case_analysis_adapter.py")
test_wrong_fixture_rejected_before_loading_or_creating_outputs = (
    _adapter_tests.test_wrong_fixture_rejected_before_loading_or_creating_outputs
)


@pytest.fixture(autouse=True)
def _forbid_native_reference_access(monkeypatch):
    """Every test collected here must work without the owner's private assets."""
    def forbidden(*args, **kwargs):
        pytest.fail("portable admission tests must not load native/reference assets")
    monkeypatch.setattr(_intake_tests.intake, "_load_legacy", forbidden)
    monkeypatch.setattr(_intake_tests.intake.netCDF4, "Dataset", forbidden)


def test_l1b_receipt_admission_never_loads_private_native_reference(tmp_path, monkeypatch):
    """Bind source receipts directly, without extracting a native core."""
    intake = _intake_tests.intake
    monkeypatch.setattr(intake, "_load_legacy", lambda: pytest.fail("receipt admission must not load native assets"))
    payload = tmp_path / "synthetic_payload.bin"
    payload.write_bytes(b"hash-provenance-only; not a decoded scene")
    pixel = {"row": 320, "column": 48, "latitude_deg": 35.41925069326254,
             "longitude_deg": 122.13724164654832,
             "reader_dqf_by_channel": {n: 0 for n in intake.ANALYSIS_CHANNEL_NAMES.values()}}
    slot = "202507190556"
    scene = {"date": "20250719", "selected_nominal_slot_obt": slot, "nearest_pixel": pixel,
             "status": "POINT_WITHIN_RADIUS", "nearest_pixel_within_2p5km": True,
             "time_interpretation": "Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; payload valid_time_utc remains unset."}
    metadata = {"private_npz_path": str(payload), "private_npz_sha256": intake.sha256_file(payload),
                "scenes": [{**scene, "reader_metadata": {
                    "nominal_slot_obt": slot, "pixel_utc_time_verified": False,
                    "payload_valid_time_role": "unset; filename label is OBT and no documented UTC conversion was applied",
                    "projection_type": "GEOS", "geos": {"cfac": 1},
                    "geos_header_upper_left_rad": {"image_upperleft_latitude": 0.77, "image_upperleft_longitude": 2.09},
                    "image_shape": [500, 500], "channels": ["wv063", "wv069", *intake.ANALYSIS_CHANNEL_NAMES.values()]}}]}
    meta_path = tmp_path / "DECODE_RECEIPT.json"
    meta_path.write_text(json.dumps(metadata))
    result = {"schema": "pr403_gk2a_l1b_heldout_result_v1", "status": "DECODED_GK2A_L1B_SCENES_ONLY",
              "private_payload_path": str(payload), "private_payload_sha256": intake.sha256_file(payload),
              "private_decode_receipt_path": str(meta_path), "scenes": [scene]}
    result_path = tmp_path / "RESULT.json"
    result_path.write_text(json.dumps(result))
    obs = {"source_result_path": str(result_path), "source_result_sha256": intake.sha256_file(result_path),
           "source_payload_path": str(payload), "source_payload_sha256": intake.sha256_file(payload),
           "source_metadata_path": str(meta_path), "source_metadata_sha256": intake.sha256_file(meta_path),
           "nearest_pixel": {k: pixel[k] for k in ("row", "column", "latitude_deg", "longitude_deg")}}
    case = _intake_tests.case_template(output_dir=tmp_path / "unused-native-output", l1b=obs)
    bound = intake._load_result_binding(intake.validate_case(case))
    assert bound["binding_status"] == "BOUND_GK2A_L1B_SCENE"
    assert len(bound["analysis_channel_dqf"]) == 7
    pixel["reader_dqf_by_channel"]["ir105"] = 1
    result_path.write_text(json.dumps(result))
    meta_path.write_text(json.dumps(metadata))
    case["observation"].update(source_result_sha256=intake.sha256_file(result_path),
                                source_metadata_sha256=intake.sha256_file(meta_path))
    with pytest.raises(ValueError, match="seven admitted analysis-channel"):
        intake._load_result_binding(intake.validate_case(case))
    assert not (tmp_path / "unused-native-output").exists()
