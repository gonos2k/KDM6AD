"""Mutation checks for C2c snow/graupel number-rate replay."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("native_c2c_number_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("C2c number replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def changed(label: str, field: str, *, number: float | None = None,
            dtype: str | None = None) -> tuple[str, bytes, str]:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if not line.startswith("#")
               and len(line.rstrip("\n").split(",")) == 11
               and line.rstrip("\n").split(",")[4] == "23"
               and line.rstrip("\n").split(",")[7:9] == ["c2c_number_inputs", field]]
    if len(matches) != 1:
        raise AssertionError("one native-16 C2c input expected")
    i = matches[0]
    parts = lines[i].rstrip("\n").split(",")
    if number is not None:
        parts[10] = format(int.from_bytes(struct.pack(">d", number), "big"), "x")
    if dtype is not None:
        parts[9] = dtype
    lines[i] = ",".join(parts) + "\n"
    raw = "".join(lines).encode()
    return label, raw, hashlib.sha256(raw).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_and_saved_result(self) -> None:
        self.assertEqual(module.replay(), json.loads((HERE / "results.json").read_text()))

    def test_cli(self) -> None:
        proc = subprocess.run([sys.executable, str(HERE / "replay.py")],
                              capture_output=True, text=True, check=True)
        self.assertIn("verified 3 native C2c number-rate calls x 39 levels", proc.stdout)

    def test_rehashed_snow_prefix_operand_rejected(self) -> None:
        override = changed("baseline", "pi_f32", number=3.0)
        with self.assertRaisesRegex(ValueError, "fixed C2c parameter: pi_f32"):
            module.replay(capture_override=override)

    def test_rehashed_graupel_slope_coefficient_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "g3pbg", number=4.0)
        with self.assertRaisesRegex(ValueError, "ngacw producer"):
            module.replay(capture_override=override)

    def test_rehashed_snow_gate_threshold_rejected(self) -> None:
        override = changed("baseline", "qcrmin", number=0.001)
        with self.assertRaisesRegex(ValueError, "fixed C2c parameter: qcrmin"):
            module.replay(capture_override=override)

    def test_rehashed_inactive_threshold_change_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "qcrmin", number=1.0e-12)
        with self.assertRaisesRegex(ValueError, "fixed C2c parameter: qcrmin"):
            module.replay(capture_override=override)

    def test_rehashed_wilt_denominator_rejected(self) -> None:
        override = changed("baseline", "qc", number=0.001)
        with self.assertRaisesRegex(ValueError, "nsacw producer"):
            module.replay(capture_override=override)

    def test_rehashed_dtype_rejected(self) -> None:
        override = changed("baseline", "den", dtype="f32")
        with self.assertRaisesRegex(ValueError, "C2c input row schema"):
            module.replay(capture_override=override)

    def test_rehashed_false_step_claim(self) -> None:
        receipt = json.loads((HERE / "raw/run_receipt.json").read_text())
        receipt["cases"][1]["nominal_step"] = 0.0
        raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "ordered signed endpoint plan"):
            module.replay(receipt_override=(raw, hashlib.sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
