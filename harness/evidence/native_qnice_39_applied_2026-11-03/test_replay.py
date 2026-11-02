"""Regression checks for the pinned native 39-level NI replay."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

import replay


HERE = Path(__file__).resolve().parent
HOST = (HERE / "raw/host_qnice_pre_call.csv").read_bytes()
NATIVE = (HERE / "raw/native_qnice_applied_30339_runtime2.csv").read_bytes()


class ReplayTest(unittest.TestCase):
    def test_official_replay_and_selected_applied_amounts(self):
        result = replay.replay()
        self.assertEqual(
            result["schema"], "kdm6.native_qnice_39_applied_public_replay.v1"
        )
        self.assertTrue(result["sedimentation_state_and_fall_raw_words_equal"])
        self.assertTrue(result["native_same_call_scalar_join"])
        self.assertTrue(result["attested_off_on_endpoint_hashes_equal"])
        self.assertEqual(result["levels"], 39)
        self.assertEqual(result["departure_cap_active_levels"], 0)
        self.assertEqual(
            result["pre_c3_ni_changes"]["snap_a"]["changed_native_levels_1based"],
            [25, 20, 19, 18, 17, 16],
        )
        self.assertEqual(
            result["selected_levels"]["21"]["applied_in_ni"], 40.591479729160824
        )
        self.assertEqual(
            result["selected_levels"]["23"]["applied_out_ni"], 172.77053588541446
        )
        self.assertFalse(result["physical_conservation_certified"])
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")

    def test_cli(self):
        completed = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_39_APPLIED_REPLAY_PASSED", completed.stdout)

    def test_rehashed_numeric_change_fails_source_order_replay(self):
        lines = NATIVE.decode().splitlines()
        for index, line in enumerate(lines):
            cells = line.split(",")
            if (
                len(cells) == 11
                and cells[4:6] == ["18", "32248"]
                and cells[7:9] == [replay.STAGE, "falk_stored_ni"]
            ):
                cells[10] = format(int(cells[10], 16) ^ 1, "x")
                lines[index] = ",".join(cells)
                break
        else:
            self.fail("selected native row absent")
        mutated = ("\n".join(lines) + "\n").encode()
        replay.load_native(mutated)  # exact shape/identity remains valid
        with self.assertRaisesRegex(ValueError, "falk stored word"):
            replay.analyze(HOST, mutated)

    def test_rehashed_mstep_and_geometry_contradictions_fail(self):
        for field, replacement, message in (
            ("mstep", replay.word(2.0), "timestep/gate/normalization"),
            ("dend_safe", replay.word(1.0), "inactive density/depth floors"),
        ):
            with self.subTest(field=field):
                lines = NATIVE.decode().splitlines()
                for index, line in enumerate(lines):
                    cells = line.split(",")
                    if (
                        len(cells) == 11
                        and cells[4] == "0"
                        and cells[7:9] == [replay.STAGE, field]
                    ):
                        cells[10] = replacement
                        lines[index] = ",".join(cells)
                        break
                else:
                    self.fail("selected native field absent")
                mutated = ("\n".join(lines) + "\n").encode()
                replay.load_native(mutated)
                with self.assertRaisesRegex(ValueError, message):
                    replay.analyze(HOST, mutated)

    def test_wrong_call_and_reordered_rows_fail(self):
        wrong = NATIVE.replace(b"2,2,0,22617,", b"1,2,0,22617,", 1)
        with self.assertRaisesRegex(ValueError, "native call/tile identity"):
            replay.load_native(wrong)
        lines = NATIVE.decode().splitlines()
        lines[5], lines[6] = lines[6], lines[5]
        with self.assertRaisesRegex(ValueError, "native row order signature"):
            replay.load_native(("\n".join(lines) + "\n").encode())

    def test_missing_row_and_host_metadata_fail(self):
        lines = NATIVE.decode().splitlines()
        lines.pop(5)
        lines[-1] = "# native_rows=2768,status=complete"
        with self.assertRaisesRegex(ValueError, "native header/footer"):
            replay.load_native(("\n".join(lines) + "\n").encode())
        wrong_host = HOST.replace(b" 2 233 143 281 ", b" 2 233 142 281 ", 1)
        with self.assertRaisesRegex(ValueError, "host trace schema/footer"):
            replay.load_host(wrong_host)

    def test_rehashed_host_number_and_receipt_mutation_fail(self):
        lines = HOST.decode().splitlines()
        cells = lines[23].split()  # native k=21
        self.assertEqual(cells[7], "21")
        cells[12] = format(int(cells[12], 16) ^ 1, "08X")
        lines[23] = " ".join(cells)
        with self.assertRaisesRegex(ValueError, "host-to-runtime f32 widening"):
            replay.analyze(("\n".join(lines) + "\n").encode(), NATIVE)
        data = replay.pinned_inputs()
        mutant = json.loads(data["raw/off_run_result.json"])
        mutant["endpoint_sha256"] = "0" * 64
        data["raw/off_run_result.json"] = json.dumps(mutant).encode()
        with self.assertRaisesRegex(ValueError, "same-build off/on receipt identity"):
            replay.verify_attestations(data)


if __name__ == "__main__":
    unittest.main()
