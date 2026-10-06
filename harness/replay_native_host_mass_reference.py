#!/usr/bin/env python3
"""Guarded replay of the immutable PR #376 snapshot audit; no model run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "harness/evidence"
AUDIT_SOURCE_SHA256 = "20dfc2dc8c3fb388b3d0a04578c5f9f50cfb52ec035918f3d1192cadbaf5203b"
RECEIPT_SHA256 = "b75fa6d6c158f9233bf947fff507393552dd9c26906656caf6f1c976bf536b01"
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")


def validate_pair(initial_state, fields, selected):
    """Bind the single analysis row to the retained native column/background."""
    if (np.asarray(fields["nx"]).shape != () or np.asarray(fields["ny"]).shape != ()
            or fields["nx"] != 234 or fields["ny"] != 282):
        raise ValueError("analysis grid differs from retained native grid")
    flat = (selected["j_1based"] - 1) * 234 + selected["i_1based"] - 1
    if flat != 36576 or selected["flat_b"] != flat or not np.array_equal(fields["sub_idx"], [flat]):
        raise ValueError("analysis row differs from selected native column")
    if initial_state.shape != (12, 39) or initial_state.dtype != np.float64:
        raise ValueError("unexpected retained background layout")
    for index, name in enumerate(STATE_FIELDS):
        row = fields[f"xb_{name}"]
        if (row.shape != (1, 39) or row.dtype != np.float64
                or row[0].tobytes() != initial_state[index].tobytes()):
            raise ValueError(f"analysis background {name} differs from window input")


def main():
    source = EVIDENCE / "NATIVE_host_mass_reference_source_2026-10-06.py"
    if hashlib.sha256(source.read_bytes()).hexdigest() != AUDIT_SOURCE_SHA256:
        raise ValueError("historical audit source differs from pinned executed bytes")
    spec = importlib.util.spec_from_file_location("retained_host_mass_audit", source)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    if audit.sha(audit.RECEIPT) != RECEIPT_SHA256:
        raise ValueError("retained window receipt differs from pinned execution")
    receipt = json.loads(audit.RECEIPT.read_text())
    if audit.sha(audit.WINDOW) != receipt["arrays_sha256"] or audit.sha(audit.FIELDS) != receipt["full_domain_fields_sha256"]:
        raise ValueError("retained array hash differs from execution receipt")
    with np.load(audit.WINDOW, allow_pickle=False) as window, np.load(audit.FIELDS, allow_pickle=False) as fields:
        validate_pair(window["initial_state"], fields, receipt["selected_column"])
    # The original generator keeps its exact arithmetic and own hash/pressure guards.
    audit.main()


if __name__ == "__main__":
    main()
