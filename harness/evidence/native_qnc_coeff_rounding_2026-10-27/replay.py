#!/usr/bin/env python3
"""Replay the PD/RK coefficient gate and saved QNC rounded-state ledger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_native_qnc_saved_state_budget import analyze_saved_state_budget  # noqa: E402
from harness.analyze_native_qnc_state7_trace import read_state7_trace  # noqa: E402
from harness.analyze_qnc_shared_face_trace import read_shared_trace  # noqa: E402
from harness.analyze_saved_qnc_scale_backoff import analyze_one_ulp_backoff  # noqa: E402
from harness.replay_qnc_flux_limiter_trace import read_qnc_flux_trace  # noqa: E402


HISTORICAL = {
    "state7": ("native_qnc_state7_2026-10-27",
               "6737fdabf1c023fe808c00c39b5d1007a43aa1323737f19a63ba1b7fb643ed02"),
    "budget": ("native_qnc_state_budget_2026-10-27",
                "ae7c1209adf5083722b609ac1e486996ba1f69b3b09f0df47d8928e31632f1c0"),
    "backoff": ("native_qnc_scale_backoff_2026-10-27",
                 "c81e545cda01d815f53525364a003b3446ab1f9ecac82048975be9001e38985a"),
}
SNAPSHOTS = {
    ("state7", "harness/analyze_native_qnc_state7_trace.py"):
        REPO / "harness/evidence/native_qnc_state_budget_2026-10-27/source_snapshots/pr461_analyze_native_qnc_state7_trace.py.txt",
    ("budget", "harness/analyze_native_qnc_saved_state_budget.py"):
        PACKET / "source_snapshots/pr462_saved_state_budget.py.txt",
    ("backoff", "harness/analyze_native_qnc_saved_state_budget.py"):
        PACKET / "source_snapshots/pr462_saved_state_budget.py.txt",
    ("backoff", "harness/analyze_saved_qnc_scale_backoff.py"):
        PACKET / "source_snapshots/pr463_scale_backoff.py.txt",
}
RUNS = {"control": "control_state7_v1_on", "alpha025": "alpha025_state7_v1_on"}


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


def _historical_packet(name: str) -> tuple[Path, dict]:
    folder, expected = HISTORICAL[name]
    root = REPO / "harness/evidence" / folder
    raw = (root / "manifest.json").read_bytes()
    if _sha(raw) != expected:
        raise ValueError(f"historical {name} manifest differs")
    manifest = json.loads(raw)
    _inventory(root, manifest)
    for source, pinned in manifest["external_source_pins"].items():
        path = SNAPSHOTS.get((name, source), REPO / source)
        if _sha(path.read_bytes()) != pinned:
            raise ValueError(f"historical {name} source differs: {source}")
    return root, manifest


def _historical_subset(previous, current) -> bool:
    if isinstance(previous, dict):
        return isinstance(current, dict) and all(
            key in current and _historical_subset(value, current[key])
            for key, value in previous.items())
    if isinstance(previous, list):
        return (isinstance(current, list) and len(previous) == len(current)
                and all(_historical_subset(a, b) for a, b in zip(previous, current)))
    return previous == current


def build_analysis() -> dict:
    state7, old = _historical_packet("state7")
    budget, parent = _historical_packet("budget")
    backoff, candidate_parent = _historical_packet("backoff")
    if (parent["historical_pr461_manifest_sha256"] != HISTORICAL["state7"][1] or
            candidate_parent["historical_pr461_manifest_sha256"] != HISTORICAL["state7"][1] or
            candidate_parent["parent_pr462_manifest_sha256"] != HISTORICAL["budget"][1] or
            old["historical_pr459_packet_manifest_sha256"] != _sha((
                REPO / "harness/evidence/native_qnc_shared_face_2026-10-27/manifest.json").read_bytes())):
        raise ValueError("historical QNC packet lineage differs")
    saved_budget = json.loads((budget / "analysis.json").read_text())["cases"]
    saved_backoff = json.loads((backoff / "analysis.json").read_text())["cases"]
    cases = {}
    for case, run_id in RUNS.items():
        data = state7 / "data" / case
        state = read_state7_trace(data / "qnc_state7.tsv")
        shared = read_shared_trace(data / "qnc_shared.tsv")
        flux = read_qnc_flux_trace(data / "qnc_flux.tsv").select_qnc_scalar_group()
        current_budget = analyze_saved_state_budget(state, shared, run_id=run_id)
        prior_budget = {key: value for key, value in saved_budget[case].items()
                        if key != "target_kdm_boundary"}
        if current_budget != prior_budget:
            raise ValueError(f"{case} existing saved-state budget changed")
        current_backoff = analyze_one_ulp_backoff(state, shared, flux, case=case)
        if not _historical_subset(saved_backoff[case], json.loads(json.dumps(current_backoff))):
            raise ValueError(f"{case} existing saved scale-backoff result changed")
        rounded = current_backoff["weighted_f32_state_change_individually_compatible_range"]
        cases[case] = {
            "pd_rk_coefficient_bitwise_verified_cells": len(current_budget["cells"]),
            "historical_budget_fields_unchanged": True,
            "historical_backoff_fields_unchanged": True,
            "weighted_exact_stored_pd_state_change":
                current_backoff["weighted_exact_stored_pd_state_change"],
            "weighted_f32_state_change_individually_compatible_range": rounded,
            "unchanged_neighbor_f32_cell_count": current_backoff["unchanged_neighbor_f32_cell_count"],
            "target_original_rk_qnc_raw": current_backoff["cells"]["i221_j63_k6"]["original_recorded_qnc_raw"],
            "target_candidate_f32_qnc_raw": current_backoff["cells"]["i221_j63_k6"]["candidate_source_compatible_f32_qnc_raw"],
        }
    return {
        "schema": "kdm6.native_qnc_coefficient_and_rounding_public_analysis.v1",
        "status": "PD_RK_COEFFICIENT_GUARD_AND_SAVED_ROUNDED_LEDGER_PASSED_HOST_GATE_OPEN",
        "historical_manifest_sha256": {key: expected for key, (_, expected) in HISTORICAL.items()},
        "cases": cases,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
        "limits": {
            "physical_raw_number_units_certified": False,
            "full_host_variant_or_domain_budget_verified": False,
            "candidate_RTTOV_cost_or_analysis_acceptance": False,
        },
    }


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_coeff_rounding_public_packet.v1":
        raise ValueError("wrong QNC coefficient packet schema")
    _inventory(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"current QNC coefficient source changed: {name}")
    result = build_analysis()
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PACKET / "analysis.json").read_bytes() != raw:
        raise ValueError("QNC coefficient/rounding analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(raw),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
