"""Regression checks for the captured applied NC/NCCN ledger."""

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
spec = importlib.util.spec_from_file_location("native_nc_nccn_applied_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("native NC/NCCN replay loader")
replay_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_module)


def changed_capture(label: str, stage: str, field: str, k: int, changed: str) -> tuple[str, bytes, str]:
    cap = gzip.decompress((HERE / "raw/cases" / (label + ".csv.gz")).read_bytes())
    lines = cap.decode().splitlines(keepends=True)
    match = [i for i, line in enumerate(lines) if not line.startswith("#") and
             len(line.split(",")) == 11 and line.split(",")[4] == str(k) and
             line.split(",")[7:9] == [stage, field]]
    if len(match) != 1:
        raise AssertionError("one capture field expected")
    i = match[0]
    parts = lines[i].rstrip("\n").split(",")
    parts[10] = changed
    lines[i] = ",".join(parts) + "\n"
    altered = "".join(lines).encode()
    return label, altered, hashlib.sha256(altered).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_original_result(self) -> None:
        self.assertEqual(replay_module.replay(), json.loads((HERE / "results.json").read_text()))

    def test_cli(self) -> None:
        p = subprocess.run([sys.executable, str(HERE / "replay.py")],
                           capture_output=True, text=True, check=True)
        self.assertIn("verified 13 NC/NCCN paired f64 calls x 39 levels", p.stdout)

    def test_rehashed_activation_store_mutation(self) -> None:
        altered = changed_capture("qv16_rel_1e-03_minus", "fd_satadj_inner",
                                  "nccn_after_activation", 23, "417bdada164299ff")
        with self.assertRaisesRegex(ValueError, "NCCN activation store"):
            replay_module.replay(capture_override=altered)

    def test_rehashed_floor_flag_mutation(self) -> None:
        altered = changed_capture("baseline", "fd_satadj_inner", "nccn_floor_active", 23, "0")
        with self.assertRaisesRegex(ValueError, "nccn_floor_active"):
            replay_module.replay(capture_override=altered)

    def test_rehashed_receipt_claim_mutation(self) -> None:
        receipt = json.loads((HERE / "raw/run_receipt.json").read_text())
        receipt["cases"][1]["direction"] = "baseline"
        receipt["cases"][1]["nominal_step"] = 0.0
        raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "complete ordered signed endpoint plan"):
            replay_module.replay(receipt_override=(raw, hashlib.sha256(raw).hexdigest()))

    def test_rehashed_dtype_mutation(self) -> None:
        label = "baseline"
        cap = gzip.decompress((HERE / "raw/cases" / (label + ".csv.gz")).read_bytes())
        old = b",23,1,39,fd_satadj_inner,nccn_final,f64,"
        self.assertEqual(cap.count(old), 1)
        altered = cap.replace(old, b",23,1,39,fd_satadj_inner,nccn_final,f32,")
        with self.assertRaisesRegex(ValueError, "f64 capture dtype"):
            replay_module.replay(capture_override=(label, altered, hashlib.sha256(altered).hexdigest()))


if __name__ == "__main__":
    unittest.main()
