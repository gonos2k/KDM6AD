import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("floor_replay", HERE / "replay.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "data.json").read_bytes())
        self.witness = r.WITNESS.read_bytes()

    def test_replay(self):
        self.assertEqual(len(r.verify(self.data, self.witness)), 84)

    def test_changed_source_fails(self):
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in r.SOURCE_SHA256:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(r.ROOT / relative, destination)
            with (root / "oracle/kdm6/slope.py").open("ab") as stream:
                stream.write(b"# changed")
            with self.assertRaisesRegex(ValueError, "source hash"):
                r.verify(self.data, self.witness, root=root)

    def test_modified_witness_bytes_fail(self):
        with self.assertRaises(ValueError):
            r.verify(self.data, self.witness + b" ")

    def test_modified_ice_word_fails(self):
        self.data["rows"][0]["words"]["QICE"] = "3F800000"
        with self.assertRaises(ValueError):
            r.verify(self.data, self.witness)

    def test_changed_saved_optic_fails(self):
        self.data["rows"][0]["saved_deff_um"] = 25.0
        with self.assertRaises(ValueError):
            r.verify(self.data, self.witness)

    def test_duplicate_fails(self):
        self.data["rows"][1] = copy.deepcopy(self.data["rows"][0])
        with self.assertRaises(ValueError):
            r.verify(self.data, self.witness)

    def test_number_causing_floor_crossing_fails(self):
        self.data["rows"][0]["words"]["QNICE"] = "3F800000"
        with self.assertRaises(ValueError):
            r.verify(self.data, self.witness)

    def test_optimized_python_uses_explicit_checks(self):
        import subprocess
        import sys

        subprocess.run(
            [sys.executable, "-O", str(HERE / "replay.py")],
            check=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
