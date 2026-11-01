"""Authentication checks; native packet mutation tests require final packet."""

import importlib
import hashlib
import json
import unittest
from unittest.mock import patch
verifier = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.verify_packet")


class PacketPinTests(unittest.TestCase):
    def test_rehashed_mutations_rejected_by_fixed_pin(self):
        packet = {
            "selected_rows": [
                {"stage": "c5_out", "field": "agg.psaut", "raw_hex": "0"},
                {"stage": "limiter_in", "field": "working.qi", "raw_hex": "0"},
                {"stage": "limited", "field": "scaled.cold.psaut", "raw_hex": "0"},
            ],
            "capture_files": [{"identity": ["2", "2", "1", "32248", "39"]}],
        }
        raw = json.dumps(packet, sort_keys=True).encode()
        pin = hashlib.sha256(raw).hexdigest()
        for index in range(4):
            mutated = json.loads(raw)
            if index < 3:
                mutated["selected_rows"][index]["raw_hex"] = "1"
            else:
                mutated["capture_files"][0]["identity"][1] = "3"
            changed = json.dumps(mutated, sort_keys=True).encode()
            with (
                self.subTest(index=index),
                patch.object(verifier, "PACKET_SHA256", pin),
            ):
                with self.assertRaisesRegex(
                    ValueError, "fixed independent packet digest"
                ):
                    verifier.verify(changed, hashlib.sha256(changed).hexdigest())


class NativeMutationTests(unittest.TestCase):
    def test_rehashed_native_mutations_rejected(self):
        raw = (verifier.Path(__file__).parent / "selected_packet.json").read_bytes()
        json.loads(raw)
        targets = [
            ("c5_out", "agg.psaut"),
            ("limiter_in", "working.qi"),
            ("limited", "scaled.cold.psaut"),
        ]
        for stage, field in targets:
            obj = json.loads(raw)
            row = next(
                r
                for r in obj["selected_rows"]
                if r["stage"] == stage and r["field"] == field and r["k_zero"] == "22"
            )
            row["raw_hex"] = format(int(row["raw_hex"], 16) ^ 1, "x")
            changed = json.dumps(obj, sort_keys=True).encode()
            with (
                self.subTest(field=field),
                patch.object(
                    verifier, "PACKET_SHA256", hashlib.sha256(changed).hexdigest()
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "fixed selected capture digest"
                ):
                    verifier.verify(changed, hashlib.sha256(changed).hexdigest())
        obj = json.loads(raw)
        obj["capture_files"][0]["identity"][1] = "99"
        changed = json.dumps(obj, sort_keys=True).encode()
        with patch.object(
            verifier, "PACKET_SHA256", hashlib.sha256(changed).hexdigest()
        ):
            with self.assertRaisesRegex(ValueError, "fixed selected capture digest"):
                verifier.verify(changed, hashlib.sha256(changed).hexdigest())

    def test_mutations_fail_independent_replay_after_repinning(self):
        raw = (verifier.Path(__file__).parent / "selected_packet.json").read_bytes()
        for stage, field in [
            ("c5_out", "agg.psaut"),
            ("limiter_in", "working.qi"),
            ("limited", "scaled.cold.psaut"),
            ("identity", ""),
        ]:
            obj = json.loads(raw)
            if stage == "identity":
                obj["selected_rows"][0]["runtime_call"] = "99"
            else:
                row = next(
                    r
                    for r in obj["selected_rows"]
                    if r["stage"] == stage
                    and r["field"] == field
                    and r["k_zero"] == "22"
                )
                row["raw_hex"] = format(int(row["raw_hex"], 16) ^ 1, "x")
            changed = json.dumps(obj, sort_keys=True).encode()
            selection = {
                k: obj[k]
                for k in ("selected_rows", "capture_files", "capture_metadata")
            }
            selected = hashlib.sha256(
                json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            with (
                self.subTest(field=field),
                patch.object(
                    verifier, "PACKET_SHA256", hashlib.sha256(changed).hexdigest()
                ),
                patch.object(verifier, "SELECTED_CAPTURE_SHA256", selected),
            ):
                with self.assertRaises(ValueError):
                    verifier.verify(changed, hashlib.sha256(changed).hexdigest())

    def test_accepted_packet(self):
        raw = (verifier.Path(__file__).parent / "selected_packet.json").read_bytes()
        result = verifier.verify(raw, verifier.PACKET_SHA256)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(set(result["levels"]), {"20", "22"})
        self.assertTrue(
            all(item["status"] == "pass" for item in result["levels"].values())
        )


if __name__ == "__main__":
    unittest.main()
