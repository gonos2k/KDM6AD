"""Regression checks for the archived native NC/NCCN process graph."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_nc_process_graph_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("process graph replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        for key in ("schema", "baseline_stage_words_raw_equal",
                    "joint_endpoint_stage_words_raw_equal", "parent_full_state_endpoints_raw_equal",
                    "numeric_stage_tangents_per_direction", "final_vjp_components_per_seed",
                    "captured_no_cap_pairs", "extra_small_step_pairs_without_cap_capture",
                    "recorded_cap_crossing_pairs", "scientific_status", "physical_unit_status"):
            self.assertEqual(actual[key], saved[key])
        self.assertEqual(actual["baseline_stage_words_raw_equal"], 127)
        self.assertEqual(actual["joint_endpoint_stage_words_raw_equal"], 254)
        self.assertEqual(actual["parent_full_state_endpoints_raw_equal"], 24)
        self.assertLess(actual["max_captured_no_cap_signal_error"], 1e-6)
        self.assertLess(actual["max_uncaptured_small_step_signal_error"], 1e-6)
        self.assertEqual(actual["directions"]["joint17_relative"]["final_jvp"][1], 0.0)
        self.assertAlmostEqual(actual["directions"]["joint17_relative"]["final_jvp"][0],
                               1182464.5883038137, places=7)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified full-call native NC/NCCN process graph", proc.stdout)

    def test_rehashed_baseline_stage_word_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["naacw_producer.naacw"] += 1e-6
        with self.assertRaisesRegex(ValueError, "baseline stage raw word"):
            module.replay(output_override=altered(change))

    def test_rehashed_joint_endpoint_word_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["joint17_relative"]["finite_differences"]["0.001"]
            pair["high_stages"]["pre2_producer.avtg"] += 1e-6
        with self.assertRaisesRegex(ValueError, "joint stage capture"):
            module.replay(output_override=altered(change))

    def test_rehashed_warm_rate_tangent_is_rejected(self) -> None:
        def change(data):
            order = data["stage_numeric_order"]
            i = order.index("nc_budget.nracw")
            data["directions"]["joint17_relative"]["stage_jvp"][i] += 100.0
        with self.assertRaisesRegex(ValueError, "full NC budget derivative"):
            module.replay(output_override=altered(change))

    def test_rehashed_shared_intermediate_offset_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["low_stages"]["naacw_producer.ngacw"] += 1.0
            pair["high_stages"]["naacw_producer.ngacw"] += 1.0
        with self.assertRaisesRegex(ValueError, "FD one-sided baseline"):
            module.replay(output_override=altered(change))

    def test_rehashed_floor_branch_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["low_stages"]["fd_satadj_inner.nccn_floor_active"] = 0.0
        with self.assertRaisesRegex(ValueError, "activation/reservoir gates"):
            module.replay(output_override=altered(change))

    def test_rehashed_final_nc_vjp_is_rejected(self) -> None:
        def change(data):
            data["vjp"]["final_nc16"][6 * 39 + 16] += 1.0
        with self.assertRaisesRegex(ValueError, "parent NC16 VJP raw"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
