"""Regression checks for prespecified native NC16 expanded FD directions."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import replay


HERE = Path(__file__).resolve().parent


def changed_npz(label: str, field: str, index: tuple[int, int], delta: float) -> bytes:
    with np.load(HERE / "raw/cases" / (label + ".npz"), allow_pickle=False) as source:
        arrays = {name: np.array(source[name], copy=True) for name in source.files}
    arrays[field][index] += delta
    out = io.BytesIO()
    np.savez_compressed(out, **arrays)
    return out.getvalue()


def changed_capture(label: str, stage: str, field: str, level: int) -> bytes:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
    changed = 0
    for i, line in enumerate(lines):
        parts = line.split(",")
        if len(parts) == 11 and parts[4] == str(level) and parts[7:9] == [stage, field]:
            parts[10] = format(int(parts[10], 16) + 1, "x")
            lines[i] = ",".join(parts)
            changed += 1
    if changed != 1:
        raise ValueError("expected one captured row")
    return gzip.compress(("\n".join(lines) + "\n").encode("ascii"), mtime=0)


class NC16ExpandedFDReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_prespecified_windows_and_coupled_control(self) -> None:
        result = self.result
        self.assertEqual(result["calls"], 37)
        self.assertEqual(result["levels"], 39)
        self.assertEqual(len(result["comparisons"]), 18)
        self.assertEqual(result["accepted_windows"], 15)
        self.assertEqual(result["captured_cap_crossings"], 3)
        data = {(x["direction"], x["h"]): x for x in result["comparisons"]}
        for key in replay.CROSSING:
            self.assertTrue(data[key]["captured_cap_crossing"])
            self.assertGreater(data[key]["normalized_error"], 1e-3)
            self.assertEqual(data[key]["changed_side"], [replay.CROSS_SIDE[key]])
            self.assertTrue(
                data[key]["one_sided"][replay.CROSS_SIDE[key]]["captured_cap_changed"]
            )
        for h in replay.PLAN["qg_bg17_rel"]:
            row = data["qg_bg17_rel", h]
            self.assertFalse(row["captured_cap_crossing"])
            self.assertEqual(row["changed_side"], [])
            self.assertLess(row["normalized_error"], 5e-6)
        self.assertTrue(
            all(0 <= x["midpoint_input_ulps"] <= 0.5 for x in data.values())
        )
        self.assertEqual(data["qg_bg17_rel", 1e-3]["midpoint_input_ulps"], 0.5)
        self.assertEqual(data["qg_bg17_rel", 1e-5]["midpoint_input_ulps"], 0.5)
        self.assertTrue(
            all(
                x["captured_cap_crossing"] or x["normalized_error"] < 5e-6
                for x in data.values()
            )
        )

    def test_rehashed_output_array_mutation_is_rejected(self) -> None:
        label = "qc16_rel_1e-04_plus"
        raw = changed_npz(label, "output", (8, 15), 1000.0)
        with self.assertRaisesRegex(ValueError, "captured endpoint output"):
            replay.replay(
                case_npz_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_progb_capture_mutation_is_rejected(self) -> None:
        label = "qg17_rel_1e-03_plus"
        raw = changed_capture(label, "fd_main", "brs_before", 16)
        with self.assertRaisesRegex(ValueError, "entry ProgB producer"):
            replay.replay(
                case_capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_activation_capture_mutation_is_rejected(self) -> None:
        label = "th16_abs_1e-02_plus"
        raw = changed_capture(label, "fd_satadj_inner", "sw_percent", 23)
        with self.assertRaisesRegex(ValueError, "activation producer and cap"):
            replay.replay(
                case_capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_unchecked_intermediate_override_is_explicitly_out_of_scope(self) -> None:
        label = "qc16_rel_1e-04_plus"
        raw = changed_capture(label, "fd_main", "brs_before", 15)
        result = replay.replay(
            case_capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
        )
        self.assertEqual(result, self.result)

    def test_cli_and_saved_diagnostics(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            text=True,
            capture_output=True,
            check=True,
        )
        cli = json.loads(proc.stdout)
        self.assertEqual(cli, self.result)
        saved = json.loads((HERE / "results.json").read_text())
        self.assertEqual(saved, self.result)


if __name__ == "__main__":
    unittest.main()
