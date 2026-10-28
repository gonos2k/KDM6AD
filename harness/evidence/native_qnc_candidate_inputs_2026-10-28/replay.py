#!/usr/bin/env python3
"""Replay executed QNC pre/post-face and receiver inputs for 54 donors."""
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

from harness.analyze_qnc_candidate_inputs import analyze, read_faces, read_writer  # noqa: E402
from harness.analyze_qnc_domain_preflight import (  # noqa: E402
    read_advect, read_writer as read_parent_writer,
)
from harness.native_qnc_candidate_face_overlay import receiver_union  # noqa: E402
from harness.native_qnc_advect_qi_trace_records import read_qnc_producer_trace  # noqa: E402
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates  # noqa: E402


EXPECTED_MANIFEST_SHA = "a975acf33c9b42a644d0682f2c47476bae15856d3af3abbcc0deb1be407b2506"
PARENT = REPO / "harness/evidence/native_qnc_domain_preflight_2026-10-28"
PR469 = REPO / "harness/evidence/native_qnc_advect_qi_2026-10-28"
FAILURES = REPO / "harness/evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json"
PARENT_REPLAY = importlib.import_module("harness.evidence.native_qnc_domain_preflight_2026-10-28.replay")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        relative = item["path"]
        if (not isinstance(relative, str) or relative in seen or
                Path(relative).is_absolute() or ".." in Path(relative).parts):
            raise ValueError("unsafe/repeated QNC candidate-input packet path")
        seen.add(relative)
        path = PACKET / relative
        if path.is_symlink() or not path.resolve().is_relative_to(PACKET.resolve()):
            raise ValueError("QNC candidate-input asset path escapes packet")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
            raise ValueError(f"QNC candidate-input asset differs: {relative}")


