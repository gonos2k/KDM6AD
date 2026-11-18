"""Boundary evidence tests use the original 312-row native packet."""

import hashlib
import importlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch


module = importlib.import_module(
    "harness.evidence.native_qnice_same_call_2026-11-02.replay"
)


class NativeQniceSameCall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (module.PARENT / "selected_packet.json").read_bytes()

    def test_saved_result_and_numeric_handoffs(self):
        report = module.replay(self.raw)
        saved = json.loads((Path(module.ROOT) / "results.json").read_bytes())
        self.assertEqual(report, saved)
        self.assertEqual(report["parent_selected_rows"], 312)
        self.assertEqual(report["physical_unit_status"], "INCONCLUSIVE")
        self.assertEqual(report["cells"]["21"]["legacy_ingress_ni"],
                         0.1376752108335495)
        self.assertEqual(report["cells"]["23"]["legacy_ingress_ni"],
                         116719.8203125)

    def test_rehashed_packet_is_not_admitted(self):
        packet = json.loads(self.raw)
        trace = next(r for r in packet["host_selected_trace"]["on_v1"] if
                     r["stage"] == "MP_INPUT" and r["native_ijk_1based"][-1] == 21)
        index = trace["fields"].index("Q")
        trace["raw_hex"][index] = format(int(trace["raw_hex"][index], 16) ^ 1, "08x")
        changed = json.dumps(packet, sort_keys=True).encode()
        with self.assertRaises(ValueError):
            module.replay(changed, hashlib.sha256(changed).hexdigest())

    def test_independent_qv_widening_check(self):
        packet = json.loads(self.raw)
        row = next(r for r in packet["selected_rows"] if
                   r["k_zero"] == "20" and r["stage"] == "converted_ingress"
                   and r["field"] == "scalar_ingress_state->qv")
        row["raw_hex"] = format(int(row["raw_hex"], 16) ^ 1, "x")
        # Isolate this replay's own semantic check; the production path first
        # authenticates the fixed packet with the parent verifier.
        with patch.object(module.PARENT_VERIFIER, "verify", return_value={}):
            with self.assertRaisesRegex(ValueError, r"host/C\+\+ widened bit Q"):
                module.replay(json.dumps(packet).encode())

    def test_conditional_density_maps_stay_distinct(self):
        report = module.replay(self.raw)
        for level in ("21", "23"):
            cell = report["cells"][level]
            values = cell["conditional_dry_number"]
            den = cell["legacy_ingress_den"]
            qv = cell["converted_ingress_qv"]
            ni = cell["legacy_ingress_ni"]
            self.assertEqual(values["source_inferred_native_dry_den"], den)
            self.assertEqual(values["generic_v2_density_from_den_and_qv"],
                             den / (1.0 + qv))
            self.assertEqual(values["host_ni_times_native_den"], ni * den)
            self.assertEqual(values["host_ni_times_generic_v2_density"],
                             ni * (den / (1.0 + qv)))
            self.assertTrue(math.isclose(
                values["generic_to_native_density_ratio"],
                1.0 / (1.0 + qv), rel_tol=2e-16))
            self.assertLess(values["generic_v2_density_from_den_and_qv"], den)


if __name__ == "__main__":
    unittest.main()
