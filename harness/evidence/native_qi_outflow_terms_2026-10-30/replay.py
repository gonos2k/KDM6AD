"""Authenticate and replay the lower-owner QI FLUX_OUT decomposition."""
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
PARENT = REPO / "harness/evidence/native_qi_face_producer_2026-10-30"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_files(root: Path, pins: dict[str, str]) -> None:
    if not isinstance(pins, dict) or not pins:
        raise ValueError("empty QI outflow pin inventory")
    for relative, digest in pins.items():
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise ValueError("unsafe QI outflow pin path")
        path = root / item
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("QI outflow pin escapes its root")
        if sha(path) != digest:
            raise ValueError(f"QI outflow pinned file changed: {relative}")


def _verify_execution(execution: dict) -> None:
    parent = json.loads((PARENT / "execution_summary.json").read_text())
    if (execution.get("schema") != "kdm6.native_qi_outflow_execution_summary.v1" or
            execution.get("parent_manifest_sha256") != sha(PARENT / "manifest.json") or
            execution.get("parent_analysis_sha256") != sha(PARENT / "analysis.json") or
            execution.get("base_executable_sha256") != parent["executable_sha256"] or
            execution.get("dso_sha256") != parent["dso_sha256"] or
            execution.get("overlay_sha256") != sha(
                REPO / "harness/native_qi_outflow_terms_overlay.py") or
            execution.get("current_overlay_renders_built_source_byte_identical") is not True or
            execution.get("changed_archive_members") != ["module_advect_em.o"] or
            execution.get("host_steps_completed") != 4 or
            execution.get("RTTOV_calls") != 0 or execution.get("optimizer_calls") != 0):
        raise ValueError("QI outflow execution lineage differs")
    for case in ("control", "alpha025"):
        run = execution["runs"][case]
        for mode in ("off", "on"):
            current = run[mode]
            previous = parent["runs"][case][mode]
            if (current["checkpoint_sha256"] != previous["checkpoint_sha256"] or
                    current["applied_ack_sha256"] != previous["applied_ack_sha256"] or
                    current["host_steps_completed"] != 1):
                raise ValueError(f"QI outflow host endpoint differs: {case}/{mode}")
        if (run["off"]["checkpoint_sha256"] != run["on"]["checkpoint_sha256"] or
                run["off"]["applied_ack_sha256"] != run["on"]["applied_ack_sha256"]):
            raise ValueError(f"QI outflow trace changed host state: {case}")
        for name, digest in parent["runs"][case]["on"]["trace_sha256"].items():
            if run["on"]["trace_sha256"].get(name) != digest:
                raise ValueError(f"inherited host trace changed: {case}/{name}")
        if run["on"]["trace_sha256"].get("qi_outflow") != sha(
                PACKET / "data" / case / "qi_outflow.tsv"):
            raise ValueError(f"QI outflow data/receipt differs: {case}")
        if run["off"]["trace_sha256"]:
            raise ValueError(f"QI outflow trace-off recorded data: {case}")


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qi_outflow_manifest.v1":
        raise ValueError("QI outflow manifest schema differs")
    _verify_files(PACKET, manifest["packet_files_sha256"])
    _verify_files(REPO, manifest["external_source_pins"])
    _verify_files(REPO, manifest["upstream_manifest_pins"])
    parent = importlib.import_module("harness.evidence.native_qi_face_producer_2026-10-30.replay")
    parent.main()
    _verify_execution(json.loads((PACKET / "execution_summary.json").read_text()))
    from harness.analyze_qi_outflow_terms import analyze  # noqa: PLC0415

    result = analyze(PACKET)
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if payload != (PACKET / "analysis.json").read_bytes():
        raise ValueError("QI outflow analysis differs from published bytes")
    print("REPLAY_PASSED")
    print("analysis_sha256:")
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
