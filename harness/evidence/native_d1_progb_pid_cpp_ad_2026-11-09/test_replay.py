"""Regression checks for entry ProgB cmg/pidn0g production and its AD."""

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
spec = importlib.util.spec_from_file_location("native_d1_progb_pid_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 entry PID replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    data = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(data)
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


def baseline(data: dict, field: str) -> float:
    return data["baseline"]["stage_scalars"][field]


def pid_fixture() -> dict[str, float | bool]:
    stages = json.loads((HERE / "raw/cpp_result.json").read_text())["baseline"]["stage_scalars"]
    rhox = stages["d1_entry_pid_inputs.rhox"]
    qg = stages["d1_entry_slope_inputs.qg"]
    brs_input = stages["d1_entry_slope_inputs.brs_input"]
    cmg = module.source_order_cmg(rhox)
    pidn0g = module.source_order_pidn0g(cmg, 4_000_000.0, 6.000000000000001, 1.0)
    return {
        "d1_entry_pid_inputs.active": True,
        "d1_entry_pid_inputs.midpoint_trace": 0.0,
        "d1_entry_pid_inputs.rhox": rhox,
        "d1_entry_pid_inputs.cmg": cmg,
        "d1_entry_pid_inputs.pidn0g": pidn0g,
        "d1_entry_pid_inputs.n0g": 4_000_000.0,
        "d1_entry_pid_inputs.g1pdgmg": 6.000000000000001,
        "d1_entry_pid_inputs.g1pmg": 1.0,
        "d1_entry_slope_inputs.rhox": rhox,
        "d1_entry_slope_inputs.pidn0g": pidn0g,
        "d1_entry_slope_inputs.qg": qg,
        "d1_entry_slope_inputs.brs_input": brs_input,
        "d1_gfac_inputs.qcrmin": 1.0e-9,
    }


class ReplayTests(unittest.TestCase):
    def assert_saved_contract(self, actual: dict, saved: dict) -> None:
        keys = (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "parent_entry_slope_stage_fields", "new_entry_pid_stage_fields",
            "native_d1_applied_words_raw_equal", "parent_native_d1_gfac_words_raw_equal",
            "native_d1_entry_anchor_words_raw_equal", "native_capture_receipts",
            "cmg_pidn0g_native_anchor",
            "entry_pid_source_order_cases", "entry_cmg_source_order_cases",
            "entry_pidn0g_parent_value_handoff_cases", "entry_pidn0g_parent_jvp_handoff_directions",
            "pidn0g_fd_via_parent_entry_slope_handoff", "pid_parameter_words",
            "pid_midpoint_trace", "pid_active_all_cases", "source_pins",
            "cmg_source_expression", "pidn0g_source_expression",
            "numeric_stage_tangents_per_direction", "pid_fd_resolved_signal_count",
            "pid_fd_rounding_floor_cases", "pid_one_sided_rounding_floor_cases",
            "fd_branch_classifications", "entry_fd_resolved_signal_count",
            "entry_fd_rounding_floor_cases", "entry_one_sided_rounding_floor_cases",
            "minimum_accepted_rhox_upper_margin",
            "directional_applied_terms", "scientific_status", "physical_unit_status",
        )
        for key in keys:
            self.assertEqual(actual[key], saved[key])

        # The parent slope replay allows a portable eight ULP source-formula
        # diagnostic. Compare all other branch-row evidence exactly.
        cpp = json.loads((HERE / "raw/cpp_result.json").read_text())
        cases = {"baseline": cpp["baseline"]["stage_scalars"]}
        for direction in module.DIRECTIONS:
            for h, pair in cpp["directions"][direction]["finite_differences"].items():
                for side in ("low", "high"):
                    cases[f"{direction}/{h}/{side}"] = pair[side + "_stages"]
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
                self.assertTrue(math.isfinite(expected) and expected > 0)
                self.assertEqual(distance, module.ulp_distance(
                    expected, cases[row["case"]]["d1_entry_slope_inputs.rslope_g"]))
                self.assertLessEqual(distance, 8)
                distances.append(distance)
            self.assertEqual(summary["maximum_entry_slope_formula_ulp_distance"], max(distances))
        def strip(rows):
            return [{key: value for key, value in row.items() if key not in portable} for row in rows]
        self.assertEqual(strip(actual_rows), strip(saved_rows))

    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["parent_stage_fields"], 26)
        self.assertEqual(actual["parent_gfac_stage_fields"], 7)
        self.assertEqual(actual["parent_entry_slope_stage_fields"], 7)
        self.assertEqual(actual["new_entry_pid_stage_fields"], 8)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 247)
        self.assertEqual(actual["native_d1_entry_anchor_words_raw_equal"], 18)
        self.assertEqual(actual["entry_pid_source_order_cases"], 25)
        self.assertEqual(actual["entry_cmg_source_order_cases"], 25)
        self.assertEqual(actual["entry_pidn0g_parent_value_handoff_cases"], 25)
        self.assertEqual(actual["entry_pidn0g_parent_jvp_handoff_directions"], 3)
        self.assertEqual(actual["pid_parameter_words"], {
            "n0g": 4_000_000.0, "g1pdgmg": 6.000000000000001, "g1pmg": 1.0,
        })
        self.assertEqual(actual["pid_midpoint_trace"], 0.0)
        self.assertTrue(actual["pid_active_all_cases"])
        self.assertTrue(actual["pidn0g_fd_via_parent_entry_slope_handoff"])
        self.assertEqual(actual["pid_fd_resolved_signal_count"], 10)
        self.assertEqual(actual["pid_fd_rounding_floor_cases"], 1)
        self.assertEqual(actual["pid_one_sided_rounding_floor_cases"], 2)

        mislabeled = {**saved, "fd_branch_classifications": [
            dict(row) for row in saved["fd_branch_classifications"]]}
        mislabeled["fd_branch_classifications"][0]["classification"] = "wrong_branch"
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(actual, mislabeled)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 entry ProgB pidn0g AD", proc.stdout)

    def test_source_order_cmg_and_pid_products(self) -> None:
        values = pid_fixture()
        module.pid_values(values, "fixture")

        altered_gamma = dict(values)
        altered_gamma["d1_entry_pid_inputs.g1pdgmg"] = 6.0
        with self.assertRaisesRegex(ValueError, "source-order pidn0g"):
            module.pid_values(altered_gamma, "fixture")

        altered_cmg = dict(values)
        altered_cmg["d1_entry_pid_inputs.cmg"] += 1.0
        altered_cmg["d1_entry_pid_inputs.pidn0g"] = module.source_order_pidn0g(
            altered_cmg["d1_entry_pid_inputs.cmg"], 4_000_000.0, 6.000000000000001, 1.0)
        altered_cmg["d1_entry_slope_inputs.pidn0g"] = altered_cmg["d1_entry_pid_inputs.pidn0g"]
        with self.assertRaisesRegex(ValueError, "source-order cmg"):
            module.pid_values(altered_cmg, "fixture")

        wrong_handoff = dict(values)
        wrong_handoff["d1_entry_pid_inputs.g1pdgmg"] = math.nextafter(
            values["d1_entry_pid_inputs.g1pdgmg"], math.inf)
        wrong_handoff["d1_entry_pid_inputs.pidn0g"] = module.source_order_pidn0g(
            wrong_handoff["d1_entry_pid_inputs.cmg"], wrong_handoff["d1_entry_pid_inputs.n0g"],
            wrong_handoff["d1_entry_pid_inputs.g1pdgmg"], wrong_handoff["d1_entry_pid_inputs.g1pmg"])
        with self.assertRaisesRegex(ValueError, "parent entry pidn0g value handoff"):
            module.pid_values(wrong_handoff, "fixture")

    def test_rehashed_one_ulp_gamma_change_breaks_pid_source_order(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["d1_entry_pid_inputs.g1pdgmg"] = 6.0
        with self.assertRaisesRegex(ValueError, "archived live ProgB parameter word: g1pdgmg"):
            module.replay(output_override=altered(change))

    def test_entry_pid_jvp_product_chain(self) -> None:
        values = {
            "d1_entry_pid_inputs.cmg": 3.0,
            "d1_entry_pid_inputs.n0g": 4.0,
            "d1_entry_pid_inputs.g1pdgmg": 6.000000000000001,
            "d1_entry_pid_inputs.g1pmg": 1.0,
        }
        tangent = {"d1_entry_pid_inputs.cmg": 0.2, "d1_entry_pid_inputs.n0g": 0.0}
        terms = module.pid_jvp_terms(values, tangent)
        self.assertAlmostEqual(terms[0], 4.8, places=14)
        self.assertEqual(terms[1], 0.0)

    def test_compensated_cmg_parameter_tangents_break_live_chain(self) -> None:
        def change(data):
            order = data["stage_numeric_order"]
            cmg_i = order.index("d1_entry_pid_inputs.cmg")
            n0g_i = order.index("d1_entry_pid_inputs.n0g")
            cmg = baseline(data, "d1_entry_pid_inputs.cmg")
            n0g = baseline(data, "d1_entry_pid_inputs.n0g")
            delta_cmg = 1.0e-6
            delta_n0g = -n0g / cmg * delta_cmg
            for name in ("qg17_relative", "joint17_relative"):
                tangent = data["directions"][name]["stage_jvp"]
                tangent[cmg_i] += delta_cmg
                tangent[n0g_i] += delta_n0g
        with self.assertRaisesRegex(ValueError, "D1 entry cmg JVP chain"):
            module.replay(output_override=altered(change))

    def test_rehashed_cmg_endpoint_breaks_source_formula(self) -> None:
        def change(data):
            pair = data["directions"]["joint17_relative"]["finite_differences"]["0.001"]
            pair["high_stages"]["d1_entry_pid_inputs.cmg"] += 1.0
        with self.assertRaisesRegex(ValueError, "source-order cmg"):
            module.replay(output_override=altered(change))

    def test_rehashed_active_or_midpoint_control_is_rejected(self) -> None:
        def disable_active(data):
            data["baseline"]["stage_scalars"]["d1_entry_pid_inputs.active"] = 0
        with self.assertRaisesRegex(ValueError, "active ProgB gate"):
            module.replay(output_override=altered(disable_active))

        def enable_midpoint(data):
            data["baseline"]["stage_scalars"]["d1_entry_pid_inputs.midpoint_trace"] = 1.0
        with self.assertRaisesRegex(ValueError, "midpoint trace disabled"):
            module.replay(output_override=altered(enable_midpoint))

    def test_active_and_midpoint_controls_are_fixed(self) -> None:
        values = {
            "d1_entry_pid_inputs.active": True,
            "d1_entry_pid_inputs.midpoint_trace": 0.0,
            "d1_entry_pid_inputs.rhox": 900.0,
            "d1_entry_pid_inputs.cmg": module.source_order_cmg(900.0),
            "d1_entry_pid_inputs.pidn0g": module.source_order_pidn0g(
                module.source_order_cmg(900.0), 4_000_000.0, 6.000000000000001, 1.0),
            "d1_entry_pid_inputs.n0g": 4_000_000.0,
            "d1_entry_pid_inputs.g1pdgmg": 6.000000000000001,
            "d1_entry_pid_inputs.g1pmg": 1.0,
            "d1_entry_slope_inputs.qg": 5.4e-5,
            "d1_entry_slope_inputs.brs_input": 5.4e-5 / 900.0,
            "d1_gfac_inputs.qcrmin": 1.0e-9,
            "d1_entry_slope_inputs.rhox": 900.0,
            "d1_entry_slope_inputs.pidn0g": module.source_order_pidn0g(
                module.source_order_cmg(900.0), 4_000_000.0, 6.000000000000001, 1.0),
        }
        inactive = dict(values)
        inactive["d1_entry_pid_inputs.active"] = False
        with self.assertRaisesRegex(ValueError, "active ProgB gate"):
            module.pid_values(inactive, "fixture")
        trace_enabled = dict(values)
        trace_enabled["d1_entry_pid_inputs.midpoint_trace"] = 1.0
        with self.assertRaisesRegex(ValueError, "midpoint trace disabled"):
            module.pid_values(trace_enabled, "fixture")

    def test_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
