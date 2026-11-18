"""Regression checks for the archived full-call pre2 input derivative bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_pre2_input_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("pre2 input replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_results_and_limits(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual["baseline_final_values_raw_equal"], 468)
        self.assertEqual(actual["baseline_pre2_inputs_raw_equal"], 78)
        self.assertEqual(actual["parent_fd_endpoints_raw_equal"], 18)
        self.assertEqual((actual["captured_no_cap_pairs"], actual["captured_cap_crossing_pairs"],
                          actual["extra_small_step_pairs_without_cap_capture"]), (7, 2, 3))
        for name, info in actual["directions"].items():
            self.assertLess(info["max_captured_no_cap_signal_error"], 1e-6, name)
            self.assertLess(info["max_uncaptured_small_step_signal_error"], 1e-6, name)
            self.assertLess(info["max_one_sided_error"], 2e-3, name)
        self.assertEqual(actual["directions"]["joint17_relative"]["recorded_cap_crossing_steps"], [])
        self.assertEqual(actual["scientific_status"], "INCONCLUSIVE")

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified full-call C++ AD into pre2 inputs", proc.stdout)

    def test_rehashed_baseline_pre2_word_is_rejected(self) -> None:
        def change(data):
            word = data["baseline"]["pre2_qg_raw"][15]
            data["baseline"]["pre2_qg_raw"][15] = format(int(word, 16) + 1, "x")
        with self.assertRaisesRegex(ValueError, "39-layer pre2 input raw"):
            module.replay(output_override=altered(change))

    def test_rehashed_joint_input_seed_is_rejected(self) -> None:
        def change(data):
            data["directions"]["joint17_relative"]["seed_brs17"] = 0.0
        with self.assertRaisesRegex(ValueError, "relative input seed"):
            module.replay(output_override=altered(change))

    def test_rehashed_coordinated_tangent_change_is_rejected_by_fd(self) -> None:
        def change(data):
            for index in (module.QG17, module.BRS17):
                data["vjp"]["pre2_qg"][index] = 0.0
            for direction in data["directions"].values():
                direction["jvp"][0] = 0.0
        with self.assertRaisesRegex(ValueError, "FD signal derivative"):
            module.replay(output_override=altered(change))

    def test_rehashed_parent_endpoint_change_is_rejected(self) -> None:
        def change(data):
            endpoint = data["directions"]["joint17_relative"]["finite_differences"]["0.001"]
            word = endpoint["high_final_raw"][8 * 39 + 15]
            endpoint["high_final_raw"][8 * 39 + 15] = format(int(word, 16) + 1, "x")
        with self.assertRaisesRegex(ValueError, "FD parent final state"):
            module.replay(output_override=altered(change))

    def test_rehashed_shared_endpoint_offset_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["low"][0] += 2**-20
            pair["high"][0] += 2**-20
        with self.assertRaisesRegex(ValueError, "FD one-sided baseline"):
            module.replay(output_override=altered(change))

    def test_off_direction_vjp_rewrite_is_outside_arithmetic_scope(self) -> None:
        # The original hash pins the archived row. Public arithmetic probes only
        # the two selected input coordinates, not independent FD for all 468.
        def change(data):
            data["vjp"]["pre2_qg"][0] = 1e12
        result = module.replay(output_override=altered(change))
        self.assertEqual(result["vjp_components_recorded_per_output"], 468)
        self.assertEqual(result["vjp_coordinates_independently_fd_checked"], 2)


if __name__ == "__main__":
    unittest.main()
