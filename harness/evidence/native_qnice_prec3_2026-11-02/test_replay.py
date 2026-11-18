"""Check the authenticated native net intervals and later endpoint words."""

import hashlib
import importlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch


module = importlib.import_module(
    "harness.evidence.native_qnice_prec3_2026-11-02.replay"
)


class NativePreC3Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = (module.PARENT / "selected_packet.json").read_bytes()
        cls.endpoint = (Path(module.ROOT) / "endpoint_density_words.json").read_bytes()

    def test_saved_results_and_distinct_times(self):
        result = module.report(self.packet, self.endpoint)
        saved = json.loads((Path(module.ROOT) / "results.json").read_bytes())
        self.assertEqual(result, saved)
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")
        self.assertEqual(result["cells"]["21"]["net_ingress_to_step"],
                         40.58969401890777)
        self.assertEqual(result["cells"]["23"]["net_ingress_to_step"],
                         -171.66587587805407)
        for cell in result["cells"].values():
            self.assertEqual(cell["net_step_to_c3"], 0.0)
            self.assertTrue(cell["endpoint_rho_equals_ingress_den_bits"])
            self.assertFalse(cell["endpoint_qv_equals_ingress_qv_bits"])

    def test_endpoint_selection_digest_is_independent(self):
        altered = json.loads(self.endpoint)
        altered["cells"]["21"]["AL"] = "3dd16af1"
        raw = json.dumps(altered, sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "selected endpoint words SHA-256"):
            module.report(self.packet, raw)

    def test_rehashed_endpoint_semantic_mutations_fail(self):
        for field, replacement, expected in (
            ("AL", "3dd17af0", "AL/ALB-to-RHO"),
            ("RHO", "3efb86c7", "AL/ALB-to-RHO"),
            ("QNICE", "4222e8d4", "endpoint QNICE"),
        ):
            altered = json.loads(self.endpoint)
            altered["cells"]["21"][field] = replacement
            raw = json.dumps(altered, sort_keys=True).encode()
            with (self.subTest(field=field),
                  patch.object(module, "ENDPOINT_WORDS_SHA256",
                               hashlib.sha256(raw).hexdigest())):
                with self.assertRaisesRegex(ValueError, expected):
                    module.report(self.packet, raw)


if __name__ == "__main__":
    unittest.main()
