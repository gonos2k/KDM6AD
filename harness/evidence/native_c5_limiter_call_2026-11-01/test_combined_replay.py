"""Native conditional producer replay with explicitly frozen zero gates."""

import importlib
import json
import math
import unittest
from pathlib import Path
import torch
from oracle.kdm6.cold import default_dep_sub_params
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

    def test_moving_ice_auxiliary_audit_tracks_actual_c4_cap(self):
        rows = self.cells["22"]
        q = torch.tensor([read(rows, "limiter_in", "working.qi")],
                         dtype=torch.float64)
        n = torch.tensor([read(rows, "limiter_in", "working.ni")],
                         dtype=torch.float64)
        n0 = read(rows, "c4_in", "n0i")
        slope2 = read(rows, "c4_in", "s.rslope2_i")
        params = default_dep_sub_params()
        rh = read(rows, "c3_in", "pre.rh_ice")
        work1 = read(rows, "c4_in", "work1_ice")
        mu = read(rows, "c4_in", "s.rslopemu_i")
        raw_base = (4 * n0 * params.g2pmi * mu * slope2 * (rh - 1)
                    / max(work1, params.qcrmin))
        dt = read(rows, "c5_in", "dtcld")
        half_cap = 0.5 * read(rows, "c3_in", "pre.supsat") / dt
        crossover = half_cap / raw_base
        self.assertGreater(crossover, 90)
        self.assertLess(crossover, 92)
        for below, scale in ((True, crossover * (1 - 1e-6)),
                             (False, crossover * (1 + 1e-6))):
            audit = {}
            combined(rows, q, n, audit=audit,
                     ice_aux=(torch.tensor([n0 * scale], dtype=torch.float64),
                              torch.tensor([slope2], dtype=torch.float64)))
            producer = audit["producers"]
            raw = raw_base * scale
            self.assertTrue(math.isclose(
                producer["margins"]["c4_ice_raw_sign"], raw,
                rel_tol=2e-15))
            self.assertTrue(math.isclose(
                producer["margins"]["c4_ice_cap_1_0"], half_cap - raw,
                rel_tol=2e-9, abs_tol=1e-20))
            self.assertEqual(producer["signature"]["c4_phases"][0][3],
                             0 if below else 1)
            self.assertTrue(math.isclose(
                producer["selected_rates"]["pidep"], min(raw, half_cap),
                rel_tol=2e-15))


if __name__ == "__main__":
    unittest.main()
