#!/usr/bin/env python3
"""Replay control-final moment repairs at all 54 candidate-failed profiles."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import sys

import numpy as np


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
PARENT = REPO / "harness/evidence/native_qnc_host_backoff_review_2026-10-28"
PARENT_MANIFEST_SHA = "802988fae908ac96e1fb60ba86d24de6e64de4128a6b6f455f16e13a65538a77"
HOST = REPO / "harness/evidence/native_qnc_host_backoff_2026-10-27"
HOST_MANIFEST_SHA = "b2655e61ce31d358499e95c11fb93b76747135a81ca180dbbed05b3b31cbe833"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        rel = item["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute()
                or ".." in Path(rel).parts or "__pycache__" in Path(rel).parts
                or Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe/repeated evidence path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"evidence path escapes packet: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"evidence asset differs: {rel}")


def _number(word: str) -> float:
    if len(word) != 8 or word.upper() != word:
        raise ValueError("raw moment word must be eight uppercase hex digits")
    value = float(np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0])
    if not np.isfinite(value):
        raise ValueError("nonfinite control moment word")
    return value


def build_analysis() -> dict:
    parent_raw = (PARENT / "manifest.json").read_bytes()
    host_raw = (HOST / "manifest.json").read_bytes()
    if _sha(parent_raw) != PARENT_MANIFEST_SHA or _sha(host_raw) != HOST_MANIFEST_SHA:
        raise ValueError("historical QNC packet manifest changed")
    parent_manifest = json.loads(parent_raw)
    host_manifest = json.loads(host_raw)
    _inventory(PARENT, parent_manifest)
    _inventory(HOST, host_manifest)
    for manifest in (parent_manifest, host_manifest):
        for name, expected in manifest["external_source_pins"].items():
            if _sha((REPO / name).read_bytes()) != expected:
                raise ValueError(f"historical QNC producer/source changed: {name}")
    previous = runpy.run_path(str(PARENT / "replay.py"))["build_analysis"]()
    previous_raw = (json.dumps(previous, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PARENT / "analysis.json").read_bytes() != previous_raw:
        raise ValueError("previous residual analysis changed")
    source_rows_path = PARENT / "residual_reason_rows.json"
    source_rows = json.loads(source_rows_path.read_text())
    witnesses_path = PACKET / "control_witness_rows.json"
    witness = json.loads(witnesses_path.read_text())
    producer = REPO / "harness/native_qnc_control_witness_producer.py"
    with np.load(HOST / "support_masks.npz", allow_pickle=False) as archive:
        m0 = np.asarray(archive["m0_mask"], dtype=np.bool_)
        control_bad = np.asarray(archive["control_hard_invalid"], dtype=np.bool_)
        candidate_bad = np.asarray(archive["alpha025_hard_invalid"], dtype=np.bool_)
    execution = json.loads((HOST / "execution_summary.json").read_text())
    inputs = {"control_final": execution["runs"]["control"]["off"]["checkpoint_sha256"],
              "candidate_residual_rows": _sha(source_rows_path.read_bytes()),
              "published_support_masks": _sha((HOST / "support_masks.npz").read_bytes())}
    old_rows = source_rows["rows"]
    rows = witness["rows"]
    if (witness["schema"] != "kdm6.native_qnc_control_failure_witness.v1" or
            witness["producer_sha256"] != _sha(producer.read_bytes()) or
            witness["input_sha256"] != inputs or witness["profile_count"] != 54 or
            len(rows) != 54 or len(old_rows) != 54 or
            m0.shape != (65988, 7) or control_bad.shape != (65988,) or
            candidate_bad.shape != (65988,) or
            witness["model_calls"] != {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}):
        raise ValueError("control witness source/input/profile binding differs")
    counts = Counter()
    origins = Counter()
    vertical = Counter()
    newly_vertical = Counter()
    overlap = {"same_layer_both": 0, "ready_only": 0, "final_only": 0,
               "disjoint_ready_final_profiles": 0}
    for old, row in zip(old_rows, rows):
        flat = old["flat_index_zero_based"]
        if (row["flat_index_zero_based"] != flat or row["i_one_based"] != flat % 234 + 1 or
                row["j_one_based"] != flat // 234 + 1 or not row["control_profile_hard_valid"] or
                not candidate_bad[flat] or control_bad[flat] or not m0[flat].any() or
                row["already_invalid_at_pre_command_READY40"] != old["already_hard_invalid_at_ready"]):
            raise ValueError("control witness coordinate or support differs")
        ready = {k for levels in old["ready_reason_levels_one_based"].values() for k in levels}
        final = {k for levels in old["final_reason_levels_one_based"].values() for k in levels}
        overlap["same_layer_both"] += len(ready & final)
        overlap["ready_only"] += len(ready - final)
        overlap["final_only"] += len(final - ready)
        overlap["disjoint_ready_final_profiles"] += bool(ready and not ready & final)
        if [layer["native_k_one_based"] for layer in row["final_failed_levels"]] != sorted(final):
            raise ValueError("control witness final native layers differ")
        old_by_level = {entry["native_k_one_based"]: entry for entry in old["failing_level_words"]}
        for layer in row["final_failed_levels"]:
            k1 = layer["native_k_one_based"]
            words = layer["control_f32_hex"]
            if set(words) != {"QCLOUD", "QNCLOUD", "QICE", "QNICE"}:
                raise ValueError("control witness field set differs")
            qc, nc, qi, ni = (_number(words[name]) for name in
                              ("QCLOUD", "QNCLOUD", "QICE", "QNICE"))
            if (qc > 0 and nc <= 0) or (qi > 0 and ni <= 0) or nc < 0 or ni < 0:
                raise ValueError("control witness still has a hard moment failure")
            liquid = k1 in old["final_reason_levels_one_based"].get(
                "liquid_QC_positive_NC_nonpositive", [])
            ice = k1 in old["final_reason_levels_one_based"].get(
                "ice_QI_positive_NI_nonpositive", [])
            if liquid == ice:
                raise ValueError("control witness must have exactly one failed phase")
            if liquid:
                expected_repair = "positive_NC_with_positive_QC" if qc > 0 and nc > 0 else "QC_zero"
                vertical[k1] += 1
                if old_by_level[k1]["final_f32_hex"]["QNCLOUD"] != "00000000":
                    raise ValueError("candidate liquid NC is not recorded positive zero")
                if not old["already_hard_invalid_at_ready"]:
                    newly_vertical[k1] += 1
                    ready_words = old_by_level[k1]["ready_f32_hex"]
                    ready_qc = _number(ready_words["QCLOUD"])
                    ready_nc = _number(ready_words["QNCLOUD"])
                    origin = ("ready_positive_NC" if ready_qc > 0 and ready_nc > 0
                              else "ready_QC_NC_zero" if ready_qc == 0 and ready_nc == 0
                              else "other")
                    if origin == "other":
                        raise ValueError("new liquid failure origin differs")
                    origins[origin] += 1
            else:
                expected_repair = "QI_zero" if qi == 0 else "positive_NI_with_positive_QI"
            if layer["control_repair"] != expected_repair:
                raise ValueError("control witness repair classification differs")
            counts[expected_repair] += 1
    summary = {"profile_count": 54,
               "candidate_liquid_failure_layer_count": sum(vertical.values()),
               "candidate_ice_failure_layer_count": counts["QI_zero"] + counts["positive_NI_with_positive_QI"],
               "control_repair_layer_counts": dict(sorted(counts.items())),
               "new_liquid_failure_origin_counts": {
                   name: origins[name] for name in ("ready_positive_NC", "ready_QC_NC_zero")},
               "ready_final_layer_overlap": overlap,
               "liquid_final_layers_by_native_k": {str(k): v for k, v in sorted(vertical.items())},
               "new_liquid_final_layers_by_native_k": {str(k): v for k, v in sorted(newly_vertical.items())}}
    for key, value in summary.items():
        if witness[key] != value:
            raise ValueError(f"control witness aggregate {key} differs")
    if (summary["control_repair_layer_counts"] != {"positive_NC_with_positive_QC": 54, "QI_zero": 1} or
            summary["new_liquid_failure_origin_counts"] != {"ready_positive_NC": 27,
                                                            "ready_QC_NC_zero": 2} or
            summary["ready_final_layer_overlap"] != {"same_layer_both": 20, "ready_only": 8,
                                                      "final_only": 35,
                                                      "disjoint_ready_final_profiles": 5} or
            summary["liquid_final_layers_by_native_k"].get("4") != 21 or
            summary["new_liquid_final_layers_by_native_k"].get("4") != 15):
        raise ValueError("control witness expected numerical groups differ")
    ice = [(old, row) for old, row in zip(old_rows, rows)
           if "ice_QI_positive_NI_nonpositive" in old["final_reason_levels_one_based"]]
    if len(ice) != 1:
        raise ValueError("expected one subnormal ice profile")
    ice_old, ice_control = ice[0]
    ice_k = ice_old["final_reason_levels_one_based"]["ice_QI_positive_NI_nonpositive"]
    if ice_old["flat_index_zero_based"] != 39078 or ice_k != [33]:
        raise ValueError("subnormal ice coordinate differs")
    ice_ready = next(item for item in ice_old["failing_level_words"] if item["native_k_one_based"] == 33)
    ice_final_control = next(item for item in ice_control["final_failed_levels"] if item["native_k_one_based"] == 33)
    if (ice_ready["ready_f32_hex"]["QICE"] != "00000007" or
            ice_ready["final_f32_hex"]["QICE"] != "00000002" or
            ice_final_control["control_f32_hex"]["QICE"] != "00000000" or
            any(item["QNICE"] != "00000000" for item in (
                ice_ready["ready_f32_hex"], ice_ready["final_f32_hex"],
                ice_final_control["control_f32_hex"])) or
            not 0 < _number("00000002") < np.finfo(np.float32).tiny):
        raise ValueError("subnormal ice witness words differ")
    return {"schema": "kdm6.native_qnc_control_witness_public_analysis.v1",
            "status": "CONTROL_SAME_LEVEL_MOMENT_REPAIR_CLASSIFIED_PROCESS_CAUSE_OPEN",
            "historical_pr466_manifest_sha256": PARENT_MANIFEST_SHA,
            "historical_pr465_manifest_sha256": HOST_MANIFEST_SHA,
            "historical_pr466_analysis_sha256": _sha(previous_raw),
            "control_witness_rows_sha256": _sha(witnesses_path.read_bytes()),
            "summary": summary,
            "ice_subnormal_witness": {"flat_index_zero_based": 39078,
                                      "native_ijk_one_based": [1, 168, 33],
                                      "ready_QI_hex": "00000007", "final_alpha_QI_hex": "00000002",
                                      "control_QI_hex": "00000000", "NI_hex_all_boundaries": "00000000"},
            "remaining_flat_indices_zero_based": [row["flat_index_zero_based"] for row in rows],
            "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "limits": {"physical_raw_NC_units_certified": False,
                       "named_process_cause_identified": False,
                       "full_fixed_support_cost_defined": False}}


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_control_witness_public_packet.v1":
        raise ValueError("wrong control-witness packet schema")
    if (manifest.get("historical_pr466_manifest_sha256") != PARENT_MANIFEST_SHA or
            manifest.get("historical_pr465_manifest_sha256") != HOST_MANIFEST_SHA):
        raise ValueError("control-witness historical manifest pin differs")
    _inventory(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"control-witness current source differs: {name}")
    result = build_analysis()
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PACKET / "analysis.json").read_bytes() != raw:
        raise ValueError("control-witness analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(raw),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
