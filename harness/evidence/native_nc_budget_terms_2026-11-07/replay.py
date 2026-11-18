#!/usr/bin/env python3
"""Replay captured, applied NC state-update terms at a joint QG/BRS endpoint."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction as F
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_nc_nccn_applied_2026-11-07"
MANIFEST_SHA = "840ccfc0db69e98dee89b80a99a8308110f98895335a7209abf1e891ab352b88"
FIELDS = (
    "nc_before", "nraut", "nccol", "nracw", "niacw", "naacw", "cold_mask",
    "ninuc", "nfrzdtc", "pimlt_ni", "dtcld", "dnc_rate_sum", "dnc_amount",
    "nc_base", "nc_unclamped", "nc_clamped",
)
PRODUCER_FIELDS = ("nccol", "nracw", "niacw", "naacw")
LABELS = (
    ("baseline", "baseline", 0.0),
    ("qg_bg17_rel_1e-03_minus", "qg_bg17_rel", -0.001),
    ("qg_bg17_rel_1e-03_plus", "qg_bg17_rel", 0.001),
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(number: float) -> int:
    return int.from_bytes(struct.pack(">d", number), "big")


def f64(row: dict[str, str]) -> float:
    need(row["dtype"] == "f64", "captured term dtype")
    return struct.unpack(">d", int(row["raw_hex"], 16).to_bytes(8, "big"))[0]


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes(), why)


def npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as loaded:
        need(set(loaded.files) == {"state", "forcing", "xland", "output"}, "NPZ inventory")
        data = {key: loaded[key].copy() for key in loaded.files}
    for key, shape, dtype in (
        ("state", (12, 39), np.float64), ("forcing", (4, 39), np.float64),
        ("xland", (1,), np.float32), ("output", (12, 39), np.float64),
    ):
        need(data[key].shape == shape and data[key].dtype == dtype
             and np.isfinite(data[key]).all(), "NPZ numeric contract: " + key)
    return data


def rows(raw: bytes) -> list[dict[str, str]]:
    need(b"# schema=kdm6.ice_number_applied.native.v1;" in raw[:300], "capture schema")
    need(raw.endswith(b"status=complete\n"), "complete capture")
    return list(csv.DictReader(line for line in io.StringIO(raw.decode()) if not line.startswith("#")))


def parent_module():
    spec = importlib.util.spec_from_file_location("nc_nccn_parent", PARENT / "replay.py")
    need(spec is not None and spec.loader is not None, "parent loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_budget_terms_packet.v1", "manifest schema")
    files = data["files"]
    actual = {str(path.relative_to(HERE)) for folder in ("raw", "producer", "executed_cpp")
              for path in (HERE / folder).rglob("*") if path.is_file()}
    need(set(files) == actual, "complete asset inventory")
    for name, digest in files.items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


def source(receipt: dict, build: dict) -> None:
    original = (PARENT / "executed_cpp/coordinator.cpp").read_bytes()
    executed = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    need(sha(original) == build["sha256"]["parent_coordinator_source"], "parent coordinator SHA")
    need(sha(executed) == build["sha256"]["instrumented_coordinator_source"]
         == receipt["coordinator_source_sha256"], "executed source receipt")
    additions = [line for line in executed.splitlines(keepends=True)
                 if b'capture_native_tensor("nc_budget",' in line
                 or b'capture_native_tensor("nc_budget_producer",' in line]
    stripped = b"".join(line for line in executed.splitlines(keepends=True)
                        if b'capture_native_tensor("nc_budget",' not in line
                        and b'capture_native_tensor("nc_budget_producer",' not in line)
    need(len(additions) == 20 and stripped == original,
         "twenty capture-only additions to parent coordinator")
    need({("nc_budget", field) for field in FIELDS}
         | {("nc_budget_producer", field) for field in PRODUCER_FIELDS}
         == {(line.split(b'"')[1].decode(), line.split(b'"')[3].decode())
             for line in additions}, "complete capture field list")
    for name, path in (
        ("runtime_source", "executed_cpp/runtime.cpp"),
        ("cmake_source", "executed_cpp/CMakeLists.txt"),
    ):
        raw = (HERE / path).read_bytes()
        need(sha(raw) == build["sha256"][name] and raw == (PARENT / path).read_bytes(),
             "parent source identity: " + name)
    for name, path in (
        ("instrumentation_patch", "executed_cpp/instrumentation.patch.gz"),
        ("cmake_cache", "raw/CMakeCache.txt.gz"),
        ("kdm6_flags", "raw/kdm6_flags.make.gz"),
    ):
        raw = gzip.decompress((HERE / path).read_bytes())
        need(sha(raw) == build["sha256"][name], "build metadata SHA: " + name)
        if name == "kdm6_flags":
            need(b"-ffp-contract=off" in raw, "executed no-contraction flags")
    need(receipt["library_sha256"] == build["sha256"]["dso"]
         and receipt["archive_sha256"] == build["sha256"]["archive"], "DSO/archive receipt")
    for name, path in (("evaluate_source_sha256", "producer/evaluate.py.txt"),
                       ("runner_source_sha256", "producer/run_terms.py.txt")):
        need(receipt[name] == sha((HERE / path).read_bytes()), "producer source receipt: " + name)


def case(record: dict, *, capture_override: tuple[str, bytes, str] | None) -> dict:
    label = record["label"]
    need(record["runs"]["on"]["returncode"] == record["runs"]["off"]["returncode"] == 0,
         "paired return code: " + label)
    local = HERE / "raw/cases"
    arrays = {}
    for mode in ("off", "on"):
        receipt = record["runs"][mode]
        path = local / f"{label}.{mode}.state_output.npz"
        need(sha(path.read_bytes()) == receipt["arrays_sha256"], "run NPZ SHA: " + label)
        arrays[mode] = npz(path)
        for stream in ("stdout", "stderr"):
            path = local / f"{label}.{mode}.{stream}.txt"
            need(sha(path.read_bytes()) == receipt[stream + "_sha256"], "run log SHA: " + label)
    parent_arrays = npz(PARENT / "raw/cases" / f"{label}.on.state_output.npz")
    for field in parent_arrays:
        exact(arrays["off"][field], arrays["on"][field], "capture off/on: " + label + "/" + field)
        exact(arrays["on"][field], parent_arrays[field], "parent output: " + label + "/" + field)
    raw = gzip.decompress((local / f"{label}.csv.gz").read_bytes())
    if capture_override is not None and capture_override[0] == label:
        raw = capture_override[1]
        need(sha(raw) == capture_override[2], "override SHA: " + label)
    else:
        need(sha(raw) == record["runs"]["on"]["capture_sha256"], "capture receipt SHA: " + label)
    captured = rows(raw)
    need(len(captured) == record["runs"]["on"]["capture_rows"] == 14781,
         "14781 captured rows: " + label)
    parent_raw = gzip.decompress((PARENT / "raw/cases" / f"{label}.csv.gz").read_bytes())
    parent_rows = rows(parent_raw)
    need(len(parent_rows) == 14001
         and [row for row in captured if row["stage"] not in ("nc_budget", "nc_budget_producer")] == parent_rows,
         "ordered parent capture preservation: " + label)
    fields = {}
    for row in captured:
        need(row["runtime_call"] == "1" and row["b_zero"] == "0"
             and row["B"] == "1" and row["K"] == "39", "capture call identity")
        k = int(row["k_zero"])
        need(0 <= k < 39, "capture level")
        key = row["stage"], row["field"], k
        need(key not in fields, "duplicate capture row")
        if row["stage"] in ("nc_budget", "nc_budget_producer"):
            need(row["one_step_call"] == "1" and row["substep"] == "0"
                 and row["field"] in (FIELDS if row["stage"] == "nc_budget" else PRODUCER_FIELDS)
                 and row["dtype"] == "f64", "NC budget row schema")
        fields[key] = row
    need(len(fields) == 14781, "unique captured rows")
    selected = {}
    positive_clamp_count = 0
    for k in range(39):
        def get(name: str) -> float:
            return f64(fields["nc_budget", name, k])
        def same(name: str, expected: float) -> None:
            need(word(get(name)) == word(expected), label + ": k=" + str(k) + ": " + name)

        n, c, w = get("nraut"), get("nccol"), get("nracw")
        need(word(n) == word(f64(fields["fd_d5", "nraut_applied", k])),
             "independent applied nraut handoff")
        for name in PRODUCER_FIELDS:
            need(word(get(name)) == word(f64(fields["nc_budget_producer", name, k])),
                 "independent applied " + name + " handoff")
        i, a, mask = get("niacw"), get("naacw"), get("cold_mask")
        need(mask in (0.0, 1.0) and get("dtcld") == 20.0, "NC branch mask and dt")
        rate = ((((-n - c) - w) - i * mask) - a) - a
        amount = (-get("ninuc") - get("nfrzdtc")) + get("pimlt_ni")
        base = get("nc_before") + amount
        raw_nc = base + rate * get("dtcld")
        clipped = max(raw_nc, 0.0)
        for name, expected in (("dnc_rate_sum", rate), ("dnc_amount", amount),
                               ("nc_base", base), ("nc_unclamped", raw_nc),
                               ("nc_clamped", clipped)):
            same(name, expected)
        need(word(get("nc_before")) == word(f64(fields["fd_state_update", "nc_before", k])),
             "NC budget input handoff")
        need(word(clipped) == word(f64(fields["fd_state_update", "nc_after", k])),
             "NC budget output handoff")
        positive_clamp_count += int(raw_nc < 0.0)
        if k == 23:
            selected = {name: get(name) for name in FIELDS}
            for stage, field in (("fd_warm", "nc"), ("fd_reclass", "nc"),
                                 ("fd_satadj_inner", "nc_input"),
                                 ("runtime_full_exit", "nc")):
                selected[stage + "." + field] = f64(fields[stage, field, k])
            need(word(selected["fd_warm.nc"]) == word(selected["nc_before"]),
                 "selected warm to state-update NC handoff")
            need(word(selected["fd_reclass.nc"]) == word(selected["nc_clamped"]),
                 "selected state-update to reclassification NC handoff")
            need(word(selected["fd_satadj_inner.nc_input"]) == word(selected["fd_reclass.nc"]),
                 "selected reclassification to activation NC handoff")
    return {"label": label, "selected_native16": selected,
            "negative_preclamp_levels": positive_clamp_count}


def difference(minus: dict, plus: dict) -> dict:
    m, p = minus["selected_native16"], plus["selected_native16"]
    before = F(p["nc_before"]) - F(m["nc_before"])
    after = F(p["nc_clamped"]) - F(m["nc_clamped"])
    contributions = {
        name: -F(20) * (F(p[name]) - F(m[name])) * multiplier
        for name, multiplier in (("nraut", 1), ("nccol", 1), ("nracw", 1),
                                 ("niacw", 0), ("naacw", 2))
    }
    need(m["cold_mask"] == p["cold_mask"] == 0.0
         and m["dnc_amount"] == p["dnc_amount"] == 0.0,
         "selected warm, zero-inline branch")
    need(m["nc_unclamped"] > 0.0 and p["nc_unclamped"] > 0.0,
         "selected nonclipping NC branch")
    residual = after - before - sum(contributions.values())
    need(after == F(p["runtime_full_exit.nc"]) - F(m["runtime_full_exit.nc"]),
         "selected NC difference propagated to final output")
    return {
        "nc_before_gap": float(before),
        "nc_after_gap": float(after),
        "applied_rate_contributions": {name: float(term) for name, term in contributions.items()},
        "stored_roundoff_residual": float(residual),
    }


def replay(*, capture_override: tuple[str, bytes, str] | None = None,
           receipt_override: tuple[bytes, str] | None = None) -> dict:
    manifest()
    parent_module().replay()
    raw = (HERE / "raw/run_receipt.json").read_bytes()
    if receipt_override is not None:
        raw = receipt_override[0]
        need(sha(raw) == receipt_override[1], "override receipt SHA")
    receipt = json.loads(raw)
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    need(receipt["schema"] == "kdm6.native_nc_budget_terms_paired.v1"
         and build["schema"] == "kdm6.native_nc_budget_terms_build.v1", "receipt schema")
    need(receipt["plan"] == {"qg_bg17_rel": [0.001]}, "prespecified joint plan")
    need([(item["label"], item["direction"], item["nominal_step"])
          for item in receipt["cases"]] == list(LABELS), "ordered signed endpoint plan")
    need(receipt["environment"] == {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
        "KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure",
        "KDM6AD_QNC_LIVE_GUARD": "1",
    }, "run environment")
    need(receipt["parent_npz_sha256"] == sha((HERE.parent /
         "native_nc16_vjp_branch_window_2026-11-06/raw/nc16_result.npz").read_bytes()),
         "native-state parent input SHA")
    if capture_override is not None:
        need(capture_override[0] in {item[0] for item in LABELS}, "known override label")
    source(receipt, build)
    results = [case(record, capture_override=capture_override) for record in receipt["cases"]]
    return {
        "schema": "kdm6.native_nc_budget_terms_results.v1",
        "calls": 3, "levels_per_call": 39,
        "negative_preclamp_levels_by_call": {
            result["label"]: result["negative_preclamp_levels"] for result in results
        },
        "native16": {result["label"]: result["selected_native16"] for result in results},
        "joint_endpoint_difference": difference(results[1], results[2]),
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
        print("verified 3 NC-budget paired calls x 39 levels")


if __name__ == "__main__":
    main()
