#!/usr/bin/env python3
"""Replay the captured NC/NCCN activation, return, and reservoir stores."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT_BRANCH = EVIDENCE / "native_fd_outlier_branches_2026-11-05"
PARENT_EXPANDED = EVIDENCE / "native_nc16_fd_expanded_2026-11-06"
MANIFEST_SHA = "a1aec8dfc95317df2294b0982091d2b915532de49203127939357a18ce96ace5"
NEW_FIELDS = {
    ("fd_satadj", "nccn_after"),
    ("fd_cleanup", "nccn"),
    ("fd_dsd", "nccn_before"),
    ("fd_dsd", "nccn_after"),
    ("fd_satadj_inner", "nccn_after_activation"),
    ("fd_satadj_inner", "nc_evap_amount"),
    ("fd_satadj_inner", "nccn_final_raw"),
    ("fd_satadj_inner", "nccn_floor_active"),
    ("fd_satadj_inner", "nccn_cap_active"),
    ("fd_satadj_inner", "nccn_final"),
}
DT = 20.0
NCCN_MIN = 1.0e8
NCCN_MAX = 2.0e10


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> int:
    return int.from_bytes(struct.pack(">d", value), "big")


def value(raw_hex: str) -> float:
    return struct.unpack(">d", int(raw_hex, 16).to_bytes(8, "big"))[0]


def f64(row: dict) -> float:
    need(row["dtype"] == "f64", "f64 capture dtype")
    return value(row["raw_hex"])


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), why)


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        need(set(data.files) == {"state", "forcing", "xland", "output"}, "NPZ fields")
        out = {key: data[key].copy() for key in data.files}
    for key, shape, dtype in (
        ("state", (12, 39), np.float64),
        ("forcing", (4, 39), np.float64),
        ("xland", (1,), np.float32),
        ("output", (12, 39), np.float64),
    ):
        need(out[key].shape == shape and out[key].dtype == dtype, "NPZ shape/dtype: " + key)
    return out


def rows_from(raw: bytes) -> list[dict[str, str]]:
    need(b"# schema=kdm6.ice_number_applied.native.v1;" in raw[:300], "capture schema")
    need(raw.endswith(b"status=complete\n"), "complete capture")
    rows = list(csv.DictReader(line for line in io.StringIO(raw.decode()) if not line.startswith("#")))
    need(len(rows) in (13611, 14001), "capture row count")
    return rows


def load_manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_nccn_applied_packet.v1", "manifest schema")
    files = data["files"]
    actual = {
        str(p.relative_to(HERE))
        for folder in ("raw", "producer", "executed_cpp")
        for p in (HERE / folder).rglob("*")
        if p.is_file()
    }
    need(set(files) == actual, "complete packet asset inventory")
    for path, digest in files.items():
        need(sha((HERE / path).read_bytes()) == digest, "asset SHA: " + path)
    return data


def verify_parent_manifests() -> None:
    for path in (PARENT_BRANCH, PARENT_EXPANDED):
        spec = importlib.util.spec_from_file_location("parent_" + path.name, path / "replay.py")
        need(spec is not None and spec.loader is not None, "parent replay loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.manifest()


def verify_source(receipt: dict, build: dict) -> None:
    parent = (PARENT_BRANCH / "executed_cpp/coordinator.cpp").read_bytes()
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    need(sha(parent) == build["sha256"]["parent_coordinator_source"], "parent coordinator SHA")
    need(sha(source) == build["sha256"]["instrumented_coordinator_source"], "instrumented coordinator SHA")
    need(receipt["coordinator_source_sha256"] == sha(source), "run/build source linkage")
    inserted = []
    old = []
    for line in source.splitlines(keepends=True):
        if b"capture_native_tensor(" in line and any(
            (f'"{stage}", "{field}"').encode() in line for stage, field in NEW_FIELDS
        ):
            inserted.append(line)
        else:
            old.append(line)
    need(len(inserted) == len(NEW_FIELDS) and b"".join(old) == parent,
         "capture-only coordinator source delta")
    need(sha(gzip.decompress((HERE / "executed_cpp/instrumentation.patch.gz").read_bytes())) == build["sha256"]["instrumentation_patch"], "instrumentation patch SHA")
    need(sha((HERE / "executed_cpp/runtime.cpp").read_bytes()) == build["sha256"]["runtime_source"], "runtime source SHA")
    need((HERE / "executed_cpp/runtime.cpp").read_bytes() == (PARENT_BRANCH / "executed_cpp/runtime.cpp").read_bytes(), "parent runtime source identity")
    need(sha((HERE / "executed_cpp/CMakeLists.txt").read_bytes()) == build["sha256"]["cmake_source"], "CMake source SHA")
    need((HERE / "executed_cpp/CMakeLists.txt").read_bytes() == (PARENT_BRANCH / "executed_cpp/CMakeLists.txt").read_bytes(), "parent CMake source identity")
    need(sha(gzip.decompress((HERE / "raw/CMakeCache.txt.gz").read_bytes())) == build["sha256"]["cmake_cache"], "CMake cache SHA")
    flags = gzip.decompress((HERE / "raw/kdm6_flags.make.gz").read_bytes())
    need(sha(flags) == build["sha256"]["kdm6_flags"] and b"-ffp-contract=off" in flags, "executed flags")
    need(receipt["library_sha256"] == build["sha256"]["dso"], "DSO receipt linkage")
    need(receipt["archive_sha256"] == build["sha256"]["archive"], "archive receipt linkage")
    need(receipt["evaluate_source_sha256"] == sha((HERE / "producer/evaluate.py.txt").read_bytes()), "producer linkage")
    need(receipt["runner_source_sha256"] == sha((HERE / "producer/run_transfer.py.txt").read_bytes()), "runner linkage")


def parent_paths(label: str) -> tuple[Path, str]:
    if label == "baseline":
        return PARENT_BRANCH, "baseline"
    if label.startswith("qv16_rel_"):
        return PARENT_BRANCH, label.replace("qv16_rel_", "qv_", 1)
    return PARENT_EXPANDED, label


def keyed(rows: list[dict[str, str]], label: str) -> dict[tuple[str, str, int], dict[str, str]]:
    out = {}
    for row in rows:
        need(
            row["runtime_call"] == "1" and row["b_zero"] == "0"
            and row["B"] == "1" and row["K"] == "39"
            and row["one_step_call"] in ("0", "1")
            and row["substep"] in ("0", "1")
            and (
                (row["one_step_call"] == "1" and row["substep"] == "0")
                if (row["stage"], row["field"]) in NEW_FIELDS else True
            ),
            "capture call identity: " + label,
        )
        k = int(row["k_zero"])
        need(0 <= k < 39, "capture level: " + label)
        key = row["stage"], row["field"], k
        need(key not in out, "duplicate capture row: " + label)
        out[key] = row
    return out


def check_case(case: dict, *, capture_override: tuple[str, bytes, str] | None) -> dict:
    label = case["label"]
    need(case["runs"]["off"]["returncode"] == case["runs"]["on"]["returncode"] == 0,
         "paired return codes: " + label)
    root = HERE / "raw/cases"
    arrays = {}
    for mode in ("off", "on"):
        path = root / f"{label}.{mode}.state_output.npz"
        need(sha(path.read_bytes()) == case["runs"][mode]["arrays_sha256"], "paired NPZ SHA: " + label)
        arrays[mode] = load_npz(path)
        for stream in ("stdout", "stderr"):
            raw = (root / f"{label}.{mode}.{stream}.txt").read_bytes()
            need(sha(raw) == case["runs"][mode][stream + "_sha256"], "paired log SHA: " + label)
    for field in arrays["on"]:
        exact(arrays["on"][field], arrays["off"][field], "capture off/on output: " + label + "/" + field)
        need(np.isfinite(arrays["on"][field]).all(), "finite paired array: " + label + "/" + field)
    parent_dir, parent_name = parent_paths(label)
    parent_npz = load_npz(parent_dir / "raw/cases" / (parent_name + ".npz"))
    for field in arrays["on"]:
        exact(arrays["on"][field], parent_npz[field], "parent value/forcing: " + label + "/" + field)
    cap_path = root / (label + ".csv.gz")
    cap = gzip.decompress(cap_path.read_bytes())
    if capture_override is not None and capture_override[0] == label:
        cap = capture_override[1]
        need(sha(cap) == capture_override[2], "override SHA: " + label)
    else:
        need(sha(cap) == case["runs"]["on"]["capture_sha256"], "capture receipt SHA: " + label)
    rows = rows_from(cap)
    need(len(rows) == case["runs"]["on"]["capture_rows"] == 14001,
         "capture row count: " + label)
    parent_cap = gzip.decompress((parent_dir / "raw/cases" / (parent_name + ".csv.gz")).read_bytes())
    parent_rows = rows_from(parent_cap)
    need([row for row in rows if (row["stage"], row["field"]) not in NEW_FIELDS] == parent_rows,
         "ordered parent capture preservation: " + label)
    d = keyed(rows, label)
    need(len(d) == 14001, "unique capture rows: " + label)
    selected = {}
    max_transfer_roundoff = Fraction(0)
    max_store_roundoff = Fraction(0)
    floor_count = 0
    cap_count = 0
    evaporation_count = 0
    nonzero_evaporation_count = 0
    active_count = 0
    for k in range(39):
        def get(stage: str, field: str) -> float:
            return f64(d[stage, field, k])
        def same(stage: str, field: str, expected: float, why: str) -> None:
            need(word(get(stage, field)) == word(expected), label + ": k=" + str(k) + ": " + why)

        nc0 = get("fd_satadj_inner", "nc_input")
        nccn0 = get("fd_satadj_inner", "nccn_input")
        rate = get("fd_satadj_inner", "ncact")
        need(nc0 >= 0.0 and nccn0 >= 0.0 and rate >= 0.0 and rate * DT <= nccn0,
             label + ": observed nonnegative, NCCN-limited rate")
        active_count += int(rate != 0.0)
        nc1 = max(nc0 + rate * DT, 0.0)
        nccn1 = max(nccn0 - rate * DT, 0.0)
        same("fd_satadj_inner", "nc_after_activation", nc1, "NC activation store")
        same("fd_satadj_inner", "nccn_after_activation", nccn1, "NCCN activation store")
        mask = d["fd_satadj_inner", "cloud_complete_evap", k]
        need(mask["dtype"] == "bool" and mask["raw_hex"] in ("0", "1"), "evaporation mask")
        evap = nc1 * float(int(mask["raw_hex"]))
        nc_final = max(nc1 - evap, 0.0)
        nccn_raw = nccn1 + evap
        nccn_final = min(max(nccn_raw, NCCN_MIN), NCCN_MAX)
        same("fd_satadj_inner", "nc_evap_amount", evap, "NC complete evaporation")
        same("fd_satadj_inner", "nc_final", nc_final, "NC final")
        same("fd_satadj_inner", "nccn_final_raw", nccn_raw, "NCCN raw return")
        same("fd_satadj_inner", "nccn_final", nccn_final, "NCCN reservoir clamp")
        floor = int(nccn_raw < NCCN_MIN)
        cap = int(nccn_raw > NCCN_MAX)
        for name, expect in (("nccn_floor_active", floor), ("nccn_cap_active", cap)):
            flag = d["fd_satadj_inner", name, k]
            need(flag["dtype"] == "bool" and flag["raw_hex"] == str(expect), label + ": " + name)
        floor_count += floor
        cap_count += cap
        evaporation_count += int(mask["raw_hex"])
        nonzero_evaporation_count += int(evap != 0.0)
        same("fd_satadj", "nc_after", nc_final, "NC handoff")
        same("fd_satadj", "nccn_after", nccn_final, "NCCN handoff")
        same("fd_cleanup", "nc", get("fd_satadj", "nc_after"), "cleanup NC")
        same("fd_cleanup", "nccn", get("fd_satadj", "nccn_after"), "cleanup NCCN")
        same("fd_dsd", "nc_before", get("fd_cleanup", "nc"), "DSD NC input")
        same("fd_dsd", "nccn_before", get("fd_cleanup", "nccn"), "DSD NCCN input")
        same("fd_dsd", "nc_after", get("fd_dsd", "nc_before"), "DSD NC output")
        same("fd_dsd", "nccn_after", get("fd_dsd", "nccn_before"), "DSD NCCN output")
        same("fd_dsd", "nc_after", float(arrays["on"]["output"][8, 38-k]), "packed NC output")
        same("fd_dsd", "nccn_after", float(arrays["on"]["output"][7, 38-k]), "packed NCCN output")
        transfer_roundoff = (Fraction.from_float(nc1) - Fraction.from_float(nc0)) - (Fraction.from_float(nccn0) - Fraction.from_float(nccn1))
        store_roundoff = (Fraction.from_float(nc_final) + Fraction.from_float(nccn_raw)) - (Fraction.from_float(nc0) + Fraction.from_float(nccn0))
        max_transfer_roundoff = max(max_transfer_roundoff, abs(transfer_roundoff))
        max_store_roundoff = max(max_store_roundoff, abs(store_roundoff))
        if k == 23:
            selected = {
                "nc_input": nc0, "nccn_input": nccn0, "ncact": rate,
                "nc_after_activation": nc1, "nccn_after_activation": nccn1,
                "nc_evap_amount": evap, "nccn_final_raw": nccn_raw,
                "nc_final": nc_final, "nccn_final": nccn_final,
                "activation_departure": float(Fraction.from_float(nccn0) - Fraction.from_float(nccn1)),
                "reservoir_adjustment": float(Fraction.from_float(nccn_final) - Fraction.from_float(nccn_raw)),
                "floor_active": bool(floor), "cap_active": bool(cap),
                "activated_fraction": get("fd_satadj_inner", "activated_fraction"),
            }
    return {
        "label": label,
        "selected_native16": selected,
        "floor_levels": floor_count,
        "active_levels": active_count,
        "cap_levels": cap_count,
        "complete_evap_levels": evaporation_count,
        "nonzero_evaporation_levels": nonzero_evaporation_count,
        "max_abs_activation_pair_roundoff": float(max_transfer_roundoff),
        "max_abs_preclamp_store_roundoff": float(max_store_roundoff),
    }


def expected_cases(plan: dict) -> list[tuple[str, str, float]]:
    expected = [("baseline", "baseline", 0.0)]
    for direction in ("qv16_rel", "th16_abs", "nc16_rel", "qg_bg17_rel"):
        steps = plan[direction]
        for h in steps:
            for sign, side in ((-1, "minus"), (1, "plus")):
                expected.append((f"{direction}_{h:.0e}_{side}", direction, sign * h))
    return expected


def replay(*, capture_override: tuple[str, bytes, str] | None = None,
           receipt_override: tuple[bytes, str] | None = None) -> dict:
    load_manifest()
    verify_parent_manifests()
    receipt_raw = (HERE / "raw/run_receipt.json").read_bytes()
    if receipt_override is not None:
        receipt_raw = receipt_override[0]
        need(sha(receipt_raw) == receipt_override[1], "override receipt SHA")
    receipt = json.loads(receipt_raw)
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    need(receipt["schema"] == "kdm6.native_nc_nccn_paired_ledger.v1", "run receipt schema")
    need(build["schema"] == "kdm6.native_nc_nccn_transfer_build.v1", "build receipt schema")
    need(receipt["parent_npz_sha256"] == sha((EVIDENCE / "native_nc16_vjp_branch_window_2026-11-06/raw/nc16_result.npz").read_bytes()), "pinned native parent input")
    need(receipt["environment"] == {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
        "KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure",
        "KDM6AD_QNC_LIVE_GUARD": "1",
    }, "run environment")
    need(receipt["plan"] == {
        "qv16_rel": [0.001, 0.0001], "th16_abs": [0.01, 0.001],
        "nc16_rel": [0.0001], "qg_bg17_rel": [0.001],
    }, "prespecified capture plan")
    verify_source(receipt, build)
    cases = receipt["cases"]
    need([(case["label"], case["direction"], case["nominal_step"]) for case in cases]
         == expected_cases(receipt["plan"]), "complete ordered signed endpoint plan")
    if capture_override is not None:
        need(capture_override[0] in {case["label"] for case in cases}, "known override label")
    results = [check_case(case, capture_override=capture_override) for case in cases]
    return {
        "schema": "kdm6.native_nc_nccn_applied_results.v1",
        "calls": len(results), "levels_per_call": 39,
        "native16": {result["label"]: result["selected_native16"] for result in results},
        "max_abs_activation_pair_roundoff": max(result["max_abs_activation_pair_roundoff"] for result in results),
        "max_abs_preclamp_store_roundoff": max(result["max_abs_preclamp_store_roundoff"] for result in results),
        "floor_levels_by_call": {result["label"]: result["floor_levels"] for result in results},
        "active_levels_by_call": {result["label"]: result["active_levels"] for result in results},
        "cap_levels_by_call": {result["label"]: result["cap_levels"] for result in results},
        "complete_evap_levels_by_call": {result["label"]: result["complete_evap_levels"] for result in results},
        "nonzero_evaporation_levels_by_call": {result["label"]: result["nonzero_evaporation_levels"] for result in results},
        "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"verified {result['calls']} NC/NCCN paired f64 calls x {result['levels_per_call']} levels")


if __name__ == "__main__":
    main()
