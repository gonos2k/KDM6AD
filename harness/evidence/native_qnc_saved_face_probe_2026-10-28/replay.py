#!/usr/bin/env python3
"""Replay a frozen RK3 QNC face residual and local one-ULP counterfactual."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_qnc_face_residual_probe import analyze  # noqa: E402
from harness.native_qnc_advect_qi_trace_records import read_qnc_producer_trace  # noqa: E402
from harness.native_qnc_representative_trace_records import read_representative_trace  # noqa: E402


EXPECTED_MANIFEST_SHA = "a718b443a242bfda4192d0769a4e1dced98e013ab4ac3e3cf2b8bf1f9cd0da83"
PARENTS = {
    "pr468": ("native_qnc_representative_boundaries_2026-10-28",
              "233651bee30976de97ca6ae8c069225dc03f2c10f222a2250e2e1789330d6dad"),
    "pr469": ("native_qnc_advect_qi_2026-10-28",
              "6a13f766cb802ae7bdd26b5f6ee1b32d0e40168f7d43c1116e98e84bdfdfd4e2"),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, entries: list[dict]) -> None:
    seen = set()
    for entry in entries:
        rel = entry["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute() or
                ".." in Path(rel).parts or "__pycache__" in Path(rel).parts or
                Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe/repeated packet asset: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet asset escapes root: {rel}")
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or sha(raw) != entry["sha256"]:
            raise ValueError(f"packet asset differs: {rel}")


def _parents(manifest: dict) -> dict[str, Path]:
    if manifest["parent_manifest_pins"] != {name: digest for name, (_, digest) in PARENTS.items()}:
        raise ValueError("historical manifest pin list differs")
    roots = {}
    for name, (directory, digest) in PARENTS.items():
        root = REPO / "harness/evidence" / directory
        raw = (root / "manifest.json").read_bytes()
        if sha(raw) != digest:
            raise ValueError(f"{name} historical packet manifest differs")
        packet_manifest = json.loads(raw)
        _inventory(root, packet_manifest["files"])
        for rel, source_sha in packet_manifest["external_source_pins"].items():
            if sha((REPO / rel).read_bytes()) != source_sha:
                raise ValueError(f"{name} historical source changed: {rel}")
        roots[name] = root
    paths = {
        "control_producer": roots["pr469"] / "data/control/qnc_producer.tsv",
        "alpha025_producer": roots["pr469"] / "data/alpha025/qnc_producer.tsv",
        "control_state": roots["pr468"] / "data/control/representative_moments.tsv",
        "alpha025_state": roots["pr468"] / "data/alpha025/representative_moments.tsv",
    }
    if manifest["parent_input_pins"] != {name: sha(path.read_bytes()) for name, path in paths.items()}:
        raise ValueError("frozen QNC face/state input differs")
    return paths


def build_analysis(manifest: dict) -> dict:
    paths = _parents(manifest)
    return analyze(read_qnc_producer_trace(paths["control_producer"]),
                   read_qnc_producer_trace(paths["alpha025_producer"]),
                   read_representative_trace(paths["control_state"]),
                   read_representative_trace(paths["alpha025_state"]))


def main() -> int:
    raw_manifest = (PACKET / "manifest.json").read_bytes()
    if sha(raw_manifest) != EXPECTED_MANIFEST_SHA:
        raise ValueError("saved-face packet manifest changed")
    manifest = json.loads(raw_manifest)
    if manifest["schema"] != "kdm6.native_qnc_saved_face_probe_public_packet.v1":
        raise ValueError("saved-face packet schema differs")
    source = Path(__file__).read_bytes()
    if (source.count(EXPECTED_MANIFEST_SHA.encode()) != 1 or
            sha(source.replace(EXPECTED_MANIFEST_SHA.encode(), b"PENDING")) !=
                manifest["normalized_replay_sha256"]):
        raise ValueError("saved-face replay source changed")
    _inventory(PACKET, manifest["files"])
    for rel, digest in manifest["external_source_pins"].items():
        if sha((REPO / rel).read_bytes()) != digest:
            raise ValueError(f"saved-face calculation source changed: {rel}")
    result = build_analysis(manifest)
    reproduced = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if reproduced != (PACKET / "analysis.json").read_bytes():
        raise ValueError("saved-face calculation differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": sha(reproduced),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
