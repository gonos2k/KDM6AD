import copy
import importlib.util
import json
import unittest
import subprocess
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("replay_east", HERE / "replay.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class WitnessTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "witness.json").read_bytes())

    def test_complete(self):
        self.assertEqual(r.verify(self.data)["profiles"], 10)

    def test_reject_mutations(self):
        for change in (
            "moment",
            "original_bt",
            "qnc_bt",
            "pilot_bt",
            "optics",
            "location",
            "observation",
        ):
            with self.subTest(change=change):
                x = copy.deepcopy(self.data)
                p = x["profiles"][0]
                if change == "moment":
                    p["changed_moment_words"][0]["words"]["pilot_control"] = "00000000"
                elif change == "original_bt":
                    p["bt"][0][0] += 1
                elif change == "qnc_bt":
                    p["bt"][1][0] += 1
                elif change == "pilot_bt":
                    p["bt"][2][0] += 1
                elif change == "optics":
                    p["optics"][2]["hydro.txt"]["values"][0] += 1
                elif change == "location":
                    p["j"] = 99
                elif change == "observation":
                    p["observation"][0] += 1
                with self.assertRaises(ValueError):
                    r.verify(x)

    def test_pilot_profile_ordinal_and_receipt(self):
        spec = importlib.util.spec_from_file_location(
            "pilot_east", HERE / "crosscheck_pilot.py"
        )
        pilot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pilot)
        for change in ("ordinal", "receipt"):
            x = copy.deepcopy(self.data)
            if change == "ordinal":
                x["profiles"][0]["case_profiles_1based"][2] = "999"
            else:
                x["chunk_receipts"][str(x["profiles"][0]["chunk"])][
                    "pilot_result_receipt_sha256"
                ] = "0" * 64
            with self.assertRaises(ValueError):
                pilot.check(x)

    def test_helper_mutation_rejected_before_numeric_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            manifest = json.loads((HERE / "source_manifest.json").read_bytes())
            (target / "source_manifest.json").write_bytes(
                (HERE / "source_manifest.json").read_bytes()
            )
            for name in manifest["sha256"]:
                (target / name).write_bytes((HERE / name).read_bytes())
            with (target / "analyze.py").open("ab") as stream:
                stream.write(b"\n# altered helper\n")
            with patch.object(r, "HERE", target):
                with self.assertRaisesRegex(
                    ValueError, "packet source SHA differs: analyze.py"
                ):
                    r.verify({})
            spec = importlib.util.spec_from_file_location(
                "guard_east", HERE / "crosscheck_qnc.py"
            )
            guard = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(guard)
            with patch.object(guard, "HERE", target):
                with self.assertRaisesRegex(
                    ValueError, "packet source SHA differs: analyze.py"
                ):
                    guard.check(target / "absent-archive.tar.gz")

    def test_official_replay_requires_guard_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "chunk_artifacts.tar.gz"
            archive.write_bytes(b"changed guard archive")
            with patch.object(r, "QNC_ARCHIVE", archive):
                with self.assertRaisesRegex(ValueError, "guard archive SHA differs"):
                    r.verify(self.data)

    def test_optimized_python_rejects_mutation(self):
        script = """
import importlib.util
import json
import sys
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("replay", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with open(sys.argv[2]) as stream:
    witness = json.load(stream)
witness["profiles"][0]["bt"][2][0] += 1
module.verify(witness)
"""
        result = subprocess.run(
            [
                sys.executable,
                "-O",
                "-c",
                script,
                str(HERE / "replay.py"),
                str(HERE / "witness.json"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ValueError", result.stderr)


if __name__ == "__main__":
    unittest.main()
