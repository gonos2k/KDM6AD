#!/usr/bin/env python3
"""False-pass guards of compare_rate_dump.py (Codex stop-review): an
incomplete, truncated, degenerate, or stale dump must NEVER report PASS.

Runs under pytest OR directly (`python3 test_compare_rate_dump.py`).
"""
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

HARNESS = pathlib.Path(__file__).resolve().parents[1]
TOOL = HARNESS / "compare_rate_dump.py"

NF, NJ, NK, NI = 3, 4, 5, 6


def mk_data():
    rng = np.random.default_rng(7)
    return rng.normal(size=(NF, NJ, NK, NI)).astype("<f4")


def fort_bytes(D):
    out = b""
    for j in range(NJ):
        out += np.array([j + 1, 1, NI, 1, NK], dtype=">i4").tobytes()
        for f in range(NF):
            out += D[f, j].astype(">f4").tobytes()          # (nk, ni)
    return out


def cpp_bytes(D):
    B = NI * NJ
    C = np.empty((NF, B, NK), dtype=">f4")
    for f in range(NF):
        for i in range(NI):
            for j in range(NJ):
                C[f, i * NJ + j] = D[f, j, :, i]
    return np.array([B, NK], dtype=">i4").tobytes() + C.tobytes()


def run(tmp, fort, cpp, extra=()):
    fp, cp = tmp / "fort_x.bin", tmp / "cpp_x.bin"
    fp.write_bytes(fort)
    cp.write_bytes(cpp)
    p = subprocess.run([sys.executable, str(TOOL), str(fp), str(cp), *extra],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_identical_pass():
    D = mk_data()
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), cpp_bytes(D))
        assert rc == 0 and "RESULT: PASS" in out, out


def test_single_bit_flip_fails():
    D = mk_data()
    C = cpp_bytes(D)
    C = C[:20] + bytes([C[20] ^ 0x01]) + C[21:]     # flip a bit in field 0
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), C)
        assert rc == 1 and "DIVERGES" in out, out


def test_cpp_missing_field_refused():
    # a whole trailing field missing parses "cleanly" as fewer fields —
    # must be REFUSED, not silently compared as a subset
    D = mk_data()
    C = cpp_bytes(D)
    C = C[:-NI * NJ * NK * 4]
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), C)
        assert rc == 2 and "field-count mismatch" in out, out


def test_cpp_midfield_truncation_refused():
    D = mk_data()
    C = cpp_bytes(D)[:-10]
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), C)
        assert rc == 2 and "truncated" in out, out


def test_min_fields_optin_labels_subset():
    D = mk_data()
    C = cpp_bytes(D)
    C = C[:-NI * NJ * NK * 4]                       # cpp has NF-1 fields
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), C,
                      extra=(f"--min-fields", str(NF - 1)))
        assert rc == 0 and "SUBSET" in out, out


def test_degenerate_all_zero_refused():
    D = np.zeros((NF, NJ, NK, NI), dtype="<f4")
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fort_bytes(D), cpp_bytes(D))
        assert rc == 2 and "DEGENERATE" in out, out


def test_duplicate_j_record_refused():
    D = mk_data()
    fb = fort_bytes(D)
    rec = len(fb) // NJ
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), fb + fb[:rec], cpp_bytes(D))
        assert rc == 2 and ("duplicate" in out or "not contiguous" in out), out


def test_bad_header_refused():
    D = mk_data()
    fb = fort_bytes(D)
    bad = np.array([1, 9, 2, 1, NK], dtype=">i4").tobytes() + fb[20:]  # its>ite
    with tempfile.TemporaryDirectory() as d:
        rc, out = run(pathlib.Path(d), bad, cpp_bytes(D))
        assert rc == 2, out


def _selftest():
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                fails += 1
    return fails


if __name__ == "__main__":
    sys.exit(1 if _selftest() else 0)
