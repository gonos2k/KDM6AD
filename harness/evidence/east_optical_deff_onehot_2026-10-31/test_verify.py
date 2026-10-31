import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("deff_verify", Path(__file__).with_name("verify.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class NegativeChecks(unittest.TestCase):
    def test_nonzero_quality_rejected(self):
        raw = (v.P / "GG_0_plus/direct_radiance.txt").read_bytes()
        bad = re.sub(rb"(RADIANCE%QUALITY\s*=\s*\(\s*)\S+", rb"\g<1>1", raw, count=1)
        self.assertNotEqual(raw, bad)
        with self.assertRaises(ValueError):
            v.check_raw(bad)

    def test_product_wrong_value_rejected(self):
        with self.assertRaises(ValueError):
            v.check_product(2., 3., 6.1, 6.)

    def test_missing_total_rejected(self):
        raw = (v.P / "GG_0_plus/direct_radiance.txt").read_bytes().replace(b"RADIANCE%TOTAL", b"RADIANCE%OTHER")
        with self.assertRaises(ValueError):
            v.check_raw(raw)

    def test_rehashed_packet_rejects_receipt_raw_mismatch(self):
        for change in ("raw", "receipt"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                packet = Path(tmp) / "packet"
                shutil.copytree(v.P, packet)
                raw_path = packet / "GG_0_plus/direct_radiance.txt"
                receipt_path = packet / "GG_0_plus/receipt.json"
                if change == "raw":
                    raw_path.write_bytes(raw_path.read_bytes() + b"\n")
                    changed = raw_path
                else:
                    receipt = json.loads(receipt_path.read_text())
                    receipt["raw_direct_hashes"]["radiance.txt"] = "0" * 64
                    receipt_path.write_text(json.dumps(receipt))
                    changed = receipt_path
                manifest_path = packet / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["files"][str(changed.relative_to(packet))] = hashlib.sha256(changed.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest))
                digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                with patch.object(v, "P", packet), patch.object(v, "PACKET_SHA", digest):
                    with self.assertRaisesRegex(ValueError, "receipt raw radiance hash"):
                        v.main()


if __name__ == "__main__":
    unittest.main()
