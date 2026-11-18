"""The captured ice slope/intercept response reaches C4 and the ice update."""

import importlib
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

verifier = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet")

module = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.ice_auxiliary_ad")


class IceAuxiliaryAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (Path(module.ROOT) / "selected_packet.json").read_bytes()
        cls.cells = module.verified_cells(cls.raw, verifier.PACKET_SHA256)

    def test_two_native_cells(self):
        for level in (20, 22):
            with self.subTest(level=level):
                result = module.diagnose(level, self.cells[level])
                self.assertIn("INCONCLUSIVE", result["status"])
                for direction in result["directions"].values():
                    self.assertAlmostEqual(
                        direction["extra_qi_from_auxiliary"],
                        direction["independent_extra_qi"], delta=2e-15)
                    self.assertLess(abs(direction["vjp_dual_error"]), 2e-11)
                    self.assertLess(
                        abs(direction["fd_minus_actual_jvp"][0]), 2e-14)
                    self.assertLess(
                        abs(direction["fd_minus_actual_jvp"][1]), 2e-7)
        result = module.diagnose(22, self.cells[22])
        self.assertAlmostEqual(
            result["directions"]["relative_qi"]["extra_qi_from_auxiliary"],
            7.237213036e-8, delta=2e-15)
        self.assertAlmostEqual(
            result["directions"]["relative_ni"]["extra_qi_from_auxiliary"],
            1.447442543e-7, delta=2e-15)

    def test_corrupt_intercept_cannot_become_baseline(self):
        source = Path(module.ROOT) / "selected_packet.json"
        packet = json.loads(source.read_bytes())
        row = next(r for r in packet["selected_rows"] if
                   r["k_zero"] == "22" and r["stage"] == "c4_in"
                   and r["field"] == "n0i")
        row["raw_hex"] = format(int(row["raw_hex"], 16) ^ 1, "x")
        rows = module.rows_for(packet, 22)
        with self.assertRaisesRegex(ValueError, "captured ice intercept raw bits"):
            module.diagnose(22, rows)

    def test_cli_rejects_shared_input_mutations(self):
        for field, value in (("pre.supcol", 1.0),
                             ("forcing.dend", 0.9825252294540405)):
            packet = json.loads(self.raw)
            row = next(r for r in packet["selected_rows"] if
                       r["k_zero"] == "20" and r["stage"] == "c5_in"
                       and r["field"] == field)
            row["raw_hex"] = format(int.from_bytes(
                struct.pack("<d", value), "little"), "x")
            altered = json.dumps(packet, sort_keys=True).encode()
            new_pin = hashlib.sha256(altered).hexdigest()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "altered.json"
                path.write_bytes(altered)
                process = subprocess.run(
                    [sys.executable, "-m", module.__name__, str(path),
                     "--sha256", new_pin], cwd=module.ROOT.parents[2],
                    capture_output=True, text=True, check=False)
            with self.subTest(field=field):
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("INVALID: fixed independent packet digest", process.stderr)

            selection = {k: packet[k] for k in
                         ("selected_rows", "capture_files", "capture_metadata")}
            selected_pin = hashlib.sha256(json.dumps(
                selection, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with (patch.object(verifier, "PACKET_SHA256", new_pin),
                  patch.object(verifier, "SELECTED_CAPTURE_SHA256", selected_pin)):
                with self.assertRaisesRegex(ValueError, "C3/C5 shared input " + field):
                    module.verified_cells(altered, new_pin)

    def test_verification_receives_original_bytes_once(self):
        with patch.object(verifier, "verify", wraps=verifier.verify) as checked:
            cells = module.verified_cells(self.raw, verifier.PACKET_SHA256)
        checked.assert_called_once_with(self.raw, verifier.PACKET_SHA256)
        self.assertEqual(set(cells), {20, 22})
        self.assertEqual(cells[20][("c3_in", "pre.supcol")]["k_zero"], "20")
        self.assertEqual(cells[22][("c3_in", "pre.supcol")]["k_zero"], "22")

    def test_cli_half_saturation_gap_for_both_rate_signs_and_endpoints(self):
        packet_path = Path(module.ROOT) / "selected_packet.json"
        process = subprocess.run(
            [sys.executable, "-m", module.__name__, str(packet_path),
             "--sha256", verifier.PACKET_SHA256],
            cwd=module.ROOT.parents[2], capture_output=True, text=True, check=True)
        report = json.loads(process.stdout)
        for level, sign in ((20, -1), (22, 1)):
            rows = self.cells[level]
            sup = module.read(rows, "c3_in", "pre.supsat")
            dt = module.read(rows, "c5_in", "dtcld")
            half = 0.5 * (sup / dt)  # same source order as the C4 candidate
            entry = report[str(level)]
            audits = [entry["baseline_c4_audit"]]
            for direction in entry["directions"].values():
                audits += [direction["plus_c4_audit"],
                           direction["minus_c4_audit"]]
            self.assertEqual(len(audits), 5)
            for audit in audits:
                with self.subTest(level=level, raw=audit["raw_pidep"]):
                    self.assertEqual((audit["raw_pidep"] > 0) -
                                     (audit["raw_pidep"] < 0), sign)
                    self.assertEqual(audit["half_cap_minus_raw"],
                                     half - audit["raw_pidep"])
            if level == 20:
                q = module.read(rows, "c4_in", "state.qi")
                available_ice_gap = -q / dt - audits[0]["raw_pidep"]
                self.assertNotEqual(audits[0]["half_cap_minus_raw"],
                                    available_ice_gap)
                self.assertAlmostEqual(audits[0]["half_cap_minus_raw"],
                                       -4.144285872186099e-7, delta=1e-20)
            else:
                self.assertAlmostEqual(audits[0]["half_cap_minus_raw"],
                                       9.864846405808e-7, delta=1e-20)

    def test_zero_raw_and_inactive_ice_audit_contract(self):
        producer = {
            "signature": {"c4_phases": [("ice", True, False, 0, False)]},
            "margins": {"c4_ice_raw_sign": 0.0, "c4_ice_cap_1_0": 2.0},
            "selected_rates": {"pidep": 0.0},
        }
        self.assertEqual(module.ice_c4_audit({"producers": producer})[
            "half_cap_minus_raw"], 2.0)
        producer["signature"]["c4_phases"] = [("ice", False, False, None, False)]
        producer["margins"].clear()
        with self.assertRaisesRegex(ValueError, "C4 ice branch not entered"):
            module.ice_c4_audit({"producers": producer})


if __name__ == "__main__":
    unittest.main()
