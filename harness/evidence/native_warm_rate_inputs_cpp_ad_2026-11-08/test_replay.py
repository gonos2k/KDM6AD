"""Regression checks for saved native B1/B2 warm-rate input derivatives."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_warm_rate_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("warm-rate replay loader")
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
        for key in ("schema", "baseline_and_endpoint_cases", "new_b1_inputs",
                    "existing_native_b2_words_raw_equal", "new_numeric_stage_tangents_per_direction",
                    "directional_producer_terms", "scientific_status", "physical_unit_status"):
            self.assertEqual(actual[key], saved[key])
        self.assertEqual(actual["baseline_and_endpoint_cases"], 25)
        self.assertEqual(actual["existing_native_b2_words_raw_equal"], 51)
        self.assertEqual(actual["new_numeric_stage_tangents_per_direction"], 149)
        self.assertLess(actual["max_captured_no_cap_signal_error"], 1e-6)
        self.assertLess(actual["max_uncaptured_small_step_signal_error"], 1e-6)
        self.assertGreater(min(actual["warm_branch_minimum_margins"].values()), 0)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native B1/B2 warm-rate input AD", proc.stdout)

    def test_rehashed_native_b2_word_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["nracw_producer.rslope3_r"] *= 1.001
        with self.assertRaisesRegex(ValueError, "native B2 word"):
            module.replay(output_override=altered(change))

    def test_rehashed_b1_constant_is_rejected_by_producer(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["nraut_producer.qck1"] *= 1.01
        with self.assertRaisesRegex(ValueError, "B1 parameter word"):
            module.replay(output_override=altered(change))

    def test_rehashed_inactive_b1_coefficient_is_rejected(self) -> None:
        def change(data):
            # Rain swap is active, so changing the unused default coefficient
            # leaves nraut and every branch/value unchanged without this pin.
            data["baseline"]["stage_scalars"]["nraut_producer.nraut_coeff"] = 1e9
        with self.assertRaisesRegex(ValueError, "B1 parameter word"):
            module.replay(output_override=altered(change))

    def test_rehashed_inactive_b2_endpoint_constant_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["1e-06"]
            pair["high_stages"]["nracw_producer.ncrk2"] *= 2.0
        with self.assertRaisesRegex(ValueError, "fixed B2 parameter"):
            module.replay(output_override=altered(change))

    def test_rehashed_b1_return_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["nraut_producer.nraut"] += 0.0001
        with self.assertRaisesRegex(ValueError, "B1 nraut ULP"):
            module.replay(output_override=altered(change))

    def test_rehashed_b2_input_tangent_is_rejected(self) -> None:
        def change(data):
            order = data["stage_numeric_order"]
            i = order.index("nracw_producer.rslope3_r")
            # Preserve joint linearity to test the B2 producer chain independently.
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 1e-12
        with self.assertRaisesRegex(ValueError, "B2 input chain"):
            module.replay(output_override=altered(change))

    def test_rehashed_shared_b2_gate_offset_is_rejected_by_one_sided_fd(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["low_stages"]["nracw_producer.avedia_r"] += 1e-5
            pair["high_stages"]["nracw_producer.avedia_r"] += 1e-5
        with self.assertRaisesRegex(ValueError, "FD warm input one-sided baseline"):
            module.replay(output_override=altered(change))

    def test_rehashed_b1_swap_boundary_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["low_stages"]["nraut_producer.qr"] = pair["low_stages"]["nraut_producer.lenconcr"]
        with self.assertRaisesRegex(ValueError, "B1 strict active/swap"):
            module.replay(output_override=altered(change))

    def test_rehashed_missing_vjp_rows_are_rejected(self) -> None:
        def change(data):
            data["vjp"] = {}
        with self.assertRaisesRegex(ValueError, "VJP row inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
