"""The legacy step helper is explicitly diagnostic, not the strict gate."""
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def test_report_only_mismatch_is_labelled_and_not_a_pass(tmp_path):
    header = struct.pack(">6i", 1, 1, 1, 1, 1, 1)
    names = ("kdm6_step1_kdm6_in.bin", "kdm6_step1_kdm6_out.bin",
             "kdm6_step1_kdm6ad_in.bin", "kdm6_step1_kdm6ad_out.bin")
    for name in names:
        values = np.zeros(12, dtype=">f4")
        if name.endswith("kdm6ad_out.bin"):
            values[0] = 1.0
        (tmp_path / name).write_bytes(header + values.tobytes())
    proc = subprocess.run(
        [sys.executable, str(ROOT / "compare_step1_kdm6_vs_kdm6ad.py"),
         str(tmp_path)], capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0
    assert "REPORT-ONLY" in proc.stdout and "OUTPUT parity" in proc.stdout
    assert "  !" in proc.stdout
