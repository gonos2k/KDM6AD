"""Regression checks for the saved D1-to-pre2 rain-slope derivative path."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_rain_slope_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("rain-slope replay loader")
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
        for key in ("schema", "selected_cases", "native_d1_and_snap_words_raw_equal",
                    "d1_postgraupel_value_links_checked", "d1_postgraupel_tangent_links_checked",
                    "new_stage_fields", "numeric_stage_tangents_per_direction",
                    "joint_b2_nested_terms", "f32_reciprocal_dmr",
                    "scientific_status", "physical_unit_status"):
            self.assertEqual(actual[key], saved[key])
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["d1_postgraupel_value_links_checked"], 50)
        self.assertEqual(actual["d1_postgraupel_tangent_links_checked"], 6)
        self.assertEqual(actual["native_d1_and_snap_words_raw_equal"], 99)
        self.assertEqual(actual["new_stage_fields"], 51)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 200)
        self.assertLess(actual["max_captured_no_cap_signal_error"], 1e-6)
        self.assertLess(actual["max_uncaptured_small_step_signal_error"], 1e-6)
        self.assertGreater(min(actual["minimum_branch_margins"].values()), 0)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1-to-pre2 rain-slope input AD", proc.stdout)

    def test_rehashed_native_d1_word_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["d1_melt_consumer.qr2"] += 1e-6
        with self.assertRaisesRegex(ValueError, "native D1/snap word"):
            module.replay(output_override=altered(change))

    def test_rehashed_d234_handoff_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["high_stages"]["d234_rain.qr_after"] += 1e-6
        with self.assertRaisesRegex(ValueError, "rain value handoff"):
            module.replay(output_override=altered(change))

    def test_rehashed_postgraupel_qr2_endpoint_handoff_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["high_stages"]["d1_melt_consumer.qr2"] += 2e-16
        with self.assertRaisesRegex(ValueError, "rain value handoff"):
            module.replay(output_override=altered(change))

    def test_rehashed_postgraupel_nr2_tangent_handoff_is_rejected(self) -> None:
        def change(data):
            index = data["stage_numeric_order"].index("d1_melt_consumer.nr2")
            # Preserve the joint=sum(single) check while breaking the D1 handoff.
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][index] += 1e-5
        with self.assertRaisesRegex(ValueError, "rain tangent handoff"):
            module.replay(output_override=altered(change))

    def test_uncaptured_snow_intermediate_override_is_outside_arithmetic_scope(self) -> None:
        # Non-joint FD endpoints lack an independent qr1 capture. This packet
        # checks the post-graupel-to-final handoff, not the full D1 melt budget.
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["high_stages"]["d1_melt_consumer.qr1"] = 1.0
        result = module.replay(output_override=altered(change))
        self.assertEqual(result["d1_postgraupel_value_links_checked"], 50)

    def test_rehashed_rain_parameter_is_rejected(self) -> None:
        def change(data):
            # Inactive default does not change the active slope output by itself.
            data["baseline"]["stage_scalars"]["pre2_rain_producer.rslopermax"] *= 2
        with self.assertRaisesRegex(ValueError, "rain constant"):
            module.replay(output_override=altered(change))

    def test_rehashed_rain_slope_value_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["pre2_rain_producer.rslope2_r"] *= 1.01
        with self.assertRaisesRegex(ValueError, "rslope2_r ULP"):
            module.replay(output_override=altered(change))

    def test_rehashed_coordinated_rain_tangent_is_rejected(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("pre2_rain_producer.rslope_r")
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 1e-6
        with self.assertRaisesRegex(ValueError, "rain rslope input chain"):
            module.replay(output_override=altered(change))

    def test_rehashed_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
