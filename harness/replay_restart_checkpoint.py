#!/usr/bin/env python3
"""Replay the retained G4 restart-checkpoint identity comparison.

This utility compares the native restart file against the parent's saved 20 s
history frame and the child's initial 20 s frame. It deliberately reports
history-only diagnostics separately from checkpoint-restored common state. It
does not inspect values after ``phy_init`` or claim to locate the 20→40 s
producer divergence.

The three NetCDF inputs are private run artifacts and are supplied explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


EXPECTED_CHECKPOINT_SHA256 = (
    "2ad545592a9a2a29afbaeb6eab7dcbca636f749c9060e814e8168470373b6a44"
)
EXPECTED_PARENT_T20 = "2025-07-19_00:00:20"
EXPECTED_CHILD_T20 = "2025-07-19_00:00:20"
EXPECTED_DIAGNOSTIC_DIFFERENCES = {
    "FOGFRAC_SFC",
    "NOAHRES",
    "REFL_10CM",
    "RHO_ICE",
    "VIS_SFC",
    "VIS_SFC_CAPPED",
    "VIS_SFC_RAW",
}
NEXT_STEP_STATE = (
    "ITIMESTEP",
    "STEPRA",
    "RADTACTTIME",
    "BLDTACTTIME",
    "CUDTACTTIME",
    "RTHRATEN",
    "RTHRATENLW",
    "RTHRATENSW",
    "RUBLTEN",
    "RVBLTEN",
    "RTHBLTEN",
    "SWDOWN",
    "GLW",
    "HFX",
    "LH",
    "TSK",
    "SMOIS",
    "SH2O",
    "CANWAT",
)


class ReplayError(ValueError):
    """The retained restart artifacts do not match the declared G4 case."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _time_strings(dataset: Dataset) -> list[str]:
    if "Times" not in dataset.variables:
        raise ReplayError(f"missing Times variable in {dataset.filepath()}")
    rows = np.asarray(dataset.variables["Times"][:])
    if rows.ndim != 2:
        raise ReplayError(f"Times must be rank 2, found {rows.shape}")
    return [b"".join(row.tolist()).decode("ascii").rstrip("\x00") for row in rows]


def _raw(variable: Any, index: int) -> tuple[np.ndarray, np.ndarray, str]:
    value = variable[index]
    mask = np.ma.getmaskarray(value)
    data = np.asarray(np.ma.getdata(value))
    if data.dtype.kind not in "fiu":
        raise ReplayError(f"expected numeric variable, found dtype {data.dtype}")
    mask_bytes = np.asarray(mask, dtype=np.uint8).tobytes(order="C")
    data_bytes = data.tobytes(order="C")
    payload = b"MASK\0" + mask_bytes + b"DATA\0" + data_bytes
    return data, np.frombuffer(payload, dtype=np.uint8), hashlib.sha256(payload).hexdigest()


def _frame_index(dataset: Dataset, expected: str) -> int:
    matches = [i for i, value in enumerate(_time_strings(dataset)) if value == expected]
    if len(matches) != 1:
        raise ReplayError(
            f"expected exactly one frame at {expected}, found {matches} "
            f"in {dataset.filepath()}"
        )
    return matches[0]


def _compare_checkpoint_frame(
    checkpoint: Dataset, history: Dataset, checkpoint_time_index: int,
    history_time_index: int,
) -> dict[str, Any]:
    common = sorted(set(checkpoint.variables) & set(history.variables) - {"Times"})
    rows: list[dict[str, Any]] = []
    nonnumeric: list[str] = []
    shape_mismatch: list[str] = []
    differing: list[str] = []
    for name in common:
        left_var, right_var = checkpoint.variables[name], history.variables[name]
        left = np.ma.asarray(left_var[checkpoint_time_index])
        right = np.ma.asarray(right_var[history_time_index])
        if left.dtype.kind not in "fiu" or right.dtype.kind not in "fiu":
            nonnumeric.append(name)
            continue
        if left.shape != right.shape or left.dtype != right.dtype:
            shape_mismatch.append(name)
            continue
        left_data, left_bytes, left_hash = _raw(left_var, checkpoint_time_index)
        right_data, right_bytes, right_hash = _raw(right_var, history_time_index)
        equal = np.array_equal(left_bytes, right_bytes)
        if not equal:
            differing.append(name)
        rows.append({
            "name": name,
            "shape": list(left_data.shape),
            "dtype_kind": left_data.dtype.kind,
            "left_sha256": left_hash,
            "right_sha256": right_hash,
            "raw_bit_equal": equal,
        })
    return {
        "numeric_common_count": len(rows),
        "numeric_raw_bit_equal_count": sum(row["raw_bit_equal"] for row in rows),
        "different_numeric_variables": differing,
        "shape_or_kind_mismatch": shape_mismatch,
        "nonnumeric_common_variables": nonnumeric,
        "per_variable": rows,
    }


def _history_pair(
    left: Dataset, right: Dataset, left_index: int, right_index: int,
) -> dict[str, Any]:
    common = sorted(set(left.variables) & set(right.variables) - {"Times"})
    equal: list[str] = []
    different: list[str] = []
    nonnumeric: list[str] = []
    shape_mismatch: list[str] = []
    for name in common:
        av, bv = left.variables[name], right.variables[name]
        a = np.ma.asarray(av[left_index])
        b = np.ma.asarray(bv[right_index])
        if a.dtype.kind not in "fiu" or b.dtype.kind not in "fiu":
            nonnumeric.append(name)
            continue
        if a.shape != b.shape or a.dtype != b.dtype:
            shape_mismatch.append(name)
            continue
        _, a_bytes, _ = _raw(av, left_index)
        _, b_bytes, _ = _raw(bv, right_index)
        (equal if np.array_equal(a_bytes, b_bytes) else different).append(name)
    return {
        "numeric_common_count": len(equal) + len(different),
        "raw_bit_equal_count": len(equal),
        "different_numeric_variables": different,
        "shape_or_kind_mismatch": shape_mismatch,
        "nonnumeric_common_variables": nonnumeric,
    }


