"""Mutation and branch-window checks for archived C++ pre2/C2c AD."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_pre2_cpp_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("pre2/C2c AD replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def altered(change) -> tuple[bytes, str]:
    result = json.loads((HERE / "raw/cpp_result.json").read_text())
    change(result)
    raw = (json.dumps(result, sort_keys=True) + "\n").encode()
    return raw, hashlib.sha256(raw).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_and_saved_contract(self) -> None:
        actual = module.replay()
        saved = json.loads((HERE / "results.json").read_text())
        for name in ("schema", "baseline_outputs_raw_equal", "input_order",
                     "output_order", "direction_names", "scientific_status",
                     "physical_unit_status"):
            self.assertEqual(actual[name], saved[name])
        self.assertEqual(actual["baseline_outputs_raw_equal"], 12)
        for direction, diagnostic in actual["portable_diagnostics"].items():
            self.assertLessEqual(diagnostic["max_transpose_fraction_of_roundoff_bound"], 1)
            self.assertLessEqual(diagnostic["max_fixed_branch_normalized_fd_residual"], 1e-6)
            self.assertLessEqual(diagnostic["max_all_resolved_signal_relative_fd_residual_h1e5"], 1e-6)
            self.assertEqual(
                set(diagnostic["resolved_outputs_h1e5"])
                | set(diagnostic["unresolved_outputs_h1e5"]),
                set(actual["output_order"]),
            )
            self.assertEqual(
                set(diagnostic["resolved_outputs_h1e5"])
                & set(diagnostic["unresolved_outputs_h1e5"]), set(),
            )
        self.assertEqual(actual["branch_windows"]["0.0001"]["qg_relative"]["upper_cap_high"], True)
        self.assertEqual(actual["branch_windows"]["0.0001"]["brs_relative"]["upper_cap_low"], True)

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified conditional C++ pre2/C2c AD", proc.stdout)

    def test_rehashed_baseline_word_is_rejected(self) -> None:
        def change(data):
            i = data["output_order"].index("naacw")
            data["baseline"]["raw_hex"][i] = format(
                int(data["baseline"]["raw_hex"][i], 16) + 1, "x")
        with self.assertRaisesRegex(ValueError, "baseline value/word roundtrip"):
            module.replay(output_override=altered(change))

    def test_rehashed_coordinated_bvtg_tangent_is_rejected_by_fd(self) -> None:
        def change(data):
            i = data["output_order"].index("bvtg")
            data["vjp_rows"]["bvtg"] = [0.0, 0.0]
            for direction in data["directions"].values():
                direction["jvp"][i] = 0.0
        with self.assertRaisesRegex(ValueError, "FD signal classification: qg_relative/bvtg"):
            module.replay(output_override=altered(change))

    def test_rehashed_fd_cap_endpoint_is_rejected(self) -> None:
        def change(data):
            ep = data["directions"]["qg_relative"]["finite_differences"]["0.0001"]
            ep["high"][0] = 899.99
        with self.assertRaisesRegex(ValueError, "FD endpoint ProgB density/clamp"):
            module.replay(output_override=altered(change))

    def test_rehashed_relative_seed_is_rejected(self) -> None:
        def change(data):
            data["directions"]["joint_relative"]["seed"][1] = 0.0
        with self.assertRaisesRegex(ValueError, "relative seed: joint_relative"):
            module.replay(output_override=altered(change))


if __name__ == "__main__":
    unittest.main()
