#!/usr/bin/env python3
"""Hash-bound offline replay of a one-ULP QNC donor-scale counterfactual."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_native_qnc_state7_trace import read_state7_trace  # noqa: E402
from harness.analyze_qnc_shared_face_trace import read_shared_trace  # noqa: E402
from harness.analyze_saved_qnc_scale_backoff import analyze_one_ulp_backoff  # noqa: E402
from harness.replay_qnc_flux_limiter_trace import read_qnc_flux_trace  # noqa: E402


STATE7 = REPO / "harness/evidence/native_qnc_state7_2026-10-27"
STATE7_MANIFEST_SHA = "6737fdabf1c023fe808c00c39b5d1007a43aa1323737f19a63ba1b7fb643ed02"
PARENT = REPO / "harness/evidence/native_qnc_state_budget_2026-10-27"
PARENT_MANIFEST_SHA = "ae7c1209adf5083722b609ac1e486996ba1f69b3b09f0df47d8928e31632f1c0"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        relative = item["path"]
        if (not isinstance(relative, str) or relative in seen or Path(relative).is_absolute()
                or ".." in Path(relative).parts):
            raise ValueError(f"unsafe or repeated packet path: {relative}")
        seen.add(relative)
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes: {relative}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"packet asset changed: {relative}")


def _pinned_manifest(root: Path, expected: str) -> dict:
    raw = (root / "manifest.json").read_bytes()
    if _sha(raw) != expected:
        raise ValueError(f"historical packet manifest changed: {root.name}")
    manifest = json.loads(raw)
    _inventory(root, manifest)
    return manifest


def build_analysis() -> dict:
    old = _pinned_manifest(STATE7, STATE7_MANIFEST_SHA)
    parent = _pinned_manifest(PARENT, PARENT_MANIFEST_SHA)
    if parent["historical_pr461_manifest_sha256"] != STATE7_MANIFEST_SHA:
        raise ValueError("state-budget and state7 packet lineage differs")
    historical_analyzer = PARENT / "source_snapshots/pr461_analyze_native_qnc_state7_trace.py.txt"
    for name, expected in old["external_source_pins"].items():
        source = historical_analyzer if name == "harness/analyze_native_qnc_state7_trace.py" else REPO / name
        if _sha(source.read_bytes()) != expected:
            raise ValueError(f"historical PR461 source differs: {name}")
    for name, expected in parent["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"parent state-budget source differs: {name}")
    shared_manifest = REPO / "harness/evidence/native_qnc_shared_face_2026-10-27/manifest.json"
    if _sha(shared_manifest.read_bytes()) != old["historical_pr459_packet_manifest_sha256"]:
        raise ValueError("historical PR459 shared-face manifest differs")
    cases = {}
    for case in ("control", "alpha025"):
        data = STATE7 / "data" / case
        result = analyze_one_ulp_backoff(
            read_state7_trace(data / "qnc_state7.tsv"),
            read_shared_trace(data / "qnc_shared.tsv"),
            read_qnc_flux_trace(data / "qnc_flux.tsv").select_qnc_scalar_group(),
            case=case,
        )
        cases[case] = result
    return {
        "schema": "kdm6.saved_qnc_one_ulp_backoff_public_analysis.v1",
        "status": "SAVED_ONE_ULP_COUNTERFACTUAL_LOCALLY_POSITIVE_HOST_GATE_OPEN",
        "state7_manifest_sha256": STATE7_MANIFEST_SHA,
        "parent_state_budget_manifest_sha256": PARENT_MANIFEST_SHA,
        "cases": cases,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.saved_qnc_scale_backoff_public_packet.v1":
        raise ValueError("wrong backoff packet schema")
    _inventory(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"backoff replay source changed: {name}")
    result = build_analysis()
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PACKET / "analysis.json").read_bytes() != raw:
        raise ValueError("saved one-ULP analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(raw),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
