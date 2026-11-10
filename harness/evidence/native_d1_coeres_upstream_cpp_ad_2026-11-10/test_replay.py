"""Regression checks for D1-entry coeres slope inputs and their AD chain."""

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
spec = importlib.util.spec_from_file_location("native_d1_coeres_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 coeres replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def endpoint(data: dict, direction: str = "joint17_relative", h: str = "0.0001",
             side: str = "high") -> dict:
    return data["directions"][direction]["finite_differences"][h][side + "_stages"]


def shifted_ulps(value: float, count: int, toward: float = math.inf) -> float:
    for _ in range(count):
        value = math.nextafter(value, toward)
    return value


class ReplayTests(unittest.TestCase):
    def assert_saved_contract(self, actual: dict, saved: dict) -> None:
        stable_keys = (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "parent_entry_slope_stage_fields", "new_entry_pid_stage_fields",
            "new_entry_precg2_stage_fields", "new_entry_coeres_stage_fields",
            "new_melt_producer_stage_fields",
            "numeric_stage_tangents_per_direction", "melt_source_order_cases",
            "melt_source_order_fields_per_case", "native_melt_producer_words_raw_equal",
            "melt_minimum_branch_margins", "melt_amount_parent_value_handoff_cases",
            "melt_amount_parent_jvp_handoff_directions", "melt_fd_resolved_signal_count",
            "directional_applied_terms", "source_pins", "native_capture_receipts",
            "fd_branch_classifications", "entry_fd_resolved_signal_count",
            "entry_fd_rounding_floor_cases", "entry_one_sided_rounding_floor_cases",
            "pid_fd_resolved_signal_count", "pid_fd_rounding_floor_cases",
            "pid_one_sided_rounding_floor_cases", "native_d1_precg2_anchor_words_raw_equal",
            "precg2_native_anchor_scope", "precg2_floor_margins",
            "precg2_source_order_cases", "precg2_source_expressions",
            "precg2_interpolation_source_order_cases",
            "precg2_parent_value_handoff_cases", "precg2_parent_jvp_handoff_directions",
            "precg2_fd_resolved_signal_count", "precg2_fd_rounding_floor_cases",
            "precg2_one_sided_rounding_floor_cases", "scientific_status", "physical_unit_status",
            "native_d1_coeres_anchor_words_raw_equal", "coeres_native_anchor_scope",
            "coeres_source_order_cases", "coeres_slope_parameter_words",
            "coeres_source_expressions", "coeres_minimum_branch_margins",
            "coeres_input_handoff_cases", "coeres_input_tangent_handoff_directions",
            "coeres_term2_tangent_chain_directions", "coeres_fd_resolved_signal_count",
            "coeres_new_slope_fd_signal_count", "coeres_parent_fd_recheck_count",
        )
        for key in stable_keys:
            self.assertEqual(actual[key], saved[key], key)

        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        cases = {"baseline": cpp["baseline"]["stage_scalars"]}
        for direction in module.DIRECTIONS:
            for h, pair in cpp["directions"][direction]["finite_differences"].items():
                for side in ("low", "high"):
                    cases[f"{direction}/{h}/{side}"] = pair[side + "_stages"]
        self.assertEqual(len(cases), 25)

        # libm gamma/pow can differ slightly across platforms. Validate every
        # captured value against the declared ULP bound, then compare stable
        # branch and margin data exactly.
        entry_portable = {"expected_rslope_g", "rslope_g_ulp_distance"}
        for result in (actual, saved):
            rows = result["entry_slope_branch_checks"]
            self.assertEqual(len(rows), 25)
            self.assertEqual({row["case"] for row in rows}, set(cases))
            distances = []
            for row in rows:
                self.assertIs(type(row["rslope_g_ulp_distance"]), int)
                self.assertLessEqual(row["rslope_g_ulp_distance"], 8)
                captured = cases[row["case"]][module.ENTRY_STAGE + ".rslope_g"]
                self.assertEqual(row["rslope_g_ulp_distance"],
                                 module.ulp_distance(row["expected_rslope_g"], captured))
                distances.append(row["rslope_g_ulp_distance"])
            self.assertEqual(result["maximum_entry_slope_formula_ulp_distance"], max(distances))
        self.assertEqual(
            [{k: v for k, v in row.items() if k not in entry_portable}
             for row in actual["entry_slope_branch_checks"]],
            [{k: v for k, v in row.items() if k not in entry_portable}
             for row in saved["entry_slope_branch_checks"]],
        )

        precg_portable = {
            "expected_g5pbgo2", "g5pbgo2_ulp_distance",
            "expected_precg2", "precg2_ulp_distance",
        }
        actual_rows = actual["precg2_source_order_checks"]
        saved_rows = saved["precg2_source_order_checks"]
        for result, rows in ((actual, actual_rows), (saved, saved_rows)):
            self.assertEqual(len(rows), 25)
            self.assertEqual({row["case"] for row in rows}, set(cases))
            g5_distances = []
            precg_distances = []
            for row in rows:
                values = cases[row["case"]]
                g5 = values[module.PRECG2_STAGE + ".g5pbgo2"]
                precg2 = values[module.PRECG2_STAGE + ".precg2"]
                self.assertTrue(math.isfinite(row["expected_g5pbgo2"]) and row["expected_g5pbgo2"] > 0)
                self.assertTrue(math.isfinite(row["expected_precg2"]) and row["expected_precg2"] > 0)
                self.assertLessEqual(module.ulp_distance(row["expected_g5pbgo2"], g5), 16)
                self.assertLessEqual(module.ulp_distance(row["expected_precg2"], precg2), 8)
                self.assertIs(type(row["g5pbgo2_ulp_distance"]), int)
                self.assertIs(type(row["precg2_ulp_distance"]), int)
                self.assertEqual(row["g5pbgo2_ulp_distance"],
                                 module.ulp_distance(row["expected_g5pbgo2"], g5))
                self.assertEqual(row["precg2_ulp_distance"],
                                 module.ulp_distance(row["expected_precg2"], precg2))
                g5_distances.append(row["g5pbgo2_ulp_distance"])
                precg_distances.append(row["precg2_ulp_distance"])
            self.assertEqual(result["precg2_source_order_g5_max_ulp_distance"], max(g5_distances))
            self.assertEqual(result["precg2_source_order_value_max_ulp_distance"], max(precg_distances))
        self.assertEqual(
            [{k: v for k, v in row.items() if k not in precg_portable} for row in actual_rows],
            [{k: v for k, v in row.items() if k not in precg_portable} for row in saved_rows],
        )
        self.assertLessEqual(actual["max_precg2_fd_relative_error"], 0.01)

        coeres_portable = {
            "expected_rslopeb_g", "rslopeb_g_ulp_distance",
            "expected_coeres_g", "coeres_g_ulp_distance",
        }
        actual_rows = actual["coeres_slope_source_order_checks"]
        saved_rows = saved["coeres_slope_source_order_checks"]
        for result, rows in ((actual, actual_rows), (saved, saved_rows)):
            self.assertEqual(len(rows), 25)
            self.assertEqual({row["case"] for row in rows}, set(cases))
            rb_distances = []
            coeres_distances = []
            for row in rows:
                values = cases[row["case"]]
                rb = values[module.COERES_STAGE + ".rslopeb_g"]
                coeres = values[module.MELT_STAGE + ".coeres_g"]
                self.assertTrue(math.isfinite(row["expected_rslopeb_g"]) and row["expected_rslopeb_g"] > 0)
                self.assertTrue(math.isfinite(row["expected_coeres_g"]) and row["expected_coeres_g"] > 0)
                rb_distance = module.ulp_distance(row["expected_rslopeb_g"], rb)
                coeres_distance = module.ulp_distance(row["expected_coeres_g"], coeres)
                self.assertLessEqual(rb_distance, module.COERES_RB_ULP_LIMIT)
                self.assertLessEqual(coeres_distance, module.COERES_VALUE_ULP_LIMIT)
                self.assertIs(type(row["rslopeb_g_ulp_distance"]), int)
                self.assertIs(type(row["coeres_g_ulp_distance"]), int)
                self.assertEqual(row["rslopeb_g_ulp_distance"], rb_distance)
                self.assertEqual(row["coeres_g_ulp_distance"], coeres_distance)
                self.assertGreater(row["qg_branch_margin"], 0.0)
                self.assertGreater(row["sqrt_argument_margin"], 0.0)
                self.assertFalse(row["graupel_mask"])
                self.assertEqual(row["rslopemu_g"], 1.0)
                rb_distances.append(rb_distance)
                coeres_distances.append(coeres_distance)
            self.assertEqual(result["coeres_rslopeb_g_max_ulp_distance"], max(rb_distances))
            self.assertEqual(result["coeres_value_max_ulp_distance"], max(coeres_distances))
        self.assertEqual(
            [{k: v for k, v in row.items() if k not in coeres_portable} for row in actual_rows],
            [{k: v for k, v in row.items() if k not in coeres_portable} for row in saved_rows],
        )

    def test_replay_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["new_entry_coeres_stage_fields"], 10)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 322)
        self.assertEqual(actual["native_d1_coeres_anchor_words_raw_equal"], 24)
        self.assertEqual(actual["coeres_fd_resolved_signal_count"], 30)
        self.assertEqual(actual["coeres_new_slope_fd_signal_count"], 20)
        self.assertEqual(actual["coeres_parent_fd_recheck_count"], 10)
        self.assertLess(actual["max_coeres_slope_fd_relative_error"], 1e-6)
        self.assertLess(actual["max_parent_coeres_fd_recheck_relative_error"], 1e-6)
        self.assertTrue(all(margin > 0 for margin in actual["coeres_minimum_branch_margins"].values()))
        self.assertEqual(actual["new_entry_precg2_stage_fields"], 8)
        self.assertEqual(actual["native_d1_precg2_anchor_words_raw_equal"], 9)
        self.assertEqual(actual["precg2_fd_resolved_signal_count"], 50)
        self.assertEqual(actual["precg2_fd_rounding_floor_cases"], 14)
        self.assertEqual(actual["precg2_one_sided_rounding_floor_cases"], 13)
        self.assertLessEqual(actual["max_precg2_fd_relative_error"], 0.003)
        self.assertTrue(all(margin > 0 for margin in actual["precg2_floor_margins"].values()))

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 coeres upstream producer AD", proc.stdout)

    def test_saved_entry_slope_max_must_match_rows(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        saved["maximum_entry_slope_formula_ulp_distance"] = 999999
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(saved, saved)

    def test_native_anchor_is_enforced(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"][module.COERES_STAGE + ".rslope2_g"] += 1e-13
        with self.assertRaisesRegex(ValueError, "native D1 coeres input word"):
            module.replay(output_override=altered(change))

    def test_unanchored_rslope2_square_mutation_is_rejected(self) -> None:
        def change(data):
            stages = endpoint(data, direction="qg17_relative", h="0.0001", side="high")
            stages[module.COERES_STAGE + ".rslope2_g"] *= 1.0001
        with self.assertRaisesRegex(ValueError, "source-order rslope2_g square"):
            module.replay(output_override=altered(change))

    def test_rslopeb_one_ulp_raw_consumer_handoff_is_rejected(self) -> None:
        def change(data):
            stages = endpoint(data, direction="joint17_relative", h="0.0001", side="high")
            key = module.COERES_STAGE + ".rslopeb_g"
            captured = stages[key]
            expected = module.source_order_rslopeb_g(
                stages[module.COERES_STAGE + ".rslope_g"],
                stages[module.COERES_STAGE + ".bvtg"],
            )
            stages[key] = math.nextafter(captured, expected if expected != captured else math.inf)
            self.assertEqual(module.ulp_distance(captured, stages[key]), 1)
            self.assertLessEqual(module.ulp_distance(stages[key], expected),
                                 module.COERES_RB_ULP_LIMIT)
        with self.assertRaisesRegex(ValueError, "coeres input producer-to-melt handoff: rslopeb_g"):
            module.replay(output_override=altered(change))

    def test_rslopeb_formula_rejects_seventeen_ulp_offset(self) -> None:
        def change(data, distance: int, toward: float):
            stages = endpoint(data, direction="qg17_relative", h="0.0001", side="high")
            key = module.COERES_STAGE + ".rslopeb_g"
            expected = module.source_order_rslopeb_g(
                stages[module.COERES_STAGE + ".rslope_g"],
                stages[module.COERES_STAGE + ".bvtg"],
            )
            stages[key] = shifted_ulps(expected, distance, toward)

        for toward in (math.inf, -math.inf):
            with self.subTest(toward=toward):
                def outside_bound(data):
                    change(data, 17, toward)
                with self.assertRaisesRegex(ValueError,
                                            "rslopeb_g pow within portable ULP bound"):
                    module.replay(output_override=altered(outside_bound))

    def test_rslopeb_pow_portable_boundary_candidates(self) -> None:
        original = module.source_order_rslopeb_g
        baseline = json.loads((HERE / "raw/cpp_result.json").read_text())["baseline"]["stage_scalars"]
        baseline_rslope = baseline[module.COERES_STAGE + ".rslope_g"]
        baseline_bvtg = baseline[module.COERES_STAGE + ".bvtg"]
        captured = baseline[module.COERES_STAGE + ".rslopeb_g"]

        for distance, toward in ((1, math.inf), (16, -math.inf)):
            with self.subTest(distance=distance, toward=toward):
                def portable_pow(rslope: float, bvtg: float) -> float:
                    if rslope == baseline_rslope and bvtg == baseline_bvtg:
                        return shifted_ulps(captured, distance, toward)
                    return original(rslope, bvtg)

                with mock.patch.object(module, "source_order_rslopeb_g", side_effect=portable_pow):
                    result = module.replay()
                row = next(row for row in result["coeres_slope_source_order_checks"]
                           if row["case"] == "baseline")
                self.assertEqual(row["rslopeb_g_ulp_distance"], distance)
                self.assert_saved_contract(result, json.loads((HERE / "results.json").read_text()))

        data = json.loads((HERE / "raw/cpp_result.json").read_text())
        stages = endpoint(data, direction="joint17_relative", h="0.0001", side="high")
        rb_key = module.COERES_STAGE + ".rslopeb_g"
        captured = stages[rb_key]
        stages[rb_key] = math.nextafter(captured, -math.inf)
        raw = (json.dumps(data, sort_keys=True) + "\n").encode()
        target_rslope = stages[module.COERES_STAGE + ".rslope_g"]
        target_bvtg = stages[module.COERES_STAGE + ".bvtg"]
        original_pow = module.source_order_rslopeb_g

        def minus_sixteen_ulp(rslope: float, bvtg: float) -> float:
            if rslope == target_rslope and bvtg == target_bvtg:
                return shifted_ulps(captured, 16, -math.inf)
            return original_pow(rslope, bvtg)

        with mock.patch.object(module, "source_order_rslopeb_g", side_effect=minus_sixteen_ulp):
            with self.assertRaisesRegex(ValueError, "coeres input producer-to-melt handoff: rslopeb_g"):
                module.replay(output_override=(raw, hashlib.sha256(raw).hexdigest()))

    def test_coeres_sqrt_portable_four_ulp_boundary(self) -> None:
        original = module.source_order_coeres_g
        baseline = json.loads((HERE / "raw/cpp_result.json").read_text())["baseline"]["stage_scalars"]
        captured = baseline[module.MELT_STAGE + ".coeres_g"]
        slope_values = tuple(baseline[module.COERES_STAGE + "." + field]
                             for field in ("rslope2_g", "rslope_g", "rslopeb_g",
                                           "rslopemu_g", "qcrmin"))

        for distance in (4, 5):
            with self.subTest(coeres_ulp_distance=distance):
                def candidate(r2: float, rslope: float, rb: float, rmu: float, qcrmin: float) -> float:
                    if (r2, rslope, rb, rmu, qcrmin) == slope_values:
                        return shifted_ulps(captured, distance)
                    return original(r2, rslope, rb, rmu, qcrmin)

                with mock.patch.object(module, "source_order_coeres_g", side_effect=candidate):
                    if distance == 4:
                        result = module.replay()
                        row = next(row for row in result["coeres_slope_source_order_checks"]
                                   if row["case"] == "baseline")
                        self.assertEqual(row["coeres_g_ulp_distance"], 4)
                        self.assert_saved_contract(
                            result, json.loads((HERE / "results.json").read_text()))
                    else:
                        with self.assertRaisesRegex(
                                ValueError, "source-order coeres_g within portable ULP bound"):
                            module.replay()

    def test_mask_change_and_masked_branch_claim_are_rejected(self) -> None:
        def change(data):
            stages = endpoint(data, direction="qg17_relative", h="0.0001", side="high")
            stages[module.COERES_STAGE + ".graupel_mask"] = 1
        with self.assertRaisesRegex(ValueError, "qg<=qcrmin slope branch"):
            module.replay(output_override=altered(change))

    def test_matched_coeres_tangent_cancellation_still_fails_slope_jvp(self) -> None:
        data = json.loads((HERE / "raw/cpp_result.json").read_text())
        values = data["baseline"]["stage_scalars"]
        order = data["stage_numeric_order"]
        direction = data["directions"]["qg17_relative"]
        tangent = dict(zip(order, direction["stage_jvp"]))
        original_tangent = dict(tangent)
        r2 = values[module.COERES_STAGE + ".rslope2_g"]
        rb = values[module.COERES_STAGE + ".rslopeb_g"]
        delta_r2 = r2 * 1e-4
        delta_rb = -2.0 * rb / r2 * delta_r2
        tangent[module.COERES_STAGE + ".rslope2_g"] += delta_r2
        tangent[module.COERES_STAGE + ".rslopeb_g"] += delta_rb
        coeres = values[module.MELT_STAGE + ".coeres_g"]
        unchanged_total = coeres * (
            tangent[module.COERES_STAGE + ".rslope2_g"] / r2
            + 0.5 * tangent[module.COERES_STAGE + ".rslope_g"]
            / values[module.COERES_STAGE + ".rslope_g"]
            + 0.5 * tangent[module.COERES_STAGE + ".rslopeb_g"] / rb
        )
        expected_total = module.coeres_jvp_terms(values, original_tangent)[-1]
        self.assertAlmostEqual(unchanged_total, expected_total, delta=1e-15 * abs(expected_total))
        with self.assertRaisesRegex(ValueError, "synthetic cancellation square JVP"):
            module.check_coeres_jvp_chain(values, tangent, "synthetic cancellation")

    def test_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
