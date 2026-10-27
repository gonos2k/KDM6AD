#!/usr/bin/env python3
"""Replay four public native moment traces and check their execution receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_representative_boundaries import analyze  # noqa: E402
from harness.native_qnc_representative_trace_records import read_representative_trace  # noqa: E402


EXPECTED_MANIFEST_SHA = "233651bee30976de97ca6ae8c069225dc03f2c10f222a2250e2e1789330d6dad"
PARENTS = {
    "pr465": ("native_qnc_host_backoff_2026-10-27",
              "b2655e61ce31d358499e95c11fb93b76747135a81ca180dbbed05b3b31cbe833"),
    "pr466": ("native_qnc_host_backoff_review_2026-10-28",
              "802988fae908ac96e1fb60ba86d24de6e64de4128a6b6f455f16e13a65538a77"),
    "pr467": ("native_qnc_control_witness_2026-10-28",
              "c28e02c82214e19076eef14dbe12c9894261f716f293345326f4e4978d37378d"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, files: list[dict]) -> None:
    seen = set()
    for entry in files:
        rel = entry["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute() or
                ".." in Path(rel).parts or "__pycache__" in Path(rel).parts or
                Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe or repeated packet path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes root: {rel}")
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]:
            raise ValueError(f"packet asset differs: {rel}")


def _historical_inputs(manifest: dict) -> tuple[dict, dict, dict]:
    if manifest["parent_manifest_pins"] != {name: digest for name, (_, digest) in PARENTS.items()}:
        raise ValueError("historical manifest pin list differs")
    parent_data = {}
    for name, (directory, digest) in PARENTS.items():
        root = REPO / "harness/evidence" / directory
        raw = (root / "manifest.json").read_bytes()
        if sha(raw) != digest:
            raise ValueError(f"{name} historical packet manifest differs")
        packet_manifest = json.loads(raw)
        _inventory(root, packet_manifest["files"])
        parent_data[name] = root
    paths = {
        "pr465_execution": parent_data["pr465"] / "execution_summary.json",
        "pr466_candidate": parent_data["pr466"] / "residual_reason_rows.json",
        "pr467_control": parent_data["pr467"] / "control_witness_rows.json",
    }
    if manifest["parent_input_pins"] != {name: sha(path.read_bytes()) for name, path in paths.items()}:
        raise ValueError("historical execution or checkpoint witness input differs")
    return tuple(json.loads(paths[name].read_text()) for name in
                 ("pr465_execution", "pr466_candidate", "pr467_control"))


def build_analysis(manifest: dict) -> dict:
    previous, candidate, control = _historical_inputs(manifest)
    execution = json.loads((PACKET / "execution_summary.json").read_text())
    if (execution["status"] != "FOUR_FULL_HOST_STEPS_TRACE_NONINTERFERING" or
            execution["base_main_commit"] != "243d2f646d34d5de2967c709ca26d25e873085e7" or
            execution["build"]["changed_archive_members"] != ["solve_em.o"] or
            execution["build"]["base_pr465_build_receipt_sha256"] !=
                previous["private_build_receipt_sha256"] or
            execution["runtime"]["native_shape_i_j_k"] != [234, 282, 39] or
            execution["runtime"]["native_runtime_parameters"]["mp_physics"] != "137" or
            execution["runtime"]["native_runtime_parameters"]["no_mp_heating"] != "0" or
            execution["runtime"]["ranks"] != 1 or execution["runtime"]["threads"] != 1 or
            execution["runtime"]["dt_seconds"] != 20 or
            execution["observed_model_calls"] != {"host_steps": 4, "KDM_wrapper_entries": 8,
                                                  "RTTOV": 0, "optimizer": 0}):
        raise ValueError("representative native execution summary differs")
    overlay_path = REPO / "harness/native_qnc_representative_trace_overlay.py"
    if execution["build"]["public_overlay_sha256"] != sha(overlay_path.read_bytes()):
        raise ValueError("built native overlay source differs")
    traces = {}
    for case in ("control", "alpha025"):
        runs = execution["runs"][case]
        original = previous["runs"][case]
        if (runs["off"]["checkpoint_sha256"] != runs["on"]["checkpoint_sha256"] or
                runs["off"]["ack_sha256"] != runs["on"]["ack_sha256"] or
                runs["off"]["checkpoint_sha256"] != original["off"]["checkpoint_sha256"] or
                runs["on"]["checkpoint_sha256"] != original["on"]["checkpoint_sha256"] or
                runs["off"]["applied_control"] != runs["on"]["applied_control"] or
                runs["off"]["trace"] or runs["off"]["host_steps"] != 1 or
                runs["on"]["host_steps"] != 1 or
                runs["off"]["observed_kdm_wrapper_entries"] != 2 or
                runs["on"]["observed_kdm_wrapper_entries"] != 2):
            raise ValueError(f"{case} host trace-off/on or PR465 endpoint differs")
        descriptor = runs["on"]["trace"]
        rel = f"data/{case}/representative_moments.tsv"
        raw = (PACKET / rel).read_bytes()
        if (descriptor != {"path": rel, "sha256": sha(raw), "bytes": len(raw),
                           "typed_records": 568}):
            raise ValueError(f"{case} native trace receipt differs from published bytes")
        traces[case] = read_representative_trace(PACKET / rel)
        if len(traces[case].values) != 568:
            raise ValueError("representative trace field inventory differs")
    result = analyze(traces["control"], traces["alpha025"], control, candidate)
    result["checkpoint_witness_sha256"] = {
        "control": manifest["parent_input_pins"]["pr467_control"],
        "alpha025": manifest["parent_input_pins"]["pr466_candidate"],
    }
    if ([target["first_recorded_liquid_validity_split"] for target in result["targets"][:3]] !=
            [{"rk_step": 3, "stage": "RKSCALAR_AFTER"}] * 3 or
            result["targets"][3]["first_recorded_ice_validity_split"] !=
                {"rk_step": 3, "stage": "RKSCALAR_BEFORE"}):
        raise ValueError("representative validity-boundary conclusion differs")
    return result


def main() -> int:
    manifest_raw = (PACKET / "manifest.json").read_bytes()
    if sha(manifest_raw) != EXPECTED_MANIFEST_SHA:
        raise ValueError("representative packet manifest changed")
    manifest = json.loads(manifest_raw)
    if manifest["schema"] != "kdm6.qnc_representative_public_packet.v1":
        raise ValueError("representative packet schema differs")
    source = Path(__file__).read_bytes()
    if source.count(EXPECTED_MANIFEST_SHA.encode()) != 1:
        raise ValueError("replay source manifest-pin substitution differs")
    normalized_source = source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")
    if sha(normalized_source) != manifest["normalized_replay_sha256"]:
        raise ValueError("representative replay source changed")
    _inventory(PACKET, manifest["files"])
    for rel, digest in manifest["external_source_pins"].items():
        if sha((REPO / rel).read_bytes()) != digest:
            raise ValueError(f"representative source changed: {rel}")
    result = build_analysis(manifest)
    actual = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if actual != (PACKET / "analysis.json").read_bytes():
        raise ValueError("representative boundary analysis differs")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(actual),
                      "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0,
                                              "optimizer": 0}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
