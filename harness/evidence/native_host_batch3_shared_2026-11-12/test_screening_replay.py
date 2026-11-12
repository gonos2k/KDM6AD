import copy
import importlib.util
import json
import zipfile
import unittest
from pathlib import Path

p = Path(__file__).with_name("screening_replay.py")
spec = importlib.util.spec_from_file_location("screening_replay", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ScreeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(m.ARCHIVE) as z:
            data = json.loads(z.read("screen/inputs.json"))
            cls.inputs = {x["key"]: x for x in data["inputs"]}
        plan = json.loads((m.HERE / "raw/screening_preflight_plan.json").read_bytes())
        cls.specs = {x["id"]: x for x in plan["directions"]}
        cls.centers = {x: cls.inputs["center_" + x] for x in m.CENTERS}

    def test_saved_result(self):
        self.assertEqual(
            m.replay(), json.loads((m.HERE / "screening_results.json").read_bytes())
        )

    def test_rehashed_direction_or_step_spoof(self):
        x = copy.deepcopy(self.inputs["lower_th_-1"])
        center = self.centers["lower"]
        altered = copy.deepcopy(x)
        altered["direction"] = "qv"
        # A recomputed JSON digest cannot turn a different declared direction into the original seed.
        m.sha(json.dumps(altered, sort_keys=True).encode())
        with self.assertRaisesRegex(ValueError, "preflight expected endpoint"):
            m.check_input(altered, center, self.specs, 1e-4)
        with self.assertRaisesRegex(ValueError, "preflight expected endpoint"):
            m.check_input(x, center, self.specs, 1e-5)

    def test_graph_center_spoof(self):
        x = copy.deepcopy(self.centers["lower"])
        x["center"] = "upper"
        with self.assertRaisesRegex(ValueError, "graph key/center identity"):
            m.check_graph_center(x, "center_lower", "screen", self.centers)
        x = copy.deepcopy(self.centers["lower"])
        x["state_words"][0] = "0000000000000000"
        with self.assertRaisesRegex(ValueError, "graph input center"):
            m.check_graph_center(x, "center_lower", "screen", self.centers)

    def test_reuse_wrong_side_rejected(self):
        x = copy.deepcopy(self.inputs["lower_th_-1"])
        x["nominal_h"] = 1e-5
        proof = {"center": "upper", "side": "lower", "th_word": x["state_words"][15]}
        with self.assertRaisesRegex(ValueError, "reuse input/side"):
            m.check_reuse_identity(proof, "lower", x)

    def test_rehashed_duplicate_diagnostic_rejected(self):
        with zipfile.ZipFile(m.ARCHIVE) as z:
            records = json.loads(z.read("screen/offline_summary.json"))["comparisons"]
        records[0] = copy.deepcopy(records[1])
        m.sha(json.dumps(records, sort_keys=True).encode())
        with self.assertRaisesRegex(ValueError, "analysis record inventory"):
            m.check_diagnostic_inventory("screen", records)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            m.vector(["7ff8000000000000"], 1, "mutation")


if __name__ == "__main__":
    unittest.main()
