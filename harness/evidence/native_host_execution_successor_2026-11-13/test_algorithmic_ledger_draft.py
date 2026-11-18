import copy
import importlib.util
import struct
import unittest
from pathlib import Path

path = Path(__file__).with_name("algorithmic_ledger_draft.py")
spec = importlib.util.spec_from_file_location("algorithmic_ledger_draft", path)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def word(number):
    return struct.pack(">d", number).hex()


def event(*, species="qr", k=1, active=True, before=10.0, outgoing=2.0,
          incoming=1.0, preclamp=9.0, candidate=9.0, selected=None):
    if selected is None:
        selected = candidate if active else before
    return {
        "schema": ledger.SCHEMA, "input_id": "baseline", "runtime_call": 1,
        "one_step_call": 0, "outer_loop": 1, "substep_family":
        "sedimentation_main" if species in ledger.MAIN else "sedimentation_ice",
        "substep_n": 1, "b_zero": 0, "k_zero": k,
        "native_level_bottom_first": 39 - k, "event_ordinal": 0,
        "species": species, "source_kind": "top_uncapped" if k == 0 else "interior_capped",
        "dtype": "f64", "active": active, "x_before_word": word(before),
        "d_out_candidate_word": word(outgoing),
        "d_in_candidate_word": None if k == 0 else word(incoming),
        "preclamp_word": word(preclamp), "candidate_word": word(candidate),
        "selected_word": word(selected),
    }


class LedgerTests(unittest.TestCase):
    def test_interior_and_inactive_gate(self):
        active = ledger.validate_event(event())
        self.assertEqual((active["algorithmic_out_word"], active["algorithmic_in_word"],
                          active["signed_residual_word"]), (word(2), word(1), word(0)))
        inactive = ledger.validate_event(event(active=False))
        self.assertEqual((inactive["algorithmic_out_word"], inactive["algorithmic_in_word"]),
                         (ledger.ZERO, ledger.ZERO))
        self.assertEqual(inactive["signed_residual_word"], word(0))

    def test_top_projection_and_coordinate_kinds(self):
        top = ledger.validate_event(event(k=0, before=10, outgoing=12, incoming=0,
                                          preclamp=-2, candidate=0))
        self.assertEqual(top["signed_residual_word"], word(2))
        self.assertEqual(top["algorithmic_in_word"], ledger.ZERO)
        self.assertEqual(ledger.validate_event(event(species="nr"))["coordinate_kind"], "number")
        self.assertEqual(ledger.validate_event(event(species="brs"))["coordinate_kind"],
                         "graupel_volume")
        self.assertEqual(ledger.validate_event(event(species="qi"))["coordinate_kind"], "mass_like")

    def test_wrong_selection_missing_source_and_nonfinite_rejected(self):
        wrong = event(active=False)
        wrong["selected_word"] = word(9)
        with self.assertRaisesRegex(ValueError, "outer gate"):
            ledger.validate_event(wrong)
        wrong = event(k=0)
        wrong["d_in_candidate_word"] = word(0)
        with self.assertRaisesRegex(ValueError, "top has no source arrival"):
            ledger.validate_event(wrong)
        wrong = event()
        wrong["d_out_candidate_word"] = word(float("nan"))
        with self.assertRaisesRegex(ValueError, "finite"):
            ledger.validate_event(wrong)
        wrong = event(preclamp=999, candidate=999)
        with self.assertRaisesRegex(ValueError, "source-order preclamp"):
            ledger.validate_event(wrong)
        wrong = event(candidate=999, selected=999)
        with self.assertRaisesRegex(ValueError, "source clamp"):
            ledger.validate_event(wrong)

    def test_actual_sedimentation_identity_and_integer_types(self):
        self.assertEqual(ledger.validate_event(event())["scope"],
                         "PROPOSED_ALGORITHMIC_DIAGNOSTIC_ONLY")
        wrong = event()
        wrong["one_step_call"] = 1
        with self.assertRaisesRegex(ValueError, "sedimentation call identity"):
            ledger.validate_event(wrong)
        wrong = event()
        wrong["b_zero"] = False
        with self.assertRaisesRegex(ValueError, "layer identity"):
            ledger.validate_event(wrong)
        wrong = event(k=38)
        wrong["native_level_bottom_first"] = True
        with self.assertRaisesRegex(ValueError, "layer identity"):
            ledger.validate_event(wrong)

    def test_duplicate_event_and_status(self):
        row = event()
        with self.assertRaisesRegex(ValueError, "duplicate transport event"):
            ledger.analyze_events([row, copy.deepcopy(row)])
        result = ledger.analyze_events([row])
        self.assertEqual(result["status"], "DRAFT_BLOCKED")
        self.assertEqual(result["results"][0]["physical_flux_status"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
