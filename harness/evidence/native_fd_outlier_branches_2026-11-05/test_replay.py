"""Regression checks for retained same-column FD branch traces."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import unittest

import replay


HERE = Path(__file__).resolve().parent


def changed_capture(
    label: str,
    *,
    stage: str,
    field: str,
    level: int,
    new_dtype: str | None = None,
    new_word: str | None = None,
    word_delta: int = 0,
    new_one_step_call: str | None = None,
    new_substep: str | None = None,
) -> bytes:
    path = HERE / "raw/cases" / (label + ".csv.gz")
    lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
    changed = 0
    for i, line in enumerate(lines):
        parts = line.split(",")
        if len(parts) == 11 and parts[4] == str(level) and parts[7:9] == [stage, field]:
            if new_one_step_call is not None:
                parts[0] = new_one_step_call
            if new_substep is not None:
                parts[2] = new_substep
            if new_dtype is not None:
                parts[9] = new_dtype
            if new_word is not None:
                parts[10] = new_word
            if word_delta:
                parts[10] = format(int(parts[10], 16) + word_delta, "x")
            lines[i] = ",".join(parts)
            changed += 1
    if changed != 1:
        raise ValueError(
            "expected one captured row: " + label + "/" + stage + "/" + field
        )
    return gzip.compress(("\n".join(lines) + "\n").encode("ascii"), mtime=0)


class NativeFDOutlierReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_branch_localization_and_parent_value_identity(self) -> None:
        result = self.result
        self.assertEqual(result["cases"], 11)
        self.assertEqual(result["parent_rows_preserved_per_case"], 11271)
        self.assertEqual(result["new_stage_fields_per_case"], 56)
        self.assertEqual(result["same_value_outputs_as_parent"], 5148)
        self.assertLess(result["qv_activation"]["sw_percent"]["qv_1e-03_minus"], 0.48)
        self.assertGreater(
            result["qv_activation"]["sw_percent"]["qv_1e-04_minus"], 0.48
        )
        self.assertLess(
            result["qg_entry_progb"]["uncapped_qg_over_brs"]["qg_1e-05_minus"], 900
        )
        self.assertGreater(
            result["qg_entry_progb"]["uncapped_qg_over_brs"]["qg_1e-06_minus"], 900
        )
        self.assertGreater(
            result["qv_activation"]["small_step_fd_error_in_output_ulps"], 1
        )
        self.assertLess(
            result["qv_activation"]["small_step_fd_error_in_output_ulps"], 2
        )

    def test_rehashed_qv_fraction_mutation_is_rejected(self) -> None:
        label = "qv_1e-03_minus"
        raw = changed_capture(
            label,
            stage="fd_satadj_inner",
            field="activated_fraction",
            level=23,
            new_word="3ff0000000000000",
        )
        with self.assertRaisesRegex(ValueError, "activation fraction producer"):
            replay.replay(
                capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_correlated_sw_and_fraction_mutation_is_rejected(self) -> None:
        label = "qv_1e-03_minus"
        path = HERE / "raw/cases" / (label + ".csv.gz")
        lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
        changed = set()
        forged = {
            "sw_percent": 0.4,
            "activated_fraction": (0.4 / 0.48) ** 0.6,
        }
        for i, line in enumerate(lines):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "23"
                and parts[7] == "fd_satadj_inner"
                and parts[8] in forged
            ):
                parts[10] = struct.pack(">d", forged[parts[8]]).hex()
                lines[i] = ",".join(parts)
                changed.add(parts[8])
        self.assertEqual(changed, set(forged))
        raw = gzip.compress(("\n".join(lines) + "\n").encode("ascii"), mtime=0)
        with self.assertRaisesRegex(ValueError, "sw producer operands"):
            replay.replay(
                capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_qg_entry_brs_mutation_is_rejected(self) -> None:
        label = "qg_1e-05_minus"
        raw = changed_capture(
            label, stage="fd_main", field="brs_before", level=15, word_delta=1
        )
        with self.assertRaisesRegex(ValueError, "entry ProgB density/BRS branch"):
            replay.replay(
                capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_parent_row_mutation_is_rejected(self) -> None:
        label = "qv_1e-03_minus"
        raw = changed_capture(
            label, stage="runtime_full_exit", field="nc", level=23, word_delta=1
        )
        with self.assertRaisesRegex(ValueError, "parent 11271 rows unchanged"):
            replay.replay(
                capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_trace_call_identity_mutations_are_rejected(self) -> None:
        cases = (
            (
                "qv_1e-03_minus",
                "fd_satadj_inner",
                "sw_percent",
                23,
                {"new_one_step_call": "999"},
            ),
            (
                "qv_1e-03_minus",
                "fd_satadj_inner",
                "sw_percent",
                23,
                {"new_substep": "1"},
            ),
            ("qg_1e-05_minus", "fd_main", "qg_before", 15, {"new_one_step_call": "1"}),
        )
        for label, stage, field, level, changed in cases:
            with self.subTest(label=label, changed=changed):
                raw = changed_capture(
                    label,
                    stage=stage,
                    field=field,
                    level=level,
                    **changed,
                )
                with self.assertRaisesRegex(ValueError, "trace dtype/call identity"):
                    replay.replay(
                        capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
                    )

    def test_cli_matches_saved_result(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(proc.stdout), self.result)
        saved = json.loads((HERE / "results.json").read_text())
        self.assertEqual(saved, self.result)


if __name__ == "__main__":
    unittest.main()