def build_analysis(manifest: dict) -> dict:
    PARENT_REPLAY.main()
    if (manifest["parent_manifest_sha256"] != sha((PARENT / "manifest.json").read_bytes()) or
            manifest["failure_rows_sha256"] != sha(FAILURES.read_bytes())):
        raise ValueError("QNC candidate-input historical parent differs")
    execution = json.loads((PACKET / "execution_summary.json").read_text())
    prior = json.loads((PARENT / "execution_summary.json").read_text())
    if (execution["status"] != "FOUR_FINAL_V2_FULL_HOST_STEPS_TRACE_NONINTERFERING" or
            execution["parent_pr474_execution_sha256"] != sha((PARENT / "execution_summary.json").read_bytes()) or
            execution["runtime"] != prior["runtime"] or
            execution["observed_final_v2_host_steps"] != 4 or
            execution["additional_preliminary_v1_host_steps"] != 2 or
            execution["expected_final_v2_kdm_wrapper_entries"] != 8 or
            execution["new_RTTOV_calls"] != 0 or execution["new_optimizer_calls"] != 0 or
            len(execution["preliminary_v1_alpha_steps_excluded_from_final_analysis"]) != 2 or
            any(item["counted_in_final_v2"] for item in
                execution["preliminary_v1_alpha_steps_excluded_from_final_analysis"])):
        raise ValueError("QNC candidate-input model execution receipt differs")
    build = execution["build"]
    if (build["base_receipt_sha256"] != prior["private_build_receipt_sha256"] or
            build["dso_sha256"] != prior["build"]["dso_sha256"] or
            build["changed_archive_members"] != ["module_advect_em.o", "solve_em.o"] or
            not build["module_interface_byte_identical"] or
            build["face_capture_cells"] != 382 or build["rk_writer_targets"] != 383 or
            build["advect_overlay_sha256"] != sha((REPO / "harness/native_qnc_candidate_face_overlay.py").read_bytes()) or
            build["solve_overlay_sha256"] != sha((REPO / "harness/native_qnc_candidate_solve_overlay.py").read_bytes())):
        raise ValueError("QNC candidate-input build lineage differs")
    failure_json = FAILURES.read_bytes()
    captures = receiver_union(failure_json)
    donors = failure_layer_coordinates(failure_json)
    cases = {}
    parents = {}
    for case in ("control", "alpha025"):
        modes, previous = execution["runs"][case], prior["runs"][case]
        if (modes["off"]["checkpoint_sha256"] != modes["on"]["checkpoint_sha256"] or
                modes["off"]["ack_sha256"] != modes["on"]["ack_sha256"] or
                modes["off"]["applied_control"] != modes["on"]["applied_control"] or
                modes["off"]["traces"] or
                any(modes[m]["status"] != "PASS" or modes[m]["host_steps_completed"] != 1 or
                    modes[m]["checkpoint_sha256"] != previous[m]["checkpoint_sha256"] or
                    modes[m]["ack_sha256"] != previous[m]["ack_sha256"]
                    for m in ("off", "on"))):
            raise ValueError(f"{case} off/on or PR474 endpoint differs")
        paths = {name: PACKET / f"data/{case}/{filename}" for name, filename in
                 (("faces", "faces.tsv"), ("rk_writer", "rk_writer.tsv"))}
        for name, path in paths.items():
            descriptor = modes["on"]["traces"][name]
            if descriptor != {"path": str(path.relative_to(PACKET)),
                               "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}:
                raise ValueError(f"{case} raw trace does not match execution receipt")
        cases[case] = (read_faces(paths["faces"], captures), read_writer(paths["rk_writer"]))
        parent_root = PARENT / "data" / case
        parents[case] = (read_advect(parent_root / "advect.tsv", donors),
                         read_parent_writer(parent_root / "rk_writer.tsv"))
    result = analyze(cases, parents, failure_json)
    pre_face_matches = {}
    for case in ("control", "alpha025"):
        original = read_qnc_producer_trace(PR469 / f"data/{case}/qnc_producer.tsv")
        row = cases[case][0]["values"][(113, 12, 70)]
        count = 0
        for face in ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH",
                     "FZ_BOTTOM", "FZ_TOP"):
            axis, side = face.split("_")
            if row[f"{axis}_PRE_{side}"] != original.word(
                    3, "RK3_PD_PRE_LIMIT", 113, 12, 70, face):
                raise ValueError(f"{case} PR469 pre-limit face differs: {face}")
            count += 1
        pre_face_matches[case] = count
    result["pr469_target_pre_face_word_matches"] = pre_face_matches
    result["execution_summary_sha256"] = sha((PACKET / "execution_summary.json").read_bytes())
    result["parent_pr474_analysis_sha256"] = sha((PARENT / "analysis.json").read_bytes())
    if (result["selected_capture_cell_count"] != 382 or
            any(result["cases"][case]["source_compatible_cells"] !=
                {"axis_matched": 382, "rk_matched": 382}
                for case in ("control", "alpha025"))):
        raise ValueError("QNC candidate-input analysis coverage differs")
    return result


def main() -> int:
    raw = (PACKET / "manifest.json").read_bytes()
    if sha(raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("QNC candidate-input manifest changed")
    manifest = json.loads(raw)
    if manifest["schema"] != "kdm6.native_qnc_candidate_inputs_packet.v1":
        raise ValueError("QNC candidate-input packet schema differs")
    source = Path(__file__).read_bytes()
    if sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) != manifest["normalized_replay_sha256"]:
        raise ValueError("QNC candidate-input replay source changed")
    _inventory(manifest)
    for relative, digest in manifest["external_source_pins"].items():
        path = REPO / relative
        if path.is_symlink() or not path.resolve().is_relative_to(REPO.resolve()):
            raise ValueError("QNC candidate-input source escapes repository")
        if sha(path.read_bytes()) != digest:
            raise ValueError(f"QNC candidate-input calculation source changed: {relative}")
    result = build_analysis(manifest)
    actual = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if actual != (PACKET / "analysis.json").read_bytes():
        raise ValueError("QNC candidate-input analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(actual),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
