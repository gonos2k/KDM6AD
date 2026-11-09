"""Regression checks for the selected D1 graupel factor inputs and tangent."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_d1_gfac_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 gfac replay loader")
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
        for key in ("schema", "selected_cases", "parent_stage_fields", "new_gfac_stage_fields",
                    "native_d1_applied_words_raw_equal",
                    "native_d1_gfac_words_raw_equal",
                    "native_d1_gfac_capture_receipts", "d1_gfac_source_expression",
                    "native_amount_and_factor_handoffs_raw_equal",
                    "numeric_stage_tangents_per_direction", "directional_applied_terms",
                    "scientific_status", "physical_unit_status"):
            self.assertEqual(actual[key], saved[key])
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["parent_stage_fields"], 26)
        self.assertEqual(actual["new_gfac_stage_fields"], 7)
        self.assertEqual(actual["native_d1_applied_words_raw_equal"], 78)
        self.assertEqual(actual["native_d1_gfac_words_raw_equal"], 21)
        self.assertEqual(actual["native_amount_and_factor_handoffs_raw_equal"], 6)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 233)
        self.assertGreater(actual["minimum_uncapped_amount_margin"], 0)
        self.assertGreater(actual["minimum_gfac_qg_branch_margin"], 0)
        self.assertGreater(actual["minimum_gfac_temperature_branch_margin"], 0)
        self.assertEqual(actual["fd_resolved_signal_count"] + actual["fd_unresolved_zero_signal_count"], 70)
        self.assertLess(actual["max_captured_no_cap_signal_error"], 1e-6)
        self.assertLess(actual["max_uncaptured_small_step_signal_error"], 1e-6)
        self.assertEqual(actual["directional_applied_terms"]["qg17_relative"]["dgfac_from_n0go"], 0.0)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 graupel gfac-input AD", proc.stdout)

    def test_source_order_gfac_formula_and_active_branch(self) -> None:
        values = {
            "d1_gfac_inputs.qg": 1.8857037232288052e-08,
            "d1_gfac_inputs.t": 274.0,
            "d1_gfac_inputs.rslope_g": 2185409965.0011334,
            "d1_gfac_inputs.n0go": 2.6547754011611264e-12,
            "d1_gfac_inputs.qcrmin": 1.0e-9,
            "d1_gfac_inputs.t0c": 273.15,
            "d1_gfac_inputs.gfac_melt": 307671.4833337283,
            "d1_melt_consumer.gfac_melt": 307671.4833337283,
            "d1_melt_consumer.qg_before": 1.8857037232288052e-08,
            "c3_pre_mf_d1.t_before": 274.0,
        }
        qg_margin, temperature_margin = module.gfac_values(values, "fixture")
        self.assertGreater(qg_margin, 0)
        self.assertGreater(temperature_margin, 0)
        wrong_order_result = dict(values)
        wrong_order_result["d1_gfac_inputs.gfac_melt"] = (
            values["d1_gfac_inputs.rslope_g"]
            * (values["d1_gfac_inputs.n0go"] / values["d1_gfac_inputs.qg"])
        )
        wrong_order_result["d1_melt_consumer.gfac_melt"] = wrong_order_result["d1_gfac_inputs.gfac_melt"]
        self.assertNotEqual(wrong_order_result["d1_gfac_inputs.gfac_melt"], values["d1_gfac_inputs.gfac_melt"])
        with self.assertRaisesRegex(ValueError, "source-order D1 gfac"):
            module.gfac_values(wrong_order_result, "fixture")
        inactive = dict(values)
        inactive["d1_gfac_inputs.qg"] = inactive["d1_gfac_inputs.qcrmin"]
        inactive["d1_melt_consumer.qg_before"] = inactive["d1_gfac_inputs.qg"]
        with self.assertRaisesRegex(ValueError, "active unclamped warm graupel branch"):
            module.gfac_values(inactive, "fixture")

    def test_three_input_gfac_jvp_terms(self) -> None:
        values = {"d1_gfac_inputs.qg": 2.0, "d1_gfac_inputs.rslope_g": 0.5,
                  "d1_gfac_inputs.n0go": 3.0}
        tangent = {"d1_gfac_inputs.qg": 0.1, "d1_gfac_inputs.rslope_g": 0.2,
                   "d1_gfac_inputs.n0go": -0.4}
        terms = module.gfac_jvp_terms(values, tangent)
        for actual, expected in zip(terms, (0.3, -0.1, -0.037500000000000006)):
            self.assertAlmostEqual(actual, expected, places=15)

    def test_rehashed_gfac_endpoint_breaks_source_formula(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["1e-05"]
            pair["high_stages"]["d1_gfac_inputs.gfac_melt"] += 1.0
        with self.assertRaisesRegex(ValueError, "source-order D1 gfac"):
            module.replay(output_override=altered(change))

    def test_rehashed_gfac_tangent_breaks_three_term_chain(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("d1_gfac_inputs.gfac_melt")
            # Keep joint linearity by perturbing QG-only and joint tangents together.
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 0.25
        with self.assertRaisesRegex(ValueError, "D1 gfac three-input chain"):
            module.replay(output_override=altered(change))

    def test_rehashed_parameter_tangent_is_rejected(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("d1_gfac_inputs.qcrmin")
            data["directions"]["qg17_relative"]["stage_jvp"][i] = 1.0
        with self.assertRaisesRegex(ValueError, "constant D1 gfac input tangent"):
            module.replay(output_override=altered(change))

    def test_rehashed_qg_tangent_cannot_be_hidden_by_rslope_compensation(self) -> None:
        def change(data):
            order = data["stage_numeric_order"]
            qg_i = order.index("d1_gfac_inputs.qg")
            slope_i = order.index("d1_gfac_inputs.rslope_g")
            for name in ("qg17_relative", "joint17_relative"):
                tangent = data["directions"][name]["stage_jvp"]
                tangent[qg_i] += 1e-12
                tangent[slope_i] += 4.505048515904758e-12
        with self.assertRaisesRegex(ValueError, "D1 qg input tangent link"):
            module.replay(output_override=altered(change))

    def test_rehashed_temperature_endpoint_breaks_source_link(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["high_stages"]["d1_gfac_inputs.t"] = 300.0
        with self.assertRaisesRegex(ValueError, "captured D1 temperature"):
            module.replay(output_override=altered(change))

    def test_rehashed_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
