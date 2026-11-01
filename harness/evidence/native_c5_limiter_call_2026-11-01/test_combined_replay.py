"""Native conditional producer replay with explicitly frozen zero gates."""

import importlib
import json
import unittest
from pathlib import Path
import torch
combined_module = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.combined_replay")
combined = combined_module.combined
combined_diagnostics = combined_module.combined_diagnostics
read = combined_module.read


class CombinedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packet = json.loads(
            (Path(__file__).parent / "selected_packet.json").read_bytes()
        )
        cls.cells = {
            k: {
                (r["stage"], r["field"]): r.copy()
                for r in packet["selected_rows"]
                if r["k_zero"] == k
            }
            for k in ("20", "22")
        }

    def test_raw_baseline_and_tied_frozen_species(self):
        for k, rows in self.cells.items():
            with self.subTest(level=k):
                q = torch.tensor(
                    [read(rows, "limiter_in", "working.qi")], dtype=torch.float64
                )
                n = torch.tensor(
                    [read(rows, "limiter_in", "working.ni")], dtype=torch.float64
                )
                self.assertEqual(len(combined(rows, q, n, check=True)), 2)
                result = combined_diagnostics(rows)
                self.assertEqual(result["status"], "pass")
                self.assertEqual(
                    result["frozen_zero_gate_exclusions"], ["C4 QS", "C4 QG"]
                )
                self.assertEqual(len(result["audit"]["limiter"]), 14)
                frozen = result["audit"]["producers"]["frozen_species_bits"]
                self.assertTrue(all(int(v, 16) == 0 for v in frozen.values()))
                for direction in result["directions"]:
                    self.assertEqual(len(direction["trials"]), 3)
                    for trial in direction["trials"]:
                        self.assertTrue(trial["stable"])
                        for side in ("plus_audit", "minus_audit"):
                            self.assertEqual(
                                trial[side]["producers"]["frozen_species_bits"], frozen
                            )

    def test_c3_c4_output_corruption_rejected(self):
        for stage, field in [("c3_out", "icenuc.ninud"), ("c4_out", "depsub.psdep")]:
            rows = {k: v.copy() for k, v in self.cells["22"].items()}
            rows[(stage, field)]["raw_hex"] = format(
                int(rows[(stage, field)]["raw_hex"], 16) ^ 1, "x"
            )
            q = torch.tensor(
                [read(rows, "limiter_in", "working.qi")], dtype=torch.float64
            )
            n = torch.tensor(
                [read(rows, "limiter_in", "working.ni")], dtype=torch.float64
            )
            with self.subTest(field=field), self.assertRaises(ValueError):
                combined(rows, q, n, check=True)


if __name__ == "__main__":
    unittest.main()
