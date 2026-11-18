"""Regression checks for full-call D1 graupel melt amount production."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_d1_melt_amount_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 melt amount replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def endpoint(data: dict, direction: str = "qg17_relative", h: str = "0.0001",
             side: str = "high") -> dict:
    return data["directions"][direction]["finite_differences"][h][side + "_stages"]


class ReplayTests(unittest.TestCase):
    def assert_saved_contract(self, actual: dict, saved: dict) -> None:
        # Only the independently recomputed libm slope and its ULP distance
        # are environment dependent. Branches, captured values and budgets
        # remain exact against the saved result.
        for key in (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "parent_entry_slope_stage_fields", "new_entry_pid_stage_fields",
            "new_melt_producer_stage_fields", "numeric_stage_tangents_per_direction",
            "melt_source_order_cases", "melt_source_order_fields_per_case",
            "native_melt_producer_words_raw_equal", "melt_minimum_branch_margins",
            "melt_amount_parent_value_handoff_cases", "melt_amount_parent_jvp_handoff_directions",
            "melt_fd_resolved_signal_count", "directional_applied_terms", "source_pins",
            "native_capture_receipts", "fd_branch_classifications",
            "entry_fd_resolved_signal_count", "entry_fd_rounding_floor_cases",
            "entry_one_sided_rounding_floor_cases", "pid_fd_resolved_signal_count",
            "pid_fd_rounding_floor_cases", "pid_one_sided_rounding_floor_cases",
            "scientific_status", "physical_unit_status",
        ):
            self.assertEqual(actual[key], saved[key])

        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        cases = {"baseline": cpp["baseline"]["stage_scalars"]}
        for direction in module.DIRECTIONS:
            for h, pair in cpp["directions"][direction]["finite_differences"].items():
                for side in ("low", "high"):
                    cases[f"{direction}/{h}/{side}"] = pair[side + "_stages"]
        self.assertEqual(len(cases), 25)
        portable = {"expected_rslope_g", "rslope_g_ulp_distance"}
        actual_rows = actual["entry_slope_branch_checks"]
        saved_rows = saved["entry_slope_branch_checks"]
        for summary, rows in ((actual, actual_rows), (saved, saved_rows)):
            self.assertEqual(len(rows), len(cases))
            self.assertEqual({row["case"] for row in rows}, set(cases))
            distances = []
            for row in rows:
                expected = row["expected_rslope_g"]
                distance = row["rslope_g_ulp_distance"]
                self.assertIs(type(distance), int)
                self.assertTrue(math.isfinite(expected) and expected > 0)
                captured = cases[row["case"]]["d1_entry_slope_inputs.rslope_g"]
                self.assertEqual(distance, module.ulp_distance(expected, captured))
                self.assertLessEqual(distance, 8)
                distances.append(distance)
            self.assertEqual(summary["maximum_entry_slope_formula_ulp_distance"], max(distances))

        def stable(rows: list[dict]) -> list[dict]:
            return [{key: value for key, value in row.items() if key not in portable}
                    for row in rows]

        self.assertEqual(stable(actual_rows), stable(saved_rows))

    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["new_melt_producer_stage_fields"], 62)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 306)
        self.assertEqual(actual["melt_source_order_fields_per_case"], 25)
        self.assertEqual(actual["native_melt_producer_words_raw_equal"], 186)
        self.assertEqual(actual["melt_fd_resolved_signal_count"], 70)
        self.assertLess(actual["max_captured_melt_signal_error"], 1e-6)
        self.assertLess(actual["max_small_step_melt_signal_error"], 1e-6)
        self.assertTrue(all(margin > 0 for margin in actual["melt_minimum_branch_margins"].values()))

    def test_permitted_parent_libm_ulp_is_portable(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        baseline = cpp["baseline"]["stage_scalars"]
        prefix = "d1_entry_slope_inputs."
        inputs = tuple(baseline[prefix + field] for field in ("qg", "dend", "pidn0g"))
        captured = baseline[prefix + "rslope_g"]
        original = module.source_order_rslope

        def one_ulp(qg: float, dend: float, pidn0g: float):
            expected, denominator, ratio = original(qg, dend, pidn0g)
            if (qg, dend, pidn0g) == inputs:
                expected = math.nextafter(captured, math.inf)
            return expected, denominator, ratio

        with mock.patch.object(module, "source_order_rslope", side_effect=one_ulp):
            actual = module.replay()
        self.assertEqual(actual["entry_slope_branch_checks"][0]["rslope_g_ulp_distance"], 1)
        self.assert_saved_contract(actual, saved)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 melt amount producer AD", proc.stdout)

    def test_rehashed_native_producer_word_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["d1_melt_producer.pgmlt_term2"] += 1e-8
        with self.assertRaisesRegex(ValueError, "native D1 melt producer f64 word"):
            module.replay(output_override=altered(change))

    def test_rehashed_uncaptured_t1_is_rejected(self) -> None:
        def change(data):
            endpoint(data)["d1_melt_producer.t1"] += 1e-3
        with self.assertRaisesRegex(ValueError, "D1 melt source-order"):
            module.replay(output_override=altered(change))

    def test_rehashed_uncaptured_raw_rate_is_rejected(self) -> None:
        def change(data):
            endpoint(data)["d1_melt_producer.pgmlt_raw"] += 1e-8
        with self.assertRaisesRegex(ValueError, "D1 melt source-order"):
            module.replay(output_override=altered(change))

    def test_rehashed_uncaptured_candidate_and_gate_are_rejected(self) -> None:
        def candidate(data):
            endpoint(data)["d1_melt_producer.pgmlt_dt"] += 1e-8
        with self.assertRaisesRegex(ValueError, "D1 melt source-order"):
            module.replay(output_override=altered(candidate))

        def gate(data):
            endpoint(data)["d1_melt_producer.graupel_active"] = False
        with self.assertRaisesRegex(ValueError, "D1 melt source-order gate"):
            module.replay(output_override=altered(gate))

    def test_joint_linear_raw_rate_tangent_mutation_is_rejected(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("d1_melt_producer.pgmlt_raw")
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 1e-8
        with self.assertRaisesRegex(ValueError, "D1 graupel raw-rate tangent"):
            module.replay(output_override=altered(change))

    def test_rehashed_applied_amount_tangent_is_rejected(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("d1_melt_producer.pgmlt_capped_g")
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 1e-6
        with self.assertRaisesRegex(ValueError, "D1 graupel active gate tangent"):
            module.replay(output_override=altered(change))

    def test_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
