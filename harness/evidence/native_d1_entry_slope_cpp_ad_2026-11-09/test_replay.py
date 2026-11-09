"""Regression checks for the D1-entry graupel slope capture and tangent."""

from __future__ import annotations

import copy
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
spec = importlib.util.spec_from_file_location("native_d1_entry_slope_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 entry slope replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def baseline(data: dict, field: str) -> float:
    return data["baseline"]["stage_scalars"][field]


class ReplayTests(unittest.TestCase):
    def assert_saved_contract(self, actual: dict, saved: dict) -> None:
        for key in (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "new_entry_slope_stage_fields", "native_d1_entry_anchor_words_raw_equal",
            "native_capture_receipts", "pidn0g_native_anchor", "source_pins",
            "numeric_stage_tangents_per_direction", "fd_branch_classifications",
            "entry_fd_resolved_signal_count", "entry_fd_rounding_floor_cases",
            "entry_one_sided_rounding_floor_cases", "directional_applied_terms",
            "minimum_accepted_rhox_upper_margin",
            "scientific_status", "physical_unit_status",
        ):
            self.assertEqual(actual[key], saved[key])

        # Independent Python libm can move these two diagnostics within the
        # declared 8-ULP envelope. All other case fields remain exact.
        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        cases = {"baseline": cpp["baseline"]["stage_scalars"]}
        for direction in module.DIRECTIONS:
            for h, pair in cpp["directions"][direction]["finite_differences"].items():
                for side in ("low", "high"):
                    cases[f"{direction}/{h}/{side}"] = pair[f"{side}_stages"]
        self.assertEqual(len(cases), 25)
        actual_rows = actual["entry_slope_branch_checks"]
        saved_rows = saved["entry_slope_branch_checks"]
        portable = {"expected_rslope_g", "rslope_g_ulp_distance"}
        for summary, rows in ((actual, actual_rows), (saved, saved_rows)):
            self.assertEqual(len(rows), len(cases))
            self.assertEqual({row["case"] for row in rows}, set(cases))
            distances = []
            for row in rows:
                expected = row["expected_rslope_g"]
                distance = row["rslope_g_ulp_distance"]
                self.assertIs(type(distance), int)
                self.assertIsInstance(expected, (int, float))
                self.assertTrue(math.isfinite(expected) and expected > 0)
                captured = cases[row["case"]]["d1_entry_slope_inputs.rslope_g"]
                self.assertEqual(distance, module.ulp_distance(expected, captured))
                self.assertLessEqual(distance, 8)
                distances.append(distance)
            self.assertEqual(summary["maximum_entry_slope_formula_ulp_distance"], max(distances))
        self.assertEqual(
            [{key: value for key, value in row.items() if key not in portable}
             for row in actual_rows],
            [{key: value for key, value in row.items() if key not in portable}
             for row in saved_rows],
        )

    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["parent_stage_fields"], 26)
        self.assertEqual(actual["parent_gfac_stage_fields"], 7)
        self.assertEqual(actual["new_entry_slope_stage_fields"], 7)
        self.assertEqual(actual["native_d1_entry_anchor_words_raw_equal"], 18)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 240)
        self.assertLessEqual(actual["maximum_entry_slope_formula_ulp_distance"], 8)
        self.assertEqual(actual["entry_fd_resolved_signal_count"], 60)
        self.assertEqual(actual["entry_fd_rounding_floor_cases"], 2)
        self.assertEqual(actual["entry_one_sided_rounding_floor_cases"], 4)
        self.assertAlmostEqual(actual["minimum_accepted_rhox_upper_margin"], 0.0126033337, places=9)
        self.assertEqual(actual["pidn0g_native_anchor"], "not independently captured by #553")
        crossings = [row for row in actual["fd_branch_classifications"]
                     if row["classification"] == "captured_density_cap_crossing"]
        self.assertEqual({(row["direction"], row["h"]) for row in crossings},
                         {("qg17_relative", "0.001"), ("brs17_relative", "0.001")})
        small = [row for row in actual["fd_branch_classifications"]
                 if row["h"] == "1e-06"]
        self.assertTrue(all(row["classification"] == "small_step_no_independent_cap_capture"
                            for row in small))

    def test_permitted_libm_ulp_diagnostic_is_portable(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        baseline_stages = cpp["baseline"]["stage_scalars"]
        prefix = "d1_entry_slope_inputs."
        baseline_inputs = tuple(baseline_stages[prefix + field]
                                for field in ("qg", "dend", "pidn0g"))
        captured = baseline_stages[prefix + "rslope_g"]
        source_order = module.source_order_rslope

        def one_ulp_result(qg: float, dend: float, pidn0g: float):
            expected, denominator, ratio = source_order(qg, dend, pidn0g)
            if (qg, dend, pidn0g) == baseline_inputs:
                expected = math.nextafter(captured, math.inf)
            return expected, denominator, ratio

        with mock.patch.object(module, "source_order_rslope", side_effect=one_ulp_result):
            actual = module.replay()
        self.assertEqual(actual["entry_slope_branch_checks"][0]["rslope_g_ulp_distance"], 1)
        self.assertNotEqual(actual["entry_slope_branch_checks"][0]["expected_rslope_g"],
                            saved["entry_slope_branch_checks"][0]["expected_rslope_g"])
        self.assert_saved_contract(actual, saved)

        wrong_distance = copy.deepcopy(saved)
        wrong_distance["entry_slope_branch_checks"][0]["rslope_g_ulp_distance"] = 2
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(actual, wrong_distance)
        wrong_branch = copy.deepcopy(saved)
        wrong_branch["entry_slope_branch_checks"][0]["rhox_branch"] = "upper_cap"
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(actual, wrong_branch)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 entry-slope AD", proc.stdout)

    def test_source_order_slope_and_active_unclamped_branch(self) -> None:
        qg, dend, pidn0g = 5.4e-5, 0.735, 1.13e10
        expected, denominator, ratio = module.source_order_rslope(qg, dend, pidn0g)
        values = {
            "d1_entry_slope_inputs.qg": qg,
            "d1_entry_slope_inputs.brs_input": qg / module.RHO_MAX,
            "d1_entry_slope_inputs.dend": dend,
            "d1_entry_slope_inputs.pidn0g": pidn0g,
            "d1_entry_slope_inputs.rhox": module.RHO_MAX,
            "d1_entry_slope_inputs.bg": qg / module.RHO_MAX,
            "d1_entry_slope_inputs.rslope_g": expected,
            "d1_gfac_inputs.qg": qg,
            "d1_gfac_inputs.rslope_g": expected,
            "d1_gfac_inputs.qcrmin": module.QCRMIN,
        }
        diag = module.entry_slope_values(values, "fixture")
        self.assertEqual(diag["rslope_g_ulp_distance"], 0)
        self.assertEqual(diag["rhox_branch"], "upper_boundary")
        self.assertGreater(denominator, module.DOMAIN_FLOOR)
        self.assertGreater(ratio, module.DOMAIN_FLOOR)

        bad_slope = dict(values)
        candidate = expected
        for _ in range(9):
            candidate = math.nextafter(candidate, math.inf)
        bad_slope["d1_entry_slope_inputs.rslope_g"] = candidate
        with self.assertRaisesRegex(ValueError, "within 8 ULP"):
            module.entry_slope_values(bad_slope, "fixture")

        inactive = dict(values)
        inactive["d1_entry_slope_inputs.qg"] = module.QCRMIN
        with self.assertRaisesRegex(ValueError, "active graupel slope mask"):
            module.entry_slope_values(inactive, "fixture")

        denominator_clamped = dict(values)
        denominator_clamped["d1_entry_slope_inputs.dend"] = 1.0e-40
        with self.assertRaisesRegex(ValueError, "unclamped denominator and ratio"):
            module.entry_slope_values(denominator_clamped, "fixture")

        ratio_clamped = dict(values)
        ratio_clamped["d1_entry_slope_inputs.pidn0g"] = 1.0e-40
        with self.assertRaisesRegex(ValueError, "unclamped denominator and ratio"):
            module.entry_slope_values(ratio_clamped, "fixture")

        wrong_prog_b = dict(values)
        wrong_prog_b["d1_entry_slope_inputs.rhox"] -= 1.0e-6
        wrong_prog_b["d1_entry_slope_inputs.bg"] = qg / wrong_prog_b["d1_entry_slope_inputs.rhox"]
        with self.assertRaisesRegex(ValueError, "entry ProgB density source order"):
            module.entry_slope_values(wrong_prog_b, "fixture")

    def test_three_input_entry_slope_jvp(self) -> None:
        values = {
            "d1_entry_slope_inputs.qg": 2.0,
            "d1_entry_slope_inputs.dend": 4.0,
            "d1_entry_slope_inputs.pidn0g": 8.0,
            "d1_entry_slope_inputs.rslope_g": 0.5,
        }
        tangent = {
            "d1_entry_slope_inputs.qg": 0.1,
            "d1_entry_slope_inputs.dend": 0.2,
            "d1_entry_slope_inputs.pidn0g": 0.4,
        }
        terms = module.entry_slope_jvp_terms(values, tangent)
        for actual, expected in zip(terms, (0.00625, 0.00625, -0.00625)):
            self.assertAlmostEqual(actual, expected, places=15)

    def test_rehashed_entry_slope_endpoint_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["1e-05"]
            pair["high_stages"]["d1_entry_slope_inputs.rslope_g"] += 1.0e-5
        with self.assertRaisesRegex(ValueError, "within 8 ULP"):
            module.replay(output_override=altered(change))

    def test_rehashed_qg_endpoint_cannot_break_consumer_handoff(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["1e-05"]
            stages = pair["high_stages"]
            old_qg = stages["d1_entry_slope_inputs.qg"]
            new_qg = old_qg * (1.0 + 1.0e-5)
            stages["d1_entry_slope_inputs.qg"] = new_qg
            stages["d1_entry_slope_inputs.pidn0g"] *= new_qg / old_qg
            bg_denominator = max(stages["d1_entry_slope_inputs.brs_input"], module.BRS_MIN)
            rhox_raw = new_qg / bg_denominator
            stages["d1_entry_slope_inputs.rhox"] = min(
                module.RHO_MAX, max(module.RHO_MIN, rhox_raw))
            stages["d1_entry_slope_inputs.bg"] = new_qg / stages["d1_entry_slope_inputs.rhox"]
            expected, _, _ = module.source_order_rslope(
                new_qg, stages["d1_entry_slope_inputs.dend"], stages["d1_entry_slope_inputs.pidn0g"])
            stages["d1_entry_slope_inputs.rslope_g"] = expected
        with self.assertRaisesRegex(ValueError, "D1 consumer qg value handoff"):
            module.replay(output_override=altered(change))

    def test_compensated_qg_pidn0g_tangent_cannot_break_parent_handoff(self) -> None:
        def change(data):
            order = data["stage_numeric_order"]
            qg_i = order.index("d1_entry_slope_inputs.qg")
            pid_i = order.index("d1_entry_slope_inputs.pidn0g")
            qg = baseline(data, "d1_entry_slope_inputs.qg")
            pidn0g = baseline(data, "d1_entry_slope_inputs.pidn0g")
            delta_qg = 1.0e-12
            delta_pidn0g = pidn0g / qg * delta_qg
            for name in ("qg17_relative", "joint17_relative"):
                tangent = data["directions"][name]["stage_jvp"]
                tangent[qg_i] += delta_qg
                tangent[pid_i] += delta_pidn0g
        with self.assertRaisesRegex(ValueError, "D1 entry QG tangent handoff"):
            module.replay(output_override=altered(change))

    def test_rehashed_native_entry_anchor_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["d1_entry_slope_inputs.brs_input"] += 1.0e-8
        with self.assertRaisesRegex(ValueError, "native D1 entry input word"):
            module.replay(output_override=altered(change))

    def test_rehashed_entry_density_and_bg_pair_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            stages = pair["low_stages"]
            qg = stages["d1_entry_slope_inputs.qg"]
            stages["d1_entry_slope_inputs.rhox"] += 1.0e-6
            stages["d1_entry_slope_inputs.bg"] = qg / stages["d1_entry_slope_inputs.rhox"]
        with self.assertRaisesRegex(ValueError, "entry ProgB density source order"):
            module.replay(output_override=altered(change))

    def test_rehashed_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
