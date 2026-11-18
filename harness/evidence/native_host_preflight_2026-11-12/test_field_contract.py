import copy
import importlib.util
import json
import unittest
from pathlib import Path

p = Path(__file__).with_name("field_contract.py")
spec = importlib.util.spec_from_file_location("field_contract", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FieldContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(p.with_name("field_contract.json").read_bytes())
        cls.archive = p.with_name("field_contract_sources.zip").read_bytes()

    def test_real_sources_and_prospective_block(self):
        result = m.validate(self.contract, self.archive)
        self.assertEqual(
            (result["groups"], result["measurements"], result["proposed_masks"]),
            (7, 28, 19),
        )
        self.assertEqual(result["new_measurements"], "BLOCKED")

    def test_source_location_must_refer_to_real_line(self):
        d = copy.deepcopy(self.contract)
        field = d["groups"]["rate_cap_tie"][1]
        field["source_locations"][0]["line"] += 1
        with self.assertRaisesRegex(ValueError, "source location"):
            m.validate(d, self.archive)

    def test_active_ledger_cannot_be_claimed_as_candidate_flux(self):
        d = copy.deepcopy(self.contract)
        item = next(
            x for x in d["groups"]["sedimentation"] if x["id"] == "transport_qr"
        )
        item["blocked_reason"] = "candidate flux is applied amount"
        with self.assertRaisesRegex(ValueError, "transport top/inactive/candidate"):
            m.validate(d, self.archive)

    def test_new_mask_cannot_enter_old_adapter(self):
        d = copy.deepcopy(self.contract)
        d["proposed_new_masks"][0]["adapter_compatibility"] = "SUPPORTED"
        with self.assertRaisesRegex(ValueError, "new mask status"):
            m.validate(d, self.archive)

    def test_source_archive_tamper_rejected(self):
        d = bytearray(self.archive)
        d[len(d) // 2] ^= 1
        with self.assertRaisesRegex(ValueError, "archive SHA"):
            m.validate(self.contract, bytes(d))

    def test_missing_live_tangent_and_precip_contract_rejected(self):
        d = copy.deepcopy(self.contract)
        field = next(
            x
            for x in d["groups"]["same_call_water"]
            if x["id"] == "total_rain_fnresult"
        )
        field["required_record_kinds"] = ["value"]
        with self.assertRaisesRegex(ValueError, "record kinds"):
            m.validate(d, self.archive)
        d = copy.deepcopy(self.contract)
        d["groups"]["same_call_water"] = [
            x
            for x in d["groups"]["same_call_water"]
            if x["id"] != "total_rain_fnresult"
        ]
        with self.assertRaisesRegex(ValueError, "measurement inventory"):
            m.validate(d, self.archive)


if __name__ == "__main__":
    unittest.main()
