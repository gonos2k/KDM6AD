#!/usr/bin/env python3
"""Replay the executed 54-layer QNC applied-face/RK preflight."""
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

from harness.analyze_qnc_domain_preflight import analyze, read_advect, read_writer  # noqa: E402
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates  # noqa: E402
from harness.native_qnc_star_qi_records import read_star_qi_writer_trace  # noqa: E402


EXPECTED_MANIFEST_SHA = "b6c72abe123046093d39e0a48900594a45c64a3ca499d6d7ce9be89acd5d50f5"
PR471 = REPO / "harness/evidence/native_qnc_star_qi_2026-10-28"
PR466 = REPO / "harness/evidence/native_qnc_host_backoff_review_2026-10-28"
PARENT_REPLAYS = (
    importlib.import_module("harness.evidence.native_qnc_star_qi_2026-10-28.replay"),
    importlib.import_module("harness.evidence.native_qnc_host_backoff_review_2026-10-28.replay"),
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        relative = item["path"]
        if (not isinstance(relative, str) or relative in seen or
                Path(relative).is_absolute() or ".." in Path(relative).parts):
            raise ValueError("unsafe/repeated QNC preflight packet path")
        seen.add(relative)
        path = PACKET / relative
        if path.is_symlink() or not path.resolve().is_relative_to(PACKET.resolve()):
            raise ValueError("QNC preflight packet path escapes packet")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
            raise ValueError(f"QNC preflight asset differs: {relative}")


def _source_pins(manifest: dict) -> None:
    for relative, expected in manifest["external_source_pins"].items():
        path = REPO / relative
        if path.is_symlink() or not path.resolve().is_relative_to(REPO.resolve()):
            raise ValueError("QNC preflight source path escapes repository")
        if sha(path.read_bytes()) != expected:
            raise ValueError(f"QNC preflight calculation source changed: {relative}")


def _prior_writer_identity(writer: dict, case: str) -> int:
    prior = read_star_qi_writer_trace(PR471 / f"data/{case}/qnc_star_qi_moments.tsv")
    for key in prior.values:
        record = writer["values"].get(key)
        if record is None or record[1] != prior.word(*key):
            raise ValueError(f"{case} existing PR471 writer value changed: {key}")
    return len(prior.values)


def build_analysis(manifest: dict) -> dict:
    for parent in PARENT_REPLAYS:
        parent.main()
    if manifest["parent_manifest_sha256"] != {
        "pr466": sha((PR466 / "manifest.json").read_bytes()),
        "pr471": sha((PR471 / "manifest.json").read_bytes()),
    }:
        raise ValueError("QNC preflight historical packet lineage differs")
    failure_json = (PR466 / "residual_reason_rows.json").read_bytes()
    if manifest["failure_rows_sha256"] != sha(failure_json):
        raise ValueError("QNC preflight failure-layer receipt differs")
    targets = failure_layer_coordinates(failure_json)
    execution = json.loads((PACKET / "execution_summary.json").read_text())
    prior = json.loads((PR471 / "execution_summary.json").read_text())
    if (execution["status"] != "FOUR_ACCEPTED_FULL_HOST_STEPS_TRACE_NONINTERFERING" or
            execution["parent_pr471_execution_sha256"] != sha((PR471 / "execution_summary.json").read_bytes()) or
            execution["runtime"] != prior["runtime"] or
            execution["observed_accepted_host_steps"] != 4 or
            execution["expected_kdm_wrapper_entries"] != 8 or
            execution["new_RTTOV_calls"] != 0 or execution["new_optimizer_calls"] != 0):
        raise ValueError("QNC preflight runtime/execution receipt differs")
    excluded = execution["excluded_preflights"]
    if (len(excluded) != 2 or
            {item["stage"] for item in excluded} != {
                "advect_source_compile", "isolated_link_script_first_attempt"} or
            any(item["counted_as_model_run"] for item in excluded)):
        raise ValueError("QNC preflight failed build attempts counted as runs")
    build = execution["build"]
    if (build["base_receipt_sha256"] != prior["private_build_receipt_sha256"] or
            build["dso_sha256"] != prior["build"]["dso_sha256"] or
            build["changed_archive_members"] != ["module_advect_em.o", "solve_em.o"] or
            not build["module_interface_byte_identical"] or
            build["advect_overlay_sha256"] != sha((REPO / "harness/native_qnc_domain_preflight_advect_overlay.py").read_bytes()) or
            build["solve_overlay_sha256"] != sha((REPO / "harness/native_qnc_domain_preflight_solve_overlay.py").read_bytes())):
        raise ValueError("QNC preflight build lineage differs")

    traces = {}
    prior_words = {}
    for case in ("control", "alpha025"):
        modes = execution["runs"][case]
        old = prior["runs"][case]
        if (modes["off"]["checkpoint_sha256"] != modes["on"]["checkpoint_sha256"] or
                modes["off"]["ack_sha256"] != modes["on"]["ack_sha256"] or
                modes["off"]["applied_control"] != modes["on"]["applied_control"] or
                modes["off"]["traces"] or
                any(modes[m]["status"] != "PASS" or modes[m]["host_steps_completed"] != 1 or
                    modes[m]["checkpoint_sha256"] != old[m]["checkpoint_sha256"] or
                    modes[m]["ack_sha256"] != old[m]["ack_sha256"]
                    for m in ("off", "on"))):
            raise ValueError(f"{case} off/on or PR471 endpoint differs")
        paths = {name: PACKET / f"data/{case}/{filename}" for name, filename in
                 (("advect", "advect.tsv"), ("rk_writer", "rk_writer.tsv"))}
        for name, path in paths.items():
            descriptor = modes["on"]["traces"][name]
            if descriptor != {"path": str(path.relative_to(PACKET)),
                               "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}:
                raise ValueError(f"{case} raw trace does not match execution receipt")
        advect = read_advect(paths["advect"], targets)
        writer = read_writer(paths["rk_writer"])
        prior_words[case] = _prior_writer_identity(writer, case)
        traces[case] = (advect, writer)
    result = analyze(*traces["control"], *traces["alpha025"], failure_json)
    if (prior_words != {"control": 1550, "alpha025": 1550} or
            result["control"]["category_counts"] != {
                "applied_correction_exceeds_available": 7, "rk3_positive": 47} or
            result["alpha025"]["category_counts"] != {
                "applied_correction_exceeds_available": 48,
                "exact_positive_but_stored_nonpositive": 6}):
        raise ValueError("QNC preflight coverage or category result differs")
    previous = json.loads((REPO / "harness/evidence/native_qnc_saved_face_probe_2026-10-28/analysis.json").read_text())
    for case in ("control", "alpha025"):
        target = result[case]["cells"]["i113_j70_k12"]
        if (target["applied_face_residual_exact"]["exact"] !=
                previous[case]["original_exact_saved_face"]["residual"]["exact"]):
            raise ValueError(f"{case} prior target exact residual differs")
    result["historical_pr471_writer_word_matches"] = prior_words
    result["execution_summary_sha256"] = sha((PACKET / "execution_summary.json").read_bytes())
    return result


def main() -> int:
    raw = (PACKET / "manifest.json").read_bytes()
    if sha(raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("QNC preflight manifest changed")
    manifest = json.loads(raw)
    if manifest["schema"] != "kdm6.native_qnc_domain_preflight_packet.v1":
        raise ValueError("QNC preflight packet schema differs")
    source = Path(__file__).read_bytes()
    if sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) != manifest["normalized_replay_sha256"]:
        raise ValueError("QNC preflight replay source changed")
    _inventory(manifest)
    _source_pins(manifest)
    result = build_analysis(manifest)
    actual = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if actual != (PACKET / "analysis.json").read_bytes():
        raise ValueError("QNC preflight analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(actual),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