def _checkpoint_scalars(checkpoint: Dataset) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in NEXT_STEP_STATE:
        if name not in checkpoint.variables:
            result[name] = {"present": False}
            continue
        data = np.asarray(checkpoint.variables[name][:])
        row: dict[str, Any] = {
            "present": True,
            "shape": list(data.shape),
            "dtype": str(data.dtype),
            "sha256": hashlib.sha256(data.tobytes(order="C")).hexdigest(),
        }
        if data.size == 1:
            val = data.item()
            row["value"] = int(val) if isinstance(val, np.integer) else float(val)
        else:
            row["finite_count"] = int(np.isfinite(data).sum())
        result[name] = row
    return result


def replay(checkpoint_path: Path, parent_history_path: Path,
           child_history_path: Path) -> dict[str, Any]:
    for path in (checkpoint_path, parent_history_path, child_history_path):
        if not path.is_file():
            raise ReplayError(f"required file is absent: {path}")
    checkpoint_sha = _sha256(checkpoint_path)
    if checkpoint_sha != EXPECTED_CHECKPOINT_SHA256:
        raise ReplayError(
            f"checkpoint digest mismatch: expected {EXPECTED_CHECKPOINT_SHA256}, "
            f"found {checkpoint_sha}"
        )
    with Dataset(checkpoint_path) as checkpoint, \
         Dataset(parent_history_path) as parent, \
         Dataset(child_history_path) as child:
        cp_times = _time_strings(checkpoint)
        if cp_times != [EXPECTED_PARENT_T20]:
            raise ReplayError(f"unexpected checkpoint Times: {cp_times}")
        parent_index = _frame_index(parent, EXPECTED_PARENT_T20)
        child_index = _frame_index(child, EXPECTED_CHILD_T20)
        if set(parent.variables) != set(child.variables):
            raise ReplayError("parent and child history variable sets differ")
        checkpoint_index = 0
        restored_parent = _compare_checkpoint_frame(
            checkpoint, parent, checkpoint_index, parent_index
        )
        restored_child = _compare_checkpoint_frame(
            checkpoint, child, checkpoint_index, child_index
        )
        initial_history = _history_pair(parent, child, parent_index, child_index)
        if restored_parent["numeric_common_count"] != 235 \
                or restored_child["numeric_common_count"] != 235:
            raise ReplayError("expected 235 common numeric checkpoint variables")
        if restored_parent["different_numeric_variables"] \
                or restored_child["different_numeric_variables"]:
            raise ReplayError("checkpoint/common frame raw-bit comparison failed")
        if restored_parent["shape_or_kind_mismatch"] \
                or restored_child["shape_or_kind_mismatch"]:
            raise ReplayError("checkpoint/common frame schema differs")
        if initial_history["numeric_common_count"] != 253:
            raise ReplayError("expected 253 common numeric history variables")
        if set(initial_history["different_numeric_variables"]) \
                != EXPECTED_DIAGNOSTIC_DIFFERENCES:
            raise ReplayError(
                "unexpected 20 s history differences: "
                f"{initial_history['different_numeric_variables']}"
            )
        if initial_history["raw_bit_equal_count"] != 246 \
                or initial_history["shape_or_kind_mismatch"]:
            raise ReplayError("unexpected t20 history comparison result")
        alarm_state = {
            name: (
                checkpoint.getncattr(name).item()
                if isinstance(checkpoint.getncattr(name), np.generic)
                else checkpoint.getncattr(name)
            )
            for name in checkpoint.ncattrs()
            if name == "MAX_WRF_ALARMS"
            or name.startswith("WRF_ALARM_ISRINGING_")
            or name.startswith("WRF_ALARM_SECS_TIL_NEXT_RING_")
        }
        return {
            "schema": "g4-restart-checkpoint-rawbit-replay-v1",
            "scope": {
                "status": "checkpoint_and_initial_history_only",
                "first_rk_producer_localized": False,
                "phy_init_poststate_measured": False,
                "cause_claimed": None,
            },
            "inputs": {
                "checkpoint_name": checkpoint_path.name,
                "checkpoint_sha256": checkpoint_sha,
                "parent_history_name": parent_history_path.name,
                "parent_history_sha256": _sha256(parent_history_path),
                "child_history_name": child_history_path.name,
                "child_history_sha256": _sha256(child_history_path),
                "checkpoint_time": cp_times[0],
                "parent_history_time": EXPECTED_PARENT_T20,
                "child_initial_time": EXPECTED_CHILD_T20,
            },
            "checkpoint_to_parent_t20": restored_parent,
            "checkpoint_to_child_initial_t20": restored_child,
            "parent_to_child_initial_t20": initial_history,
            "checkpoint_next_step_state": _checkpoint_scalars(checkpoint),
            "checkpoint_alarm_state": dict(sorted(alarm_state.items())),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("parent_history", type=Path)
    parser.add_argument("child_history", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = replay(args.checkpoint, args.parent_history, args.child_history)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "checkpoint_to_parent_equal": result["checkpoint_to_parent_t20"]["numeric_raw_bit_equal_count"],
        "checkpoint_to_child_equal": result["checkpoint_to_child_initial_t20"]["numeric_raw_bit_equal_count"],
        "history_differences": result["parent_to_child_initial_t20"]["different_numeric_variables"],
        "first_rk_producer_localized": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
