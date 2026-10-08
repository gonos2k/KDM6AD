"""Synthetic receipt fixtures for the ordinary and failed-run artifact gates."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("run_native_kma_bt_frames.py")
SPEC = importlib.util.spec_from_file_location("nativecmp_gate_test", SCRIPT)
nativecmp = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(nativecmp)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_receipt_fixture(root: Path) -> tuple[Path, Path, dict]:
    root = root.resolve()
    run_id = "synthetic_failed_artifact_fixture"
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    forecast = run_dir / "klfs_lc05_fcst.202507190000"
    case_forecast = root / "case" / forecast.name
    case_forecast.parent.mkdir()
    payload = b"synthetic source-gate fixture; never parsed as model output"
    forecast.write_bytes(payload)
    case_forecast.write_bytes(payload)
    sha = digest(forecast)
    times = list(nativecmp.TARGET_FRAME_TIMES)
    receipt = {
        "status": "COMPLETE",
        "run_id": run_id,
        "run_directory": str(run_dir),
        "successful": False,
        "forecast_file_created": True,
        "forecast_generated": True,
        "fatal_or_error_lines_observed": True,
        "wrapper_marker_expected": "marker-v2-dry1",
        "runner_result": {
            "run_id": run_id,
            "exit_code": 1,
            "experiment_valid": False,
            "model_completed_flag": False,
            "wrf_success_complete_observed": True,
            "wrf_fatal_lines_observed": False,
            "mpi_abnormal_termination_observed": True,
            "wrapper_marker_observed": "marker-v2-dry1",
            "private_comparison_gate": "NOT_PASSED: runner exit_code is nonzero and experiment_valid is false",
            "invalid_reasons": ["model_did_not_complete"],
        },
        "completion_times": times,
        "latest_model_time": times[-1],
        "forecast": {"path": str(forecast), "sha256": sha, "times": times},
        "verified_output_discovery": {
            "status": "verified",
            "archive_path": str(forecast),
            "case_path": str(case_forecast),
            "archive_sha256": sha,
            "case_sha256": sha,
            "archive_case_hash_match": True,
            "times": times,
            "time_count": 8,
            "finite_all_numeric": True,
            "numeric_elements_checked": 635785640,
            "variable_count": 254,
            "numeric_variable_count": 253,
        },
        "executable_sha256": "exe-sha",
        "library_sha256": "lib-sha",
        "binary_after_hashes": {
            "executable_stable": True,
            "executable_sha256_before": "exe-sha",
            "executable_sha256_after": "exe-sha",
            "library_stable": True,
            "library_sha256_before": "lib-sha",
            "library_sha256_after": "lib-sha",
        },
        "final_input_hashes": {
            "wrfinput_d01": {"stable": True, "before": "input-sha", "after": "input-sha"}
        },
    }
    receipt_path = root / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    return receipt_path, forecast, receipt


class FailedRunArtifactGateTests(unittest.TestCase):
    def test_ordinary_gate_rejects_runner_invalid_complete_receipt(self):
        with tempfile.TemporaryDirectory(prefix="kdm6ad-invalid-receipt-") as tmp:
            receipt_path, _, receipt = make_receipt_fixture(Path(tmp))
            with self.assertRaisesRegex(RuntimeError, "successful, experiment-valid"):
                nativecmp.validate_completed_run(receipt_path, receipt["run_id"], None)

    def test_diagnostic_gate_requires_exact_runner_and_verified_artifact_fields(self):
        with tempfile.TemporaryDirectory(prefix="kdm6ad-diagnostic-receipt-") as tmp:
            receipt_path, forecast, receipt = make_receipt_fixture(Path(tmp))
            accepted, accepted_forecast = nativecmp.validate_failed_run_artifact_diagnostic(
                receipt_path, receipt["run_id"], forecast)
            self.assertFalse(accepted["runner_result"]["experiment_valid"])
            self.assertTrue(accepted["runner_result"]["wrf_success_complete_observed"])
            self.assertEqual(accepted_forecast, forecast.resolve())

            broken = copy.deepcopy(receipt)
            broken["verified_output_discovery"]["archive_case_hash_match"] = False
            broken_path = Path(tmp) / "broken_receipt.json"
            broken_path.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError, "finite-output/hash verification"):
                nativecmp.validate_failed_run_artifact_diagnostic(
                    broken_path, receipt["run_id"], forecast)

    def test_solar_disable_changes_only_the_staged_fixture_copy(self):
        with tempfile.TemporaryDirectory(prefix="kdm6ad-thermal-fixture-") as tmp:
            root = Path(tmp)
            original = root / "original" / "out" / "rttov_test.txt"
            original.parent.mkdir(parents=True)
            original.write_text("&rttov_test_nml\n  defn%opts%rt_all%solar = .TRUE.\n/\n")
            original_simple = root / "original" / "in/profiles/001/atm/simple_cloud.txt"
            original_simple.parent.mkdir(parents=True)
            original_simple.write_text("&simple_cloud\n ctp = 949.0\n cfraction = 0.6\n/\n")
            staged_case = root / "staged"
            (staged_case / "out").mkdir(parents=True)
            staged_simple = staged_case / "in/profiles/001/atm/simple_cloud.txt"
            staged_simple.parent.mkdir(parents=True)
            staged_simple.write_bytes(original_simple.read_bytes())
            staged = staged_case / "out" / "rttov_test.txt"
            staged.write_bytes(original.read_bytes())
            original_sha = digest(original)
            original_simple_sha = digest(original_simple)

            modes = nativecmp.stage_thermal_only_fixture(staged_case)

            self.assertEqual(digest(original), original_sha)
            self.assertEqual(digest(original_simple), original_simple_sha)
            self.assertEqual(digest(staged), modes["solar_namelist_sha256"])
            self.assertIn("solar = .FALSE.", staged.read_text())
            self.assertEqual(modes["original_simple_cloud_fraction"], 0.6)
            self.assertEqual(modes["staged_simple_cloud_fraction"], 0.0)
            self.assertEqual(float(re.search(r"(?im)^\s*ctp\s*=\s*([^\n]+)", staged_simple.read_text()).group(1)), 949.0)
            self.assertEqual(float(re.search(r"(?im)^\s*cfraction\s*=\s*([^\n]+)", staged_simple.read_text()).group(1)), 0.0)


if __name__ == "__main__":
    unittest.main()
