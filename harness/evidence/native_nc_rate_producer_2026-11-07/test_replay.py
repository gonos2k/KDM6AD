"""Mutation checks for selected NC rate producers and limiter handoffs."""

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
spec = importlib.util.spec_from_file_location("native_nc_rates_replay", HERE / "replay.py")
if spec is None or spec.loader is None:
    raise RuntimeError("NC rates replay loader")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def changed(label: str, stage: str, field: str, *, number: float | None = None,
            word_increment: int = 0, raw_hex: str | None = None) -> tuple[str, bytes, str]:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if not line.startswith("#")
               and len(line.rstrip("\n").split(",")) == 11
               and line.rstrip("\n").split(",")[4] == "23"
               and line.rstrip("\n").split(",")[7:9] == [stage, field]]
    if len(matches) != 1:
        raise AssertionError("one native-16 capture row expected")
    i = matches[0]
    parts = lines[i].rstrip("\n").split(",")
    if number is not None:
        parts[10] = format(int.from_bytes(struct.pack(">d", number), "big"), "x")
    elif word_increment:
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
        self.assertIn("verified 3 NC-rate producer calls x 39 levels", proc.stdout)

    def test_rehashed_naacw_input_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "naacw_producer", "ngacw", number=400.0)
        with self.assertRaisesRegex(ValueError, "naacw_producer.naacw"):
            module.replay(capture_override=override)

    def test_rehashed_nracw_mode_input_rejected(self) -> None:
        override = changed("qg_bg17_rel_1e-03_plus", "nracw_producer", "rslope3_r",
                           number=1.0e-10)
        with self.assertRaisesRegex(ValueError, "nracw_producer.nracw"):
            module.replay(capture_override=override)

    def test_rehashed_limiter_source_rejected(self) -> None:
        override = changed("baseline", "nc_limit_warm", "source_sum", word_increment=1)
        with self.assertRaisesRegex(ValueError, "nc_limit_warm.source_sum"):
            module.replay(capture_override=override)

    def test_rehashed_limiter_gate_rejected(self) -> None:
        override = changed("baseline", "nc_limit_cold", "gate", raw_hex="1")
        with self.assertRaisesRegex(ValueError, "limiter gates bound to NC budget cold mask"):
            module.replay(capture_override=override)

    def test_rehashed_both_limiter_gates_flipped_rejected(self) -> None:
        label, cold_changed, _ = changed("baseline", "nc_limit_cold", "gate", raw_hex="1")
        lines = cold_changed.decode().splitlines(keepends=True)
        matches = [i for i, line in enumerate(lines) if not line.startswith("#")
                   and len(line.rstrip("\n").split(",")) == 11
                   and line.rstrip("\n").split(",")[4] == "23"
                   and line.rstrip("\n").split(",")[7:9] == ["nc_limit_warm", "gate"]]
        self.assertEqual(len(matches), 1)
        i = matches[0]
        parts = lines[i].rstrip("\n").split(",")
        parts[10] = "0"
        lines[i] = ",".join(parts) + "\n"
        raw = "".join(lines).encode()
        with self.assertRaisesRegex(ValueError, "limiter gates bound to NC budget cold mask"):
            module.replay(capture_override=(label, raw, hashlib.sha256(raw).hexdigest()))

    def test_rehashed_rate_handoff_rejected(self) -> None:
        override = changed("baseline", "nc_limit_warm", "naacw_after", word_increment=1)
        with self.assertRaisesRegex(ValueError, "nc_limit_warm.naacw_after"):
            module.replay(capture_override=override)

    def test_rehashed_false_step_claim(self) -> None:
        receipt = json.loads((HERE / "raw/run_receipt.json").read_text())
        receipt["cases"][1]["nominal_step"] = 0.0
        raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "ordered signed endpoint plan"):
            module.replay(receipt_override=(raw, hashlib.sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
