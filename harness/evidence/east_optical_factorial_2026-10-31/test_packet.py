import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "packet", Path(__file__).with_name("packet.py")
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.w = {
            "profiles": [
                {
                    "flat": j * 234 - 1,
                    "chunk": (j * 234 - 1) // 512,
                    "case_profiles_1based": ["1", "2", "3"],
                    "observation": [0.0] * 7,
                    "bt": [[0.0] * 7, [1.0] * 7, [4.0] * 7],
                }
                for j in p.JS
            ]
        }
        self.x = {
            "schema": "east-optical-factorial-export-v1",
            "recorded_direct_calls": 4,
            "recorded_K_calls": 0,
            "witness_sha256": p.digest((p.WITNESS / "witness.json").read_bytes()),
            "mapping": [
                {
                    "j": j,
                    "flat": j * 234 - 1,
                    "chunk": (j * 234 - 1) // 512,
                    "guard_ordinal": 2,
                    "pilot_ordinal": 3,
                }
                for j in p.JS
            ],
            "arms": {
                a: {"bt": [[v] * 7 for _ in p.JS], "quality": [[0] * 7 for _ in p.JS]}
                for a, v in zip(p.ARMS, (1.0, 2.0, 3.0, 4.0))
            },
        }

    def test_effects_and_endpoint_comparison(self):
        analysis = p.analyze(self.x, self.w)
        cell = analysis["profiles"][0]["cells"][0]
        self.assertEqual(analysis["summary"]["huber_content_numerator_fsum"], 70.0)
        self.assertEqual(analysis["summary"]["huber_content_mean_70_cells"], 1.0)
        self.assertEqual(
            analysis["summary"]["huber_content_fixed_m0_contribution"], 70.0 / 377342
        )
        self.assertEqual(cell["bt_effects"]["interaction"], 0.0)
        self.assertEqual(cell["huber_effects"]["interaction"], 0.0)
        self.assertEqual(cell["GG_minus_historical_guard"], 0.0)
        self.x["arms"]["PP"]["bt"][0][0] = 5.0
        cell = p.analyze(self.x, self.w)["profiles"][0]["cells"][0]
        self.assertEqual(cell["bt_effects"]["interaction"], 1.0)
        self.assertEqual(cell["PP_minus_historical_pilot"], 1.0)

    def test_raw_rttov_differences_and_malformed_field(self):
        raw = p.raw_differences()
        self.assertEqual(raw["TOTAL"]["GP_minus_GG"]["nonzero"], 4)
        self.assertEqual(raw["TOTAL"]["PP_minus_PG"]["nonzero"], 2)
        self.assertEqual(raw["BT"]["GP_minus_GG"]["nonzero"], 1)
        self.assertEqual(raw["BT"]["PP_minus_PG"]["nonzero"], 0)
        with self.assertRaises(ValueError):
            p.raw_field(b"RADIANCE%BT = (1 2)", "BT")

    def test_quality_and_mapping_rejected(self):
        for field in ("quality", "mapping"):
            x = copy.deepcopy(self.x)
            if field == "quality":
                x["arms"]["GG"]["quality"][0][0] = 1
            else:
                x["mapping"][0]["guard_ordinal"] += 1
            with self.assertRaises(ValueError):
                p.analyze(x, self.w)

    def test_source_manifest_rejects_tampered_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = json.loads((p.HERE / "source_manifest.json").read_bytes())
            shutil.copyfile(
                p.HERE / "source_manifest.json", root / "source_manifest.json"
            )
            for name in manifest["sha256"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p.HERE / name, target)
            with mock.patch.object(p, "HERE", root):
                p.check_source_pins()
                with (root / "test_packet.py").open("ab") as f:
                    f.write(b"\n# mutated helper\n")
                with self.assertRaisesRegex(ValueError, "packet source changed"):
                    p.check_source_pins()

    def test_external_identical_export_copy_replays_in_both_modes(self):
        raw = (p.HERE / "export.json").read_bytes()
        published = (p.HERE / "analysis.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "external-export.json"
            copied.write_bytes(raw)
            for optimized in (False, True):
                command = [sys.executable]
                if optimized:
                    command.append("-O")
                command.extend((str(p.HERE / "packet.py"), "replay", str(copied)))
                result = subprocess.run(command, cwd=p.REPO, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, published)

    def test_external_changed_export_bytes_rejected_in_both_modes(self):
        original = (p.HERE / "export.json").read_bytes()
        variants = {}
        for name in ("K_calls", "manifest_sha256", "coordinate", "finite_BT"):
            changed = json.loads(original)
            if name == "K_calls":
                changed["arms"]["GG"]["receipt"]["K_calls"] = 1
            elif name == "manifest_sha256":
                changed["manifest_sha256"] = "0" * 64
            elif name == "coordinate":
                changed["arms"]["GG"]["receipt"]["coordinate"] = "native"
            else:
                changed["arms"]["GP"]["bt"][0][0] += 1.0
            variants[name] = json.dumps(changed).encode()
        variants["whitespace_only"] = original + b" "
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed-export.json"
            for name, raw in variants.items():
                path.write_bytes(raw)
                for optimized in (False, True):
                    with self.subTest(change=name, optimized=optimized):
                        command = [sys.executable]
                        if optimized:
                            command.append("-O")
                        command.extend((str(p.HERE / "packet.py"), "replay", str(path)))
                        result = subprocess.run(
                            command, cwd=p.REPO, capture_output=True
                        )
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(b"replay packet SHA differs", result.stderr)
                        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
