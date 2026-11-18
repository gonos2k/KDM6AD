import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_host_analysis_batch_replay", HERE / "replay.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class BatchReplayTest(unittest.TestCase):
    def test_saved_batch_contract(self):
        result = replay.replay()
        self.assertEqual(result, json.loads((HERE / "results.json").read_text()))
        self.assertEqual(result["full_output_fd_rows"], 2808)
        self.assertEqual(result["f32_f64_baseline_mismatch_count"], 101)
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
