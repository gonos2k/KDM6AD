"""Regression checks for the D1-entry graupel slope capture and tangent."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest


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
    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        for key in (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "new_entry_slope_stage_fields", "native_d1_entry_anchor_words_raw_equal",
            "native_capture_receipts", "pidn0g_native_anchor", "source_pins",
            "numeric_stage_tangents_per_direction", "fd_branch_classifications",
            "entry_fd_resolved_signal_count", "entry_fd_rounding_floor_cases",
            "entry_one_sided_rounding_floor_cases", "directional_applied_terms",
            "entry_slope_branch_checks", "minimum_accepted_rhox_upper_margin",
            "scientific_status", "physical_unit_status",
        ):
            self.assertEqual(actual[key], saved[key])
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
