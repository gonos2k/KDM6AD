#!/usr/bin/env python3
"""Replay a selected-star applied-face acceptance predicate on PR #471 data."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_applied_face_guard import first_passing_scale  # noqa: E402
from harness.native_qnc_advect_qi_trace_records import read_qnc_producer_trace  # noqa: E402
from harness.native_qnc_star_qi_records import (  # noqa: E402
    read_qnc_star_trace, read_star_qi_writer_trace,
)


EXPECTED_MANIFEST_SHA = "08cc728ee62603bd526070ba08948de09b54acacea2f04abac53b2dede6b3b44"
PARENT = REPO / "harness/evidence/native_qnc_star_qi_2026-10-28"
PARENT_REPLAY = importlib.import_module("harness.evidence.native_qnc_star_qi_2026-10-28.replay")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_analysis() -> dict:
    PARENT_REPLAY.main()
    cases = {}
    for case in ("control", "alpha025"):
        star = PARENT / "data" / case
        producer = REPO / "harness/evidence/native_qnc_advect_qi_2026-10-28/data" / case
        results = first_passing_scale(
            read_qnc_star_trace(star / "qnc_star.tsv"),
            read_star_qi_writer_trace(star / "qnc_star_qi_moments.tsv"),
            read_qnc_producer_trace(producer / "qnc_producer.tsv"),
            max_decrements=3,
        )
        expected = 0 if case == "control" else 2
        if results["first_passing_decrements"] != expected:
            raise ValueError(f"{case} selected-star guard result differs")
        cases[case] = results
    return {
        "schema": "kdm6.native_qnc_applied_face_guard_analysis.v1",
        "parent_analysis_sha256": sha((PARENT / "analysis.json").read_bytes()),
        "cases": cases,
        "predicate": "all seven exact saved-face residuals and compatible f32 states positive",
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
        "limits": {
            "changed_host_executable_run": False,
            "whole_domain_m0_admissible": False,
            "physical_number_units_certified": False,
            "compiled_fma_instruction_sequence_identified": False,
            "selected_star_only": True,
        },
    }


def main() -> int:
    raw = (PACKET / "manifest.json").read_bytes()
    if sha(raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("applied-face guard manifest changed")
    manifest = json.loads(raw)
    if (manifest["schema"] != "kdm6.native_qnc_applied_face_guard_packet.v1" or
            manifest["parent_manifest_sha256"] != sha((PARENT / "manifest.json").read_bytes())):
        raise ValueError("applied-face guard parent differs")
    source = Path(__file__).read_bytes()
    if sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) != manifest["normalized_replay_sha256"]:
        raise ValueError("applied-face guard replay source changed")
    for relative, digest in manifest["source_pins"].items():
        if sha((REPO / relative).read_bytes()) != digest:
            raise ValueError(f"applied-face guard source changed: {relative}")
    expected = (PACKET / "analysis.json").read_bytes()
    if len(expected) != manifest["analysis_bytes"] or sha(expected) != manifest["analysis_sha256"]:
        raise ValueError("applied-face guard published analysis changed")
    result = build_analysis()
    analysis = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if analysis != expected:
        raise ValueError("applied-face guard analysis differs")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(analysis),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
