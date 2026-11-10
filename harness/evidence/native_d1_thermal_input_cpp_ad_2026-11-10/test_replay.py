"""Regression checks for D1-entry coeres slope inputs and their AD chain."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_d1_thermal_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 thermal replay loader")
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
            "thermal_direction_names", "thermal_native_vjp_selected_k_index0",
            "thermal_native_vjp_state_order", "thermal_native_d1_output_vjp_rows",
            "thermal_native_d1_output_vjp_gradient_words", "thermal_input_baseline",
            "thermal_branch_summaries", "thermal_activation_crossings",
            "thermal_native_anchor_summary", "thermal_native_anchor_helper_sha256",
            "thermal_runtime_source_sha256",
            "thermal_final_fd_helper_sha256", "thermal_joint_stage_jvp_max_abs_residual",
            "thermal_joint_stage_jvp_max_relative_residual",
            "thermal_joint_stage_jvp_max_residual_field", "thermal_smooth_fd_steps",
            "thermal_d1_fd_pairs", "thermal_final_fd_pairs", "thermal_fd_central_check_count",
            "thermal_fd_one_sided_check_count", "thermal_structural_zero_qv_checks",
            "thermal_final_nc_accepted_pairs", "thermal_final_nc_crossing_pairs",
            "thermal_final_activation_crossing_endpoints", "thermal_final_nccn_floor_endpoint_checks",
        )
        for key in stable_keys:
            self.assertEqual(actual[key], saved[key], key)

        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        base_values = cpp["baseline"]["stage_scalars"]
        work2_summaries = []
        for result in (actual, saved):
            work2 = result["thermal_baseline_source_values"]
            self.assertEqual(work2["temperature"], result["thermal_input_baseline"]["physical_t16"])
            self.assertEqual(work2["expected_cpm"], base_values[module.MELT_STAGE + ".cpm"])
            self.assertTrue(math.isfinite(work2["expected_work2"]) and work2["expected_work2"] > 0.0)
            expected_work2_ulp = module.ulp_distance(
                work2["expected_work2"], base_values[module.MELT_STAGE + ".work2"])
            self.assertIs(type(work2["work2_ulp_distance"]), int)
            self.assertEqual(work2["work2_ulp_distance"], expected_work2_ulp)
            self.assertLessEqual(expected_work2_ulp, 16)
            work2_summaries.append(work2)
            self.assertEqual(len(result["thermal_branch_summaries"]), 15)
            self.assertEqual(result["thermal_final_nc_accepted_pairs"], 4)
            self.assertEqual(result["thermal_final_nc_crossing_pairs"], 3)
            self.assertEqual(result["thermal_final_nccn_floor_endpoint_checks"], 14)
            self.assertLessEqual(result["max_thermal_final_nc_central_relative_error"], 1e-6)
            self.assertLessEqual(result["max_thermal_fd_relative_error"], 5e-6)
        self.assertEqual(work2_summaries[0]["temperature"], work2_summaries[1]["temperature"])
        self.assertEqual(work2_summaries[0]["expected_cpm"], work2_summaries[1]["expected_cpm"])

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
        for result in (actual, saved):
            base_values = cpp["baseline"]["stage_scalars"]
            work2_expected = result["thermal_baseline_source_values"]["expected_work2"]
            work2_value = base_values[module.MELT_STAGE + ".work2"]
            self.assertTrue(math.isfinite(work2_expected) and work2_expected > 0)
            self.assertLessEqual(module.ulp_distance(work2_expected, work2_value), 16)
            self.assertLessEqual(result["thermal_baseline_source_values"]["work2_ulp_distance"], 16)
            self.assertEqual(result["thermal_native_anchor_summary"]["native_overlap_cases"], 10)
            self.assertEqual(result["thermal_native_anchor_summary"]["native_overlap_d1_words_raw_equal"], 620)
            self.assertEqual(result["thermal_native_anchor_summary"]["native_overlap_final_state_words_raw_equal"], 4680)
            self.assertEqual(result["thermal_d1_fd_pairs"], 7)
            self.assertEqual(result["thermal_final_fd_pairs"], 4)
            self.assertEqual(result["thermal_final_activation_crossing_endpoints"], [
                "qv16_rel/0.001/low",
                "th16_abs/0.01/high",
                "th16_abs_qv16_rel_joint/0.001/low",
            ])
            self.assertLessEqual(result["max_thermal_final_nc_central_relative_error"], 1e-6)

    def test_replay_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["schema"], "kdm6.native_d1_thermal_input_cpp_ad_replay.v1")
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 322)
        self.assertEqual(actual["thermal_direction_names"], list(module.THERMAL_DIRECTION_NAMES))
        self.assertEqual(actual["thermal_native_d1_output_vjp_rows"], 4)
        self.assertEqual(actual["thermal_d1_fd_pairs"], 7)
        self.assertEqual(actual["thermal_final_fd_pairs"], 4)
        self.assertEqual(actual["thermal_fd_central_check_count"], 36)
        self.assertEqual(actual["thermal_fd_one_sided_check_count"], 72)
        self.assertEqual(actual["thermal_final_nc_crossing_pairs"], 3)
        self.assertLessEqual(actual["max_thermal_fd_relative_error"], 5e-6)
        self.assertLessEqual(actual["max_thermal_final_nc_central_relative_error"], 1e-6)
        self.assertEqual(actual["thermal_final_activation_crossing_endpoints"], [
            "qv16_rel/0.001/low",
            "th16_abs/0.01/high",
            "th16_abs_qv16_rel_joint/0.001/low",
        ])
        self.assertEqual(actual["thermal_native_anchor_summary"]["native_overlap_d1_words_raw_equal"], 620)
        self.assertEqual(actual["thermal_native_anchor_summary"]["native_overlap_final_state_words_raw_equal"], 4680)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native TH16/QV16 full-call D1 thermal AD", proc.stdout)

    def test_saved_entry_slope_max_must_match_rows(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        saved["maximum_entry_slope_formula_ulp_distance"] = 999999
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(saved, saved)

    def test_saved_work2_ulp_must_match_captured_value(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        distance = saved["thermal_baseline_source_values"]["work2_ulp_distance"]
        saved["thermal_baseline_source_values"]["work2_ulp_distance"] = (
            distance + 1 if distance < 16 else distance - 1)
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(saved, saved)

    def test_initial_thermal_coordinates_are_native_anchored(self) -> None:
        def change(data):
            data["thermal_directions"]["input"]["qv16"] = math.nextafter(
                data["thermal_directions"]["input"]["qv16"], math.inf)
        with self.assertRaisesRegex(ValueError, "thermal baseline QV16 parent anchor"):
            module.replay(output_override=altered(change))

    def test_thermal_d1_branch_summary_is_verified(self) -> None:
        def change(data):
            pair = data["thermal_directions"]["directions"]["th16_abs"]["finite_differences"]["0.001"]
            pair["high_branch"]["d1_branch"]["warm"] = False
        with self.assertRaisesRegex(ValueError, "D1 branch summary matches stage: warm"):
            module.replay(output_override=altered(change))

    def test_thermal_vjp_rows_are_raw_word_bound(self) -> None:
        def change(data):
            data["thermal_vjp"]["rows"][module.THERMAL_STAGE_VJP_FIELDS[0]]["values"][0] += 1.0
        with self.assertRaisesRegex(ValueError, "thermal VJP gradient raw words"):
            module.replay(output_override=altered(change))

    def test_cpm_work2_and_t1_source_tangent_roles(self) -> None:
        raw = json.loads((HERE / "raw/cpp_result.json").read_text())
        base = raw["baseline"]["stage_scalars"]
        thermal = raw["thermal_directions"]
        qv = thermal["directions"]["qv16_rel"]["jvp"]["stage_jvp"]
        th = thermal["directions"]["th16_abs"]["jvp"]["stage_jvp"]
        order = raw["stage_numeric_order"]
        qv_map = dict(zip(order, qv))
        th_map = dict(zip(order, th))
        source_qv = module.thermal_d1_jvp_sources(
            base, 0.0, base["c3_pre_mf_d1.qv_before"], thermal["input"]["pii16"], "test QV")
        source_th = module.thermal_d1_jvp_sources(
            base, 1.0, 0.0, thermal["input"]["pii16"], "test TH")
        self.assertEqual(qv_map["d1_melt_producer.work2"], 0.0)
        self.assertEqual(source_qv["d_work2"], 0.0)
        self.assertEqual(source_qv["d_psmlt"], 0.0)
        self.assertEqual(th_map["d1_melt_producer.cpm"], 0.0)
        self.assertAlmostEqual(th_map["d1_melt_producer.t1"], source_th["d_t1"], places=12)
        self.assertAlmostEqual(qv_map["d1_melt_producer.t1"], source_qv["d_t1"], places=12)

    def test_final_nc_fd_rejects_rehashed_endpoint_word(self) -> None:
        data = json.loads((HERE / "raw/cpp_result.json").read_text())
        pair = data["thermal_directions"]["directions"]["th16_abs_qv16_rel_joint"]["finite_differences"]["0.0001"]
        nc_index = 8 * 39 + 15
        value = struct.unpack(">d", int(pair["high_final_raw"][nc_index], 16).to_bytes(8, "big"))[0]
        pair["high_final_raw"][nc_index] = module.word(value + 1.0)
        helper_path = HERE / "final_fd.py"
        spec = importlib.util.spec_from_file_location("thermal_final_fd_mutation", helper_path)
        self.assertIsNotNone(spec)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with self.assertRaisesRegex(ValueError, "final NC16 central derivative"):
            helper.check_final_thermal_differences(data)

    def test_native_anchor_rejects_rehashed_final_state(self) -> None:
        data = json.loads((HERE / "raw/cpp_result.json").read_text())
        pair = data["thermal_directions"]["directions"]["th16_abs"]["finite_differences"]["0.001"]
        nc_index = 8 * 39 + 15
        value = struct.unpack(">d", int(pair["high_final_raw"][nc_index], 16).to_bytes(8, "big"))[0]
        pair["high_final_raw"][nc_index] = module.word(value + 1.0)
        helper_path = HERE / "native_anchors.py"
        spec = importlib.util.spec_from_file_location("thermal_native_anchors_mutation", helper_path)
        self.assertIsNotNone(spec)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        with self.assertRaisesRegex(ValueError, "complete output raw words"):
            helper.check_native_thermal_anchors(data, module.EVIDENCE,
                                                module.THERMAL_NATIVE_MANIFEST_SHA)

    def test_missing_parent_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
