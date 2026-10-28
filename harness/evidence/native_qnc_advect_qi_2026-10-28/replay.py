#!/usr/bin/env python3
"""Replay executed QNC/QI stage records and verify their path-free receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_advect_qi_trace import analyze  # noqa: E402
from harness.native_qnc_advect_qi_trace_records import (  # noqa: E402
    read_qi_writer_trace,
    read_qnc_producer_trace,
)
from harness.native_qnc_representative_trace_records import read_representative_trace  # noqa: E402


EXPECTED_MANIFEST_SHA = "6a13f766cb802ae7bdd26b5f6ee1b32d0e40168f7d43c1116e98e84bdfdfd4e2"
PARENT_MANIFEST_SHA = "233651bee30976de97ca6ae8c069225dc03f2c10f222a2250e2e1789330d6dad"
PARENT = REPO / "harness/evidence/native_qnc_representative_boundaries_2026-10-28"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, entries: list[dict]) -> None:
    seen = set()
    for entry in entries:
        rel = entry["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute() or
                ".." in Path(rel).parts or "__pycache__" in Path(rel).parts or
                Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe or repeated evidence path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"evidence path escapes packet: {rel}")
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]:
            raise ValueError(f"evidence asset differs: {rel}")


def _parent(manifest: dict) -> dict:
    raw = (PARENT / "manifest.json").read_bytes()
    if sha(raw) != PARENT_MANIFEST_SHA or manifest["pr468_manifest_sha256"] != PARENT_MANIFEST_SHA:
        raise ValueError("PR #468 representative manifest differs")
    previous = json.loads(raw)
    _inventory(PARENT, previous["files"])
    for rel, digest in previous["external_source_pins"].items():
        if sha((REPO / rel).read_bytes()) != digest:
            raise ValueError(f"PR #468 source changed: {rel}")
    expected = {
        "execution_summary": sha((PARENT / "execution_summary.json").read_bytes()),
        "control_trace": sha((PARENT / "data/control/representative_moments.tsv").read_bytes()),
        "alpha025_trace": sha((PARENT / "data/alpha025/representative_moments.tsv").read_bytes()),
    }
    if manifest["pr468_input_pins"] != expected:
        raise ValueError("PR #468 source trace or native execution input differs")
    return json.loads((PARENT / "execution_summary.json").read_text())


def build_analysis(manifest: dict) -> dict:
    previous_execution = _parent(manifest)
    execution = json.loads((PACKET / "execution_summary.json").read_text())
    if (execution["status"] != "FOUR_FULL_HOST_STEPS_TRACE_NONINTERFERING" or
            execution["base_main_commit"] != "69a87a507a3e1ea421131c176ad7498155fc4535" or
            set(execution["build"]["changed_archive_members"]) !=
                {"module_advect_em.o", "solve_em.o"} or
            not execution["build"]["module_interface_byte_identical"]):
        raise ValueError("native producer/writer build identity differs")
    if execution["build"]["base_receipt_sha256"] != previous_execution[
            "build"]["private_build_receipt_sha256"]:
        raise ValueError("PR #468 private build receipt identity differs")
    overlay = REPO / "harness/native_qnc_advect_qi_overlay.py"
    if execution["build"]["public_overlay_sha256"] != sha(overlay.read_bytes()):
        raise ValueError("native producer/writer overlay source differs")
    runtime = execution["runtime"]
    if (runtime["native_shape_i_j_k"] != [234, 282, 39] or
            runtime["ranks"] != 1 or runtime["threads"] != 1 or
            runtime["dt_seconds"] != 20 or not runtime["radiation_every_step"] or
            runtime["checked_namelist_values"] != {
                "scalar_adv_opt": "1", "moist_adv_opt": "1", "specified": ".true.",
                "spec_zone": "1", "diff_opt": "1", "no_mp_heating": "0",
                "use_q_diabatic": "0"} or
            runtime["native_runtime_parameters"]["mp_physics"] != "137" or
            execution["observed_model_calls"] != {"host_steps": 4,
                                                  "KDM_wrapper_entries": 8,
                                                  "RTTOV": 0, "optimizer": 0}):
        raise ValueError("native producer/writer forward configuration differs")
    producer, writer, previous = {}, {}, {}
    for case in ("control", "alpha025"):
        runs = execution["runs"][case]
        prior = previous_execution["runs"][case]
        if (runs["off"]["checkpoint_sha256"] != runs["on"]["checkpoint_sha256"] or
                runs["off"]["ack_sha256"] != runs["on"]["ack_sha256"] or
                runs["off"]["applied_control"] != runs["on"]["applied_control"] or
                runs["off"]["checkpoint_sha256"] != prior["off"]["checkpoint_sha256"] or
                runs["on"]["checkpoint_sha256"] != prior["on"]["checkpoint_sha256"] or
                runs["off"]["traces"] or
                any(runs[mode]["host_steps"] != 1 or
                    runs[mode]["observed_kdm_wrapper_entries"] != 2
                    for mode in ("off", "on"))):
            raise ValueError(f"{case} host trace-off/on or PR #468 endpoint differs")
        descriptors = runs["on"]["traces"]
        if set(descriptors) != {"qnc_producer", "qi_writer"}:
            raise ValueError(f"{case} trace descriptor list differs")
        paths = {"qnc_producer": f"data/{case}/qnc_producer.tsv",
                 "qi_writer": f"data/{case}/qi_writer_moments.tsv"}
        for name, rel in paths.items():
            raw = (PACKET / rel).read_bytes()
            expected_count = 77 if name == "qnc_producer" else 678
            if descriptors[name] != {"path": rel, "sha256": sha(raw),
                                     "bytes": len(raw), "typed_records": expected_count}:
                raise ValueError(f"{case}/{name} published trace differs from private receipt")
        producer[case] = read_qnc_producer_trace(PACKET / paths["qnc_producer"])
        writer[case] = read_qi_writer_trace(PACKET / paths["qi_writer"])
        previous[case] = read_representative_trace(
            PARENT / f"data/{case}/representative_moments.tsv")
    return analyze(producer, writer, previous)


def main() -> int:
    manifest_raw = (PACKET / "manifest.json").read_bytes()
    if sha(manifest_raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("native producer/writer manifest changed")
    manifest = json.loads(manifest_raw)
    if manifest["schema"] != "kdm6.native_qnc_advect_qi_public_packet.v1":
        raise ValueError("native producer/writer packet schema differs")
    source = Path(__file__).read_bytes()
    if source.count(EXPECTED_MANIFEST_SHA.encode()) != 1 or sha(
            source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) != manifest[
                "normalized_replay_sha256"]:
        raise ValueError("native producer/writer replay source changed")
    _inventory(PACKET, manifest["files"])
    for rel, digest in manifest["external_source_pins"].items():
        if sha((REPO / rel).read_bytes()) != digest:
            raise ValueError(f"native producer/writer source changed: {rel}")
    result = build_analysis(manifest)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if raw != (PACKET / "analysis.json").read_bytes():
        raise ValueError("native producer/writer analysis differs")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(raw),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
