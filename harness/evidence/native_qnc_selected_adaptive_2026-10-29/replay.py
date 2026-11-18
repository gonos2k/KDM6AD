#!/usr/bin/env python3
"""Replay the frozen 54-donor adaptive-scale and receiver-state pilot."""
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

from harness.analyze_qnc_selected_adaptive_pilot import (  # noqa: E402
    DEFAULT_MAX_ULP, analyze_pilot, load_v2_inputs,
)


EXPECTED_MANIFEST_SHA = "6a8ec5c06456148d4ad1cf3da90a795d1d44b984fa8cbac66e5b75dbc7e76452"
PARENT = REPO / "harness/evidence/native_qnc_candidate_inputs_2026-10-28"
FAILURES = REPO / "harness/evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
PARENT_REPLAY = importlib.import_module("harness.evidence.native_qnc_candidate_inputs_2026-10-28.replay")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_analysis(manifest: dict) -> dict:
    PARENT_REPLAY.main()
    if (manifest["parent_manifest_sha256"] != sha((PARENT / "manifest.json").read_bytes()) or
            manifest["failure_rows_sha256"] != sha(FAILURES.read_bytes()) or
            manifest["max_ulp_cap"] != DEFAULT_MAX_ULP):
        raise ValueError("selected adaptive pilot parent or search bound differs")
    control_faces, control_writer, alpha_faces, alpha_writer, rows = load_v2_inputs(PARENT, FAILURES)
    result = analyze_pilot(control_faces, control_writer, alpha_faces, alpha_writer,
                           rows, max_ulp=DEFAULT_MAX_ULP)
    if result["schema"] != "kdm6.native_qnc_selected_adaptive_pilot.v3":
        raise ValueError("selected adaptive pilot arithmetic schema differs")
    result["parent_candidate_inputs_analysis_sha256"] = sha((PARENT / "analysis.json").read_bytes())
    if (result["cases"]["control"]["scale_search"]["step_histogram"] != {"0": 47, "1": 7} or
            result["cases"]["alpha025"]["scale_search"]["step_histogram"] !=
                {"1": 30, "2": 19, "3": 4, "4": 1} or
            any(result["cases"][case]["scale_search"]["unresolved"] or
                result["cases"][case]["case_specific_candidate"]["failures_ikj"]["donors"] or
                result["cases"][case]["baseline_to_candidate_failures"][
                    "new_sign_failures_all_cells_ikj"] or
                result["cases"][case]["baseline_to_candidate_failures"][
                    "new_qc_positive_receiver_failures_ikj"]
                for case in ("control", "alpha025")) or
            result["same_operator"] is None):
        raise ValueError("selected adaptive pilot result/receiver gate differs")
    return result


def main() -> int:
    raw = (PACKET / "manifest.json").read_bytes()
    if sha(raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("selected adaptive pilot manifest changed")
    manifest = json.loads(raw)
    if manifest["schema"] != "kdm6.native_qnc_selected_adaptive_packet.v3":
        raise ValueError("selected adaptive pilot packet schema differs")
    source = Path(__file__).read_bytes()
    if sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) != manifest["normalized_replay_sha256"]:
        raise ValueError("selected adaptive pilot replay source changed")
    if sha((REPO / "harness/analyze_qnc_selected_adaptive_pilot.py").read_bytes()) != manifest[
            "analyzer_source_sha256"]:
        raise ValueError("selected adaptive pilot analyzer source changed")
    expected = (PACKET / "analysis.json").read_bytes()
    if len(expected) != manifest["analysis_bytes"] or sha(expected) != manifest["analysis_sha256"]:
        raise ValueError("selected adaptive pilot published analysis changed")
    result = build_analysis(manifest)
    actual = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if actual != expected:
        raise ValueError("selected adaptive pilot result differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(actual),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
