"""Mutation checks for the post-freeze pre2 producer-to-C2c path."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_pre2_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("pre2 replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def changed(label: str, stage: str, field: str, *, word_increment: int = 0,
            raw_hex: str | None = None, k_zero: int = 23) -> tuple[str, bytes, str]:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if not line.startswith("#")
               and len(line.rstrip("\n").split(",")) == 11
               and line.rstrip("\n").split(",")[4] == str(k_zero)
               and line.rstrip("\n").split(",")[7:9] == [stage, field]]
    if len(matches) != 1:
        raise AssertionError("one native-16 row expected")
    i = matches[0]
    parts = lines[i].rstrip("\n").split(",")
    if word_increment:
        parts[10] = format(int(parts[10], 16) + word_increment, "x")
    elif raw_hex is not None:
        parts[10] = raw_hex
    else:
        raise ValueError("mutation value required")
    lines[i] = ",".join(parts) + "\n"
    raw = "".join(lines).encode()
    return label, raw, hashlib.sha256(raw).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_and_saved_result(self) -> None:
        self.assertEqual(module.replay(), json.loads((HERE / "results.json").read_text()))

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified 3 postfreeze pre2 producer calls x 39 levels", proc.stdout)

    def test_rehashed_d234_handoff_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "d234_boundary", "qg_after",
                           word_increment=1)
        with self.assertRaisesRegex(ValueError, "D2-D4 to pre2 input"):
            module.replay(capture_override=override)

    def test_rehashed_d234_entry_qg_rejected_outside_selected_layer(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "d234_boundary", "qg_before",
                           raw_hex="3ff0000000000000", k_zero=0)
        with self.assertRaisesRegex(ValueError, "postmelt QG to D2-D4 entry"):
            module.replay(capture_override=override)

    def test_rehashed_progb_gate_rejected(self) -> None:
        override = changed("baseline", "pre2_producer", "progb_active", raw_hex="0")
        with self.assertRaisesRegex(ValueError, "postfreeze ProgB active gate"):
            module.replay(capture_override=override)

    def test_rehashed_slope_handoff_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_minus", "pre2_producer", "rslope3_g",
                           word_increment=1)
        with self.assertRaisesRegex(ValueError, "pre2 to C2c operand"):
            module.replay(capture_override=override)

    def test_rehashed_pidn0g_one_ulp_rounding_limit(self) -> None:
        label = "qg_bg17_rel_1e-03_plus"
        altered = changed(label, "pre2_producer", "pidn0g", word_increment=1)
        result = module.replay(capture_override=altered)
        original = json.loads((HERE / "results.json").read_text())
        self.assertNotEqual(result["native16"][label]["pre2"]["pidn0g"],
                            original["native16"][label]["pre2"]["pidn0g"])

    def test_rehashed_false_endpoint_claim_rejected(self) -> None:
        receipt = json.loads((HERE / "raw/run_receipt.json").read_text())
        receipt["cases"][1]["nominal_step"] = 0.0
        raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "ordered signed endpoint plan"):
            module.replay(receipt_override=(raw, hashlib.sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
