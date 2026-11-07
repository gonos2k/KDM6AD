#!/usr/bin/env python3
"""Replay f64 C2c snow/graupel number-riming producers from captured operands."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_nc_rate_producer_2026-11-07"
MANIFEST_SHA = "96d27fd4f87aac11f5f9d7d6882fbba803bb4b8975e448645052a60f18f13117"
FIELDS = (
    "qc", "nc", "qs", "qg", "den", "denfac", "n0so", "n0sfac", "n0go", "n0c",
    "avtg", "g3pbg", "rslope3_s", "rslopeb_s", "rslopemu_s", "rslope3_g",
    "rslopeb_g", "rslopemu_g", "rslopec", "rslopecmu", "ncmin", "dtcld",
    "qcrmin", "muc", "g3pbs", "avts", "eacsc", "eacgc", "pi_f32", "qsum_floor",
)
# Fixed values of the executed default C2c parameter set in this archived call.
# g3pbs is the f32 rgmma result promoted to f64, not Python's math.gamma value.
STATIC_EXPECTED = {
    "dtcld": 20.0, "qcrmin": 1.0e-9, "muc": 2.0,
    "g3pbs": 3.013315439224243, "avts": 11.720000267028809,
    "eacsc": 1.0, "eacgc": 1.0,
    "pi_f32": 3.1415927410125732, "qsum_floor": 1.0e-15,
}
LABELS = (("baseline", "baseline", 0.0),
          ("qg_bg17_rel_1e-03_minus", "qg_bg17_rel", -0.001),
          ("qg_bg17_rel_1e-03_plus", "qg_bg17_rel", 0.001))


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(x: float) -> int:
    return int.from_bytes(struct.pack(">d", x), "big")


def f64(row: dict[str, str]) -> float:
    need(row["dtype"] == "f64", "f64 capture dtype")
    return struct.unpack(">d", int(row["raw_hex"], 16).to_bytes(8, "big"))[0]


def f32(x: float) -> float:
    return struct.unpack(">f", struct.pack(">f", x))[0]


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes(), why)


def npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        need(set(z.files) == {"state", "forcing", "xland", "output"}, "NPZ fields")
        data = {name: z[name].copy() for name in z.files}
    for name, shape, dtype in (("state", (12, 39), np.float64),
                               ("forcing", (4, 39), np.float64),
                               ("xland", (1,), np.float32),
                               ("output", (12, 39), np.float64)):
        need(data[name].shape == shape and data[name].dtype == dtype
             and np.isfinite(data[name]).all(), "NPZ shape/dtype/finite: " + name)
    return data


def capture_rows(raw: bytes) -> list[dict[str, str]]:
    need(b"# schema=kdm6.ice_number_applied.native.v1;" in raw[:300], "capture schema")
    need(raw.endswith(b"status=complete\n"), "complete capture")
    return list(csv.DictReader(line for line in io.StringIO(raw.decode()) if not line.startswith("#")))


def parent_module():
    spec = importlib.util.spec_from_file_location("c2c_parent", PARENT / "replay.py")
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_c2c_number_rates_packet.v1", "manifest schema")
    files = data["files"]
    actual = {str(path.relative_to(HERE)) for folder in ("raw", "producer", "executed_cpp")
              for path in (HERE / folder).rglob("*") if path.is_file()}
    need(set(files) == actual, "complete asset inventory")
    for name, digest in files.items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


def source(receipt: dict, build: dict) -> None:
    parent = (PARENT / "executed_cpp/coordinator.cpp").read_bytes()
    executed = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    need(sha(parent) == build["sha256"]["parent_coordinator_source"], "parent coordinator SHA")
    need(sha(executed) == build["sha256"]["instrumented_coordinator_source"]
         == receipt["coordinator_source_sha256"], "executed coordinator receipt")
    additions = [line for line in executed.splitlines(keepends=True)
                 if b'capture_native_tensor("c2c_number_inputs",' in line]
    stripped = b"".join(line for line in executed.splitlines(keepends=True)
                        if b'capture_native_tensor("c2c_number_inputs",' not in line)
    need(len(additions) == 30 and stripped == parent, "30 capture-only source additions")
    need({line.split(b'"')[3].decode() for line in additions} == set(FIELDS),
         "complete C2c input capture fields")
    for name, path, parent_path in (
        ("runtime_source", "executed_cpp/runtime.cpp", PARENT / "executed_cpp/runtime.cpp"),
        ("cmake_source", "executed_cpp/CMakeLists.txt", PARENT / "executed_cpp/CMakeLists.txt"),
        ("cold_source", "executed_cpp/cold.cpp", HERE.parents[2] / "libtorch/src/cold.cpp"),
        ("cold_header", "executed_cpp/cold.h", HERE.parents[2] / "libtorch/include/kdm6/cold.h"),
    ):
        raw = (HERE / path).read_bytes()
        need(sha(raw) == build["sha256"][name] and raw == parent_path.read_bytes(),
             "executed source identity: " + name)
    for name, path in (("instrumentation_patch", "executed_cpp/instrumentation.patch.gz"),
                       ("cmake_cache", "raw/CMakeCache.txt.gz"),
                       ("kdm6_flags", "raw/kdm6_flags.make.gz")):
        raw = gzip.decompress((HERE / path).read_bytes())
        need(sha(raw) == build["sha256"][name], "build metadata SHA: " + name)
        if name == "kdm6_flags":
            need(b"-ffp-contract=off" in raw, "no-contraction compile flags")
    need(receipt["library_sha256"] == build["sha256"]["dso"]
         and receipt["archive_sha256"] == build["sha256"]["archive"], "DSO/archive receipt")
    for key, path in (("evaluate_source_sha256", "producer/evaluate.py.txt"),
                      ("runner_source_sha256", "producer/run_c2c.py.txt")):
        need(receipt[key] == sha((HERE / path).read_bytes()), "producer source receipt")


def wilt(q: float, qc_safe: float) -> tuple[float, float]:
    ratio = q / qc_safe
    need(math.isfinite(ratio), "finite observed f64 Wilt ratio")
    clamped = min(max(ratio, 0.0), 1.0)
    return ratio, clamped * clamped


def number_rates(v) -> dict:
    qc, nc, qs, qg = (v(name) for name in ("qc", "nc", "qs", "qg"))
    qc_safe = max(qc, v("qcrmin"))
    snow_ratio, snow_wilt = wilt(qs, qc_safe)
    graupel_ratio, graupel_wilt = wilt(qg, qc_safe)
    prefix = f32(f32(f32(v("pi_f32") * f32(v("avts"))) * 0.25)
                 * f32(v("eacsc")))
    ns_raw = prefix
    for term in (v("n0so"), v("n0sfac"), v("n0c")):
        ns_raw *= term
    ns_raw /= v("muc") + 1.0
    for term in (v("g3pbs"), v("rslope3_s"), v("rslopeb_s"),
                 v("rslopemu_s"), v("rslopec"), v("rslopecmu"),
                 snow_wilt, v("denfac")):
        ns_raw *= term
    ng_raw = math.pi
    for term in (v("avtg"), 0.25, v("eacgc"), v("n0go"), v("n0c")):
        ng_raw *= term
    ng_raw /= v("muc") + 1.0
    for term in (v("g3pbg"), v("rslope3_g"), v("rslopeb_g"),
                 v("rslopemu_g"), v("rslopec"), v("rslopecmu"),
                 graupel_wilt, v("denfac")):
        ng_raw *= term
    cap = nc / v("dtcld")
    snow_gate = qs > v("qcrmin") and nc > v("ncmin")
    graupel_gate = qg > v("qcrmin") and nc > v("ncmin")
    return {
        "nsacw_raw": ns_raw, "ngacw_raw": ng_raw,
        "nsacw_capped": min(ns_raw, cap), "ngacw_capped": min(ng_raw, cap),
        "nsacw": min(ns_raw, cap) if snow_gate else 0.0,
        "ngacw": min(ng_raw, cap) if graupel_gate else 0.0,
        "snow_wilt_ratio": snow_ratio, "graupel_wilt_ratio": graupel_ratio,
        "snow_wilt_factor": snow_wilt, "graupel_wilt_factor": graupel_wilt,
        "nc_per_dt": cap, "snow_gate": snow_gate,
        "graupel_gate": graupel_gate,
        "snow_cap_active": snow_gate and ns_raw > cap,
        "graupel_cap_active": graupel_gate and ng_raw > cap,
        "nsacw_pref": prefix,
    }


def case(record: dict, capture_override: tuple[str, bytes, str] | None) -> dict:
    label = record["label"]
    need(record["runs"]["on"]["returncode"] == record["runs"]["off"]["returncode"] == 0,
         "paired return code: " + label)
    local = HERE / "raw/cases"
    arrays = {}
    for mode in ("off", "on"):
        run = record["runs"][mode]
        path = local / f"{label}.{mode}.state_output.npz"
        need(sha(path.read_bytes()) == run["arrays_sha256"], "NPZ receipt SHA")
        arrays[mode] = npz(path)
        for stream in ("stdout", "stderr"):
            path = local / f"{label}.{mode}.{stream}.txt"
            need(sha(path.read_bytes()) == run[stream + "_sha256"], "log receipt SHA")
    parent_arrays = npz(PARENT / "raw/cases" / f"{label}.on.state_output.npz")
    for name in parent_arrays:
        exact(arrays["off"][name], arrays["on"][name], "capture off/on: " + label + "/" + name)
        exact(arrays["on"][name], parent_arrays[name], "parent output: " + label + "/" + name)
    raw = gzip.decompress((local / f"{label}.csv.gz").read_bytes())
    if capture_override is not None and capture_override[0] == label:
        raw = capture_override[1]
        need(sha(raw) == capture_override[2], "override SHA")
    else:
        need(sha(raw) == record["runs"]["on"]["capture_sha256"], "capture receipt SHA")
    captured = capture_rows(raw)
    need(len(captured) == record["runs"]["on"]["capture_rows"] == 17667,
         "17667 captured rows: " + label)
    parent_raw = gzip.decompress((PARENT / "raw/cases" / f"{label}.csv.gz").read_bytes())
    parent_rows = capture_rows(parent_raw)
    need(len(parent_rows) == 16497
         and [row for row in captured if row["stage"] != "c2c_number_inputs"] == parent_rows,
         "ordered parent capture preservation: " + label)
    data = {}
    for row in captured:
        need(row["runtime_call"] == "1" and row["b_zero"] == "0"
             and row["B"] == "1" and row["K"] == "39", "capture call identity")
        k = int(row["k_zero"])
        need(0 <= k < 39, "capture level")
        key = row["stage"], row["field"], k
        need(key not in data, "duplicate capture row")
        if row["stage"] == "c2c_number_inputs":
            need(row["one_step_call"] == "1" and row["substep"] == "0"
                 and row["field"] in FIELDS and row["dtype"] == "f64",
                 "C2c input row schema")
        data[key] = row
    need(len(data) == 17667, "unique capture rows")
    selected = {}
    counts = {"snow_gate": 0, "graupel_gate": 0,
              "snow_cap": 0, "graupel_cap": 0}
    for k in range(39):
        def v(name: str) -> float:
            return f64(data["c2c_number_inputs", name, k])
        for name, expected in STATIC_EXPECTED.items():
            need(word(v(name)) == word(expected),
                 "fixed C2c parameter: " + name)
        need(v("dtcld") == 20.0 and v("den") > 0.0
             and v("qcrmin") > 0.0 and v("qc") >= 0.0,
             "observed f64 C2c numeric domain")
        computed = number_rates(v)
        for name in ("nsacw", "ngacw"):
            actual = f64(data["naacw_producer", name, k])
            need(word(computed[name]) == word(actual),
                 label + ": k=" + str(k) + ": " + name + " producer")
        for name, parent_name in (("qs", "qs"), ("qg", "qg")):
            need(word(v(name)) == word(f64(data["naacw_producer", parent_name, k])),
                 "C2c weighting input handoff: " + name)
        need(word(v("nc")) == word(f64(data["nracw_producer", "nc", k]))
             and word(v("ncmin")) == word(f64(data["nc_limit_cold", "ncmin", k])),
             "C2c NC and per-cell floor handoff")
        for name, key in (("snow_gate", "snow_gate"),
                          ("graupel_gate", "graupel_gate"),
                          ("snow_cap", "snow_cap_active"),
                          ("graupel_cap", "graupel_cap_active")):
            counts[name] += int(computed[key])
        if k == 23:
            selected = {"inputs": {name: v(name) for name in FIELDS},
                        "reconstructed": computed}
    return {"label": label, "selected_native16": selected,
            "branch_counts": counts}


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
    need(receipt["schema"] == "kdm6.native_c2c_number_rates_paired.v1"
         and build["schema"] == "kdm6.native_c2c_number_rates_build.v1", "receipt schema")
    need(receipt["plan"] == {"qg_bg17_rel": [0.001]}, "prespecified joint plan")
    need([(r["label"], r["direction"], r["nominal_step"])
          for r in receipt["cases"]] == list(LABELS), "ordered signed endpoint plan")
    need(receipt["parent_npz_sha256"] == sha((HERE.parent /
         "native_nc16_vjp_branch_window_2026-11-06/raw/nc16_result.npz").read_bytes()),
         "native-state parent input SHA")
    need(receipt["environment"] == {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
        "KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure",
        "KDM6AD_QNC_LIVE_GUARD": "1",
    }, "run environment")
    if capture_override is not None:
        need(capture_override[0] in {r[0] for r in LABELS}, "known override case")
    source(receipt, build)
    results = [case(r, capture_override) for r in receipt["cases"]]
    return {"schema": "kdm6.native_c2c_number_rates_results.v1",
            "calls": 3, "levels_per_call": 39,
            "native16": {r["label"]: r["selected_native16"] for r in results},
            "branch_counts_by_call": {r["label"]: r["branch_counts"] for r in results},
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("verified 3 native C2c number-rate calls x 39 levels")


if __name__ == "__main__":
    main()
