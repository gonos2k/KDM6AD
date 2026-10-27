"""Capture control-final moment words at the 54 candidate failure profiles.

This reads an existing private checkpoint and two published public assets.
It records matching native levels without running or changing the model.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from harness.native_qnc_residual_reason_producer import FIELDS, _fields, _flags


CONTROL_SHA = "2f66f2fb920bd808989eef70c983b4b9cff378a44c7169692f07c6bc70043ec9"
RESIDUAL_SHA = "fa7ba0a92ccec5f1b8001a3c218b8a737ca90c1b9ed4a24f6253e616c1f6257e"
SUPPORT_SHA = "c4154b4b735fcbfb5509b1f23ee53f4cfe17b46ccf0c6930f63aa244f2a0f9a9"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(word: str) -> float:
    if len(word) != 8:
        raise ValueError("raw moment word must have eight hex digits")
    return float(np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0])


def produce(control: Path, residual: Path, support: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise FileExistsError("control-witness output requires a new path")
    for source, expected in ((control, CONTROL_SHA), (residual, RESIDUAL_SHA), (support, SUPPORT_SHA)):
        if sha(source) != expected:
            raise ValueError(f"pinned control-witness input differs: {source.name}")
    prior = json.loads(residual.read_text())
    rows = prior["rows"]
    with np.load(support, allow_pickle=False) as archive:
        control_bad = np.asarray(archive["control_hard_invalid"], dtype=np.bool_)
        candidate_bad = np.asarray(archive["alpha025_hard_invalid"], dtype=np.bool_)
        m0 = np.asarray(archive["m0_mask"], dtype=np.bool_)
    fields = _fields(control)
    flags = _flags(fields)
    control_any = np.any(np.stack([np.any(value, axis=0) for value in flags.values()]), axis=0)
    if (len(rows) != 54 or control_bad.shape != (65988,) or
            candidate_bad.shape != (65988,) or m0.shape != (65988, 7) or
            not np.array_equal(control_bad, control_any)):
        raise ValueError("control/candidate hard-mask inputs differ")
    selected = np.flatnonzero(candidate_bad & m0.any(axis=1))
    if selected.tolist() != [row["flat_index_zero_based"] for row in rows]:
        raise ValueError("candidate failure rows differ from published M0")
    if control_bad[selected].any():
        raise ValueError("a candidate-failed profile remains hard-invalid in control")
    repairs = Counter()
    origins = Counter()
    vertical = Counter()
    new_vertical = Counter()
    overlap = {"same_layer_both": 0, "ready_only": 0, "final_only": 0,
               "disjoint_ready_final_profiles": 0}
    result_rows = []
    for row in rows:
        flat = row["flat_index_zero_based"]
        if not row["already_hard_invalid_at_ready"] and (
                len(row["final_reason_levels_one_based"].get("liquid_QC_positive_NC_nonpositive", [])) != 1 or
                len(row["final_reason_levels_one_based"]) != 1):
            raise ValueError("new liquid failure must have one final failed layer per profile")
        ready_levels = {k for levels in row["ready_reason_levels_one_based"].values() for k in levels}
        final_levels = {k for levels in row["final_reason_levels_one_based"].values() for k in levels}
        overlap["same_layer_both"] += len(ready_levels & final_levels)
        overlap["ready_only"] += len(ready_levels - final_levels)
        overlap["final_only"] += len(final_levels - ready_levels)
        overlap["disjoint_ready_final_profiles"] += bool(ready_levels and not ready_levels & final_levels)
        by_level = {entry["native_k_one_based"]: entry for entry in row["failing_level_words"]}
        level_rows = []
        for k1 in sorted(final_levels):
            entry = by_level[k1]
            k0 = k1 - 1
            control_words = {name: f"{int(fields[name][k0, flat].view(np.uint32)):08X}" for name in FIELDS}
            qc, nc, qi, ni = (_number(control_words[name]) for name in FIELDS)
            liquid = k1 in row["final_reason_levels_one_based"].get("liquid_QC_positive_NC_nonpositive", [])
            ice = k1 in row["final_reason_levels_one_based"].get("ice_QI_positive_NI_nonpositive", [])
            if liquid:
                if entry["final_f32_hex"]["QNCLOUD"] != "00000000":
                    raise ValueError("final liquid failure NC is not the captured positive zero")
                control_repair = ("positive_NC_with_positive_QC" if qc > 0 and nc > 0
                                  else "QC_zero" if qc == 0 else "other")
                if control_repair == "other":
                    raise ValueError("control liquid moment did not become admissible")
                vertical[k1] += 1
                if not row["already_hard_invalid_at_ready"]:
                    new_vertical[k1] += 1
                    ready_qc = _number(entry["ready_f32_hex"]["QCLOUD"])
                    ready_nc = _number(entry["ready_f32_hex"]["QNCLOUD"])
                    origin = ("ready_positive_NC" if ready_qc > 0 and ready_nc > 0
                              else "ready_QC_NC_zero" if ready_qc == 0 and ready_nc == 0
                              else "other")
                    if origin == "other":
                        raise ValueError("new liquid failure origin is not one of the captured classes")
                    origins[origin] += 1
            elif ice:
                control_repair = "QI_zero" if qi == 0 else "positive_NI_with_positive_QI" if qi > 0 and ni > 0 else "other"
                if control_repair == "other":
                    raise ValueError("control ice moment did not become admissible")
            else:
                raise ValueError("final failure level has no liquid/ice reason")
            repairs[control_repair] += 1
            level_rows.append({"native_k_one_based": k1,
                               "final_reason": "liquid" if liquid else "ice",
                               "control_f32_hex": control_words,
                               "control_repair": control_repair})
        result_rows.append({"flat_index_zero_based": flat, "i_one_based": row["i_one_based"],
                            "j_one_based": row["j_one_based"],
                            "control_profile_hard_valid": True,
                            "already_invalid_at_pre_command_READY40": row["already_hard_invalid_at_ready"],
                            "final_failed_levels": level_rows})
    summary = {"schema": "kdm6.native_qnc_control_failure_witness.v1",
               "producer_sha256": sha(Path(__file__)),
               "input_sha256": {"control_final": CONTROL_SHA, "candidate_residual_rows": RESIDUAL_SHA,
                                "published_support_masks": SUPPORT_SHA},
               "profile_count": len(result_rows),
               "candidate_liquid_failure_layer_count": sum(vertical.values()),
               "candidate_ice_failure_layer_count": sum(
                   level["final_reason"] == "ice" for row in result_rows for level in row["final_failed_levels"]),
               "control_repair_layer_counts": {name: int(value) for name, value in sorted(repairs.items())},
               "new_liquid_failure_origin_counts": {
                   name: int(origins[name]) for name in ("ready_positive_NC", "ready_QC_NC_zero")},
               "ready_final_layer_overlap": overlap,
               "liquid_final_layers_by_native_k": {str(k): count for k, count in sorted(vertical.items())},
               "new_liquid_final_layers_by_native_k": {str(k): count for k, count in sorted(new_vertical.items())},
               "rows": result_rows,
               "model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
               "limits": {"raw_number_physical_units_certified": False,
                          "named_process_attribution": False}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "residual", "support", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    result = produce(args.control, args.residual, args.support, args.output)
    print(json.dumps({"status": "CONTROL_WITNESSES_CAPTURED", "profiles": result["profile_count"],
                      "repair_counts": result["control_repair_layer_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
