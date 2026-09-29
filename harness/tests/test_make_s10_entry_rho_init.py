from __future__ import annotations

from pathlib import Path
from collections import Counter
import hashlib
import json
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_s10_entry_rho_init as entry  # noqa: E402


def test_entry_volume_initialization_is_opt_in_and_before_first_progb():
    base = entry.RHO_DECL + entry.ANCHOR + "   call ProgB_param(brs,qrs_tmp,rhox)\n"
    candidate = entry.inject_entry(base)
    assert candidate.replace(entry.ENTRY, "", 1) == base
    assert candidate.index("brs(i,k) = qrs_tmp(i,k,3)/400.") < candidate.index(
        "   call ProgB_param")
    assert "if (loop.eq.1) then" in candidate
    assert "qrs_tmp(i,k,3).gt.0. .and. brs(i,k).eq.0." in candidate


def test_selected_native_entry_rows_replay():
    path = (Path(__file__).resolve().parents[1] / "evidence" /
            "S10_entry_rho_init_en8_run1" / "S10ENTRY_selected_rows.txt")
    receipt = json.loads((path.parent / "receipt.json").read_text())
    harness_dir = Path(__file__).resolve().parents[1]
    assert receipt["candidate"]["entry_generator_sha256"] == hashlib.sha256(
        (harness_dir / "make_s10_entry_rho_init.py").read_bytes()).hexdigest()
    assert receipt["candidate"]["hybrid_generator_sha256"] == hashlib.sha256(
        (harness_dir / "make_s10_midpoint_rate_zero.py").read_bytes()).hexdigest()
    previous = json.loads((harness_dir / "evidence" /
                           "S10_midpoint_rate_zero_run2" / "receipt.json").read_text())
    comparison = receipt["between_variant_history_vs_prior_hybrid_off"]
    assert comparison["prior_hybrid_executable_sha256"] == (
        previous["source_and_build"]["linked_executable_sha256"])
    assert comparison["prior_hybrid_off_history_sha256"] == (
        previous["runs"]["logging_off"]["history_sha256"])
    ledger = receipt["entry_initialization_ledger"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ledger["raw_rows_sha256"]
    assert ledger["qcrmin_REAL4_word"] == struct.pack(">f", 1.0e-9).hex().upper()
    qcrmin = struct.unpack(">f", bytes.fromhex(ledger["qcrmin_REAL4_word"]))[0]
    branches = Counter()
    keys = set()
    for line in path.read_text().splitlines():
        fields = line.split()
        assert len(fields) == 8 and fields[0] == "S10ENTRY"
        step, lat, i, k, action = map(int, fields[1:6])
        key = (step, lat, i, k)
        assert key not in keys
        keys.add(key)
        assert (step, lat, action) == (1, 73, 1)
        assert i in (113, 115) and 1 <= k <= 12
        qg = struct.unpack(">f", bytes.fromhex(fields[6]))[0]
        assert qg > 0.0
        assert struct.pack(">f", qg / 400.0).hex().upper() == fields[7]
        branches["active" if qg > qcrmin else "trace"] += 1
    assert len(keys) == ledger["row_count"] == 24
    assert branches == {"active": 19, "trace": 5}
