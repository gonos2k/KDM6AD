"""Regression checks for live D1-entry precg2 production and its AD chain."""

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
spec = importlib.util.spec_from_file_location("native_d1_precg2_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 precg2 replay loader")
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


class ReplayTests(unittest.TestCase):
    def assert_saved_contract(self, actual: dict, saved: dict) -> None:
        stable_keys = (
            "schema", "selected_cases", "parent_stage_fields", "parent_gfac_stage_fields",
            "parent_entry_slope_stage_fields", "new_entry_pid_stage_fields",
            "new_entry_precg2_stage_fields", "new_melt_producer_stage_fields",
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

    def test_replay_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(actual, saved)
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["new_entry_precg2_stage_fields"], 8)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 313)
        self.assertEqual(actual["native_d1_precg2_anchor_words_raw_equal"], 9)
        self.assertEqual(actual["precg2_fd_resolved_signal_count"], 50)
        self.assertEqual(actual["precg2_fd_rounding_floor_cases"], 14)
        self.assertEqual(actual["precg2_one_sided_rounding_floor_cases"], 13)
        self.assertLessEqual(actual["max_precg2_fd_relative_error"], 0.003)
        self.assertTrue(all(margin > 0 for margin in actual["precg2_floor_margins"].values()))

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 entry precg2 producer AD", proc.stdout)

    def test_saved_entry_slope_max_must_match_rows(self) -> None:
        saved = json.loads((HERE / "results.json").read_text())
        saved["maximum_entry_slope_formula_ulp_distance"] = 999999
        with self.assertRaises(AssertionError):
            self.assert_saved_contract(saved, saved)

    def test_native_anchor_is_enforced(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"][module.PRECG2_STAGE + ".avtg"] += 1e-7
        with self.assertRaisesRegex(ValueError, "native D1 precg2 anchor word"):
            module.replay(output_override=altered(change))

    def test_rehashed_bvtg2_formula_mutation_is_rejected(self) -> None:
        def change(data):
            endpoint(data)[module.PRECG2_STAGE + ".bvtg2"] += 1e-6
        with self.assertRaisesRegex(ValueError, "source-order bvtg2"):
            module.replay(output_override=altered(change))

    def test_rehashed_avtg_bvtg_interpolation_is_rejected(self) -> None:
        def change(data):
            stages = endpoint(data, direction="qg17_relative", h="0.0001", side="high")
            for field in ("avtg", "bvtg"):
                key = module.PRECG2_STAGE + "." + field
                stages[key] = math.nextafter(stages[key], math.inf)
        with self.assertRaisesRegex(ValueError, "source-order ProgB avtg interpolation"):
            module.replay(output_override=altered(change))

    def test_rehashed_precg2_outside_formula_ulp_bound_is_rejected(self) -> None:
        def change(data):
            endpoint(data)[module.PRECG2_STAGE + ".precg2"] += 1e-5
        with self.assertRaisesRegex(ValueError, "precg2 pow/product within 8 ULP"):
            module.replay(output_override=altered(change))

    def test_one_ulp_precg2_parent_handoff_is_rejected(self) -> None:
        def change(data):
            key = module.PRECG2_STAGE + ".precg2"
            stages = endpoint(data, direction="joint17_relative", h="0.0001", side="high")
            stages[key] = math.nextafter(stages[key], math.inf)
        with self.assertRaisesRegex(ValueError, "parent D1 melt precg2 value handoff"):
            module.replay(output_override=altered(change))

    def test_g5_gamma_portable_one_ulp_candidate(self) -> None:
        original = module.source_order_g5pbgo2

        def one_ulp(value: float) -> float:
            return math.nextafter(original(value), math.inf)

        with mock.patch.object(module, "source_order_g5pbgo2", side_effect=one_ulp):
            result = module.replay()
        self.assertLessEqual(result["precg2_source_order_g5_max_ulp_distance"], 16)
        saved = json.loads((HERE / "results.json").read_text())
        self.assert_saved_contract(result, saved)

    def test_g5_outside_portable_bound_is_rejected(self) -> None:
        def change(data):
            values = data["baseline"]["stage_scalars"]
            key = module.PRECG2_STAGE + ".g5pbgo2"
            for _ in range(20):
                values[key] = math.nextafter(values[key], math.inf)
        with self.assertRaisesRegex(ValueError, "g5pbgo2 gamma within 16 ULP"):
            module.replay(output_override=altered(change))

    def test_precg2_jvp_chain_mutation_is_rejected(self) -> None:
        def change(data):
            index = data["stage_numeric_order"].index(module.PRECG2_STAGE + ".precg2")
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][index] += 0.01
        with self.assertRaisesRegex(ValueError, "D1 precg2 JVP chain"):
            module.replay(output_override=altered(change))

    def test_rehashed_gate_mutation_is_rejected(self) -> None:
        def change(data):
            endpoint(data)[module.PRECG2_STAGE + ".active"] = False
        with self.assertRaisesRegex(ValueError, "active ProgB gate matches parent"):
            module.replay(output_override=altered(change))

    def test_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
