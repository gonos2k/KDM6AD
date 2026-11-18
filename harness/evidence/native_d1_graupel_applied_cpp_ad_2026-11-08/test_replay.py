"""Regression checks for the selected D1 graupel applied-amount tangent."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_d1_applied_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("D1 applied replay loader")
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
        for key in ("schema", "selected_cases", "new_stage_fields",
                    "native_d1_applied_words_raw_equal",
                    "native_amount_and_factor_handoffs_raw_equal",
                    "numeric_stage_tangents_per_direction", "directional_applied_terms",
                    "scientific_status", "physical_unit_status"):
            self.assertEqual(actual[key], saved[key])
        self.assertEqual(actual["selected_cases"], 25)
        self.assertEqual(actual["new_stage_fields"], 26)
        self.assertEqual(actual["native_d1_applied_words_raw_equal"], 78)
        self.assertEqual(actual["native_amount_and_factor_handoffs_raw_equal"], 6)
        self.assertEqual(actual["numeric_stage_tangents_per_direction"], 226)
        self.assertGreater(actual["minimum_uncapped_amount_margin"], 0)
        self.assertLess(actual["max_captured_no_cap_signal_error"], 1e-6)
        self.assertLess(actual["max_uncaptured_small_step_signal_error"], 1e-6)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified native D1 graupel applied-amount AD", proc.stdout)

    def test_rehashed_native_applied_amount_is_rejected(self) -> None:
        def change(data):
            data["baseline"]["stage_scalars"]["c3_pre_mf_d1.pgmlt_capped"] += 1e-8
        with self.assertRaisesRegex(ValueError, "native D1 applied word"):
            module.replay(output_override=altered(change))

    def test_rehashed_uncaptured_endpoint_amount_breaks_qr_store(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["0.0001"]
            pair["high_stages"]["c3_pre_mf_d1.pgmlt_capped"] += 1e-8
        with self.assertRaisesRegex(ValueError, "source-order QR2"):
            module.replay(output_override=altered(change))

    def test_rehashed_amount_sign_is_rejected(self) -> None:
        def change(data):
            pair = data["directions"]["qg17_relative"]["finite_differences"]["1e-06"]
            pair["high_stages"]["c3_pre_mf_d1.pgmlt_capped"] *= -1.0
        with self.assertRaisesRegex(ValueError, "signed uncapped warm graupel amount"):
            module.replay(output_override=altered(change))

    def test_rehashed_coordinated_amount_tangent_breaks_qr_chain(self) -> None:
        def change(data):
            i = data["stage_numeric_order"].index("c3_pre_mf_d1.pgmlt_capped")
            # Keep joint=sum(single) while falsifying the applied-amount chain.
            for name in ("qg17_relative", "joint17_relative"):
                data["directions"][name]["stage_jvp"][i] += 1e-5
        with self.assertRaisesRegex(ValueError, "D1 graupel QR applied tangent"):
            module.replay(output_override=altered(change))

    def test_rehashed_missing_vjp_row_is_rejected(self) -> None:
        def change(data):
            del data["vjp"]["final_nc16"]
        with self.assertRaisesRegex(ValueError, "VJP inventory"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
