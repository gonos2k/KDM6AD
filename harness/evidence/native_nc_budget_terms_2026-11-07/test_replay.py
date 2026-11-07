"""Mutation checks for the applied NC state-update terms."""

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
spec = importlib.util.spec_from_file_location("native_nc_budget_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("NC budget replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def changed(label: str, field: str, *, word_increment: int = 0,
            dtype: str | None = None) -> tuple[str, bytes, str]:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    match = [i for i, line in enumerate(lines) if not line.startswith("#")
             and len(line.rstrip("\n").split(",")) == 11
             and line.rstrip("\n").split(",")[4] == "23"
             and line.rstrip("\n").split(",")[7:9] == ["nc_budget", field]]
    if len(match) != 1:
        raise AssertionError("one native-16 budget term expected")
    i = match[0]
    parts = lines[i].rstrip("\n").split(",")
    if word_increment:
        parts[10] = format(int(parts[10], 16) + word_increment, "x")
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
        self.assertIn("verified 3 NC-budget paired calls x 39 levels", proc.stdout)

    def test_rehashed_rate_term_mutation(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "naacw", word_increment=1)
        with self.assertRaisesRegex(ValueError, "independent applied naacw handoff"):
            module.replay(capture_override=override)

    def test_rehashed_compensating_rates_rejected_by_producer_handoff(self) -> None:
        label = "qg_bg17_rel_1e-03_plus"
        raw = gzip.decompress((HERE / "raw/cases" / (label + ".csv.gz")).read_bytes())
        lines = raw.decode().splitlines(keepends=True)
        replacements = {"nraut": 1.2951605219140427,
                        "nccol": 3036.4650046281895}
        found = set()
        for i, line in enumerate(lines):
            parts = line.rstrip("\n").split(",")
            if len(parts) == 11 and parts[4] == "23" and parts[7] == "nc_budget" \
                    and parts[8] in replacements:
                found.add(parts[8])
                parts[10] = format(int.from_bytes(struct.pack(">d", replacements[parts[8]]), "big"), "x")
                lines[i] = ",".join(parts) + "\n"
        self.assertEqual(found, set(replacements))
        altered = "".join(lines).encode()
        with self.assertRaisesRegex(ValueError, "independent applied nraut handoff"):
            module.replay(capture_override=(label, altered, hashlib.sha256(altered).hexdigest()))

    def test_rehashed_stored_nc_mutation(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "nc_clamped", word_increment=1)
        with self.assertRaisesRegex(ValueError, "nc_clamped"):
            module.replay(capture_override=override)

    def test_rehashed_dtype_mutation(self) -> None:
        override = changed("baseline", "nraut", dtype="f32")
        with self.assertRaisesRegex(ValueError, "NC budget row schema"):
            module.replay(capture_override=override)

    def test_rehashed_false_step_claim(self) -> None:
        receipt = json.loads((HERE / "raw/run_receipt.json").read_text())
        receipt["cases"][1]["nominal_step"] = 0.0
        raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "ordered signed endpoint plan"):
            module.replay(receipt_override=(raw, hashlib.sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
