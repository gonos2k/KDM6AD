#!/usr/bin/env python3
"""Replay selected post-freeze ProgB/slope producers through C2c inputs."""

from __future__ import annotations

import argparse
import bisect
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
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_c2c_number_rates_2026-11-07"
PROGB_ARCHIVE = EVIDENCE / "native_d1_progb_ad_2026-11-04/executed_cpp/progb.cpp"
MANIFEST_SHA = "e8de2720761618c854c4873a288cb1b3f6204c1b68d8d2d37dd4cd0d99774fc4"
LABELS = (("baseline", "baseline", 0.0),
          ("qg_bg17_rel_1e-03_minus", "qg_bg17_rel", -0.001),
          ("qg_bg17_rel_1e-03_plus", "qg_bg17_rel", 0.001))
NEW_FIELDS = {
    "d234_boundary": ("qg_before", "brs_before", "qg_after", "brs_after"),
    "pre2_producer": ("qg_input", "brs_input", "den_input", "dend_input",
                      "progb_active", "graupel_slope_mask", "rhox", "bg",
                      "pidn0g", "avtg", "bvtg", "g3pbg", "rslopegbmax",
                      "rslope_g", "rslope2_g", "rslope3_g", "rslopeb_g",
                      "rslopemu_g"),
    "c2c_pre2_consumer": ("qg", "brs"),
}
BOOL_FIELDS = {("pre2_producer", "progb_active"),
               ("pre2_producer", "graupel_slope_mask")}
TABLE = (100., 200., 300., 400., 500., 600., 700., 800., 900.)
AVTG = (54.9153, 74.2262, 88.8313, 101.0411, 111.7359, 121.3625,
        130.1841, 138.3714, 146.0422)
BVTG = (.5446, .5375, .5339, .5316, .5299, .5286, .5275, .5266, .5258)


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


def same(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def near_ulps(a: float, b: float, max_ulps: int, why: str) -> int:
    need(math.isfinite(a) and math.isfinite(b) and a > 0.0 and b > 0.0,
         "positive finite ULP comparison: " + why)
    gap = abs(word(a) - word(b))
    need(gap <= max_ulps, why + ": ULP gap " + str(gap))
    return gap


def npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        need(set(z.files) == {"state", "forcing", "xland", "output"}, "NPZ fields")
        data = {key: z[key].copy() for key in z.files}
    for key, shape, dtype in (("state", (12, 39), np.float64),
                              ("forcing", (4, 39), np.float64),
                              ("xland", (1,), np.float32),
                              ("output", (12, 39), np.float64)):
        need(data[key].shape == shape and data[key].dtype == dtype
             and np.isfinite(data[key]).all(), "NPZ shape/dtype/finite: " + key)
    return data


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes(), why)


def rows(raw: bytes) -> list[dict[str, str]]:
    need(b"# schema=kdm6.ice_number_applied.native.v1;" in raw[:300], "capture schema")
    need(raw.endswith(b"status=complete\n"), "complete capture")
    return list(csv.DictReader(line for line in io.StringIO(raw.decode()) if not line.startswith("#")))


def parent_module():
    spec = importlib.util.spec_from_file_location("pre2_parent", PARENT / "replay.py")
    need(spec is not None and spec.loader is not None, "parent loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_c2c_pre2_upstream_packet.v1", "manifest schema")
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
                 if any((f'capture_native_tensor("{stage}",').encode() in line
                        for stage in NEW_FIELDS)]
    stripped = b"".join(line for line in executed.splitlines(keepends=True)
                        if not any((f'capture_native_tensor("{stage}",').encode() in line
                                   for stage in NEW_FIELDS))
    need(len(additions) == 24 and stripped == parent, "24 capture-only coordinator additions")
    need({(line.split(b'"')[1].decode(), line.split(b'"')[3].decode()) for line in additions}
         == {(stage, name) for stage, names in NEW_FIELDS.items() for name in names},
         "complete source capture fields")
    for name, path, reference in (
        ("runtime_source", "executed_cpp/runtime.cpp", PARENT / "executed_cpp/runtime.cpp"),
        ("cmake_source", "executed_cpp/CMakeLists.txt", PARENT / "executed_cpp/CMakeLists.txt"),
        ("progb_source", "executed_cpp/progb.cpp", PROGB_ARCHIVE),
        ("progb_header", "executed_cpp/progb.h", HERE.parents[2] / "libtorch/include/kdm6/progb.h"),
        ("slope_source", "executed_cpp/slope.cpp", HERE.parents[2] / "libtorch/src/slope.cpp"),
        ("slope_header", "executed_cpp/slope.h", HERE.parents[2] / "libtorch/include/kdm6/slope.h"),
    ):
        raw = (HERE / path).read_bytes()
        need(sha(raw) == build["sha256"][name] and raw == reference.read_bytes(),
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
                      ("runner_source_sha256", "producer/run_pre2.py.txt")):
        need(receipt[key] == sha((HERE / path).read_bytes()), "producer source receipt")


def interpolated(rho: float, values: tuple[float, ...]) -> tuple[float, int, int]:
    right = min(max(bisect.bisect_right(TABLE, rho), 1), 8)
    left = right - 1
    reciprocal = 1.0 / (TABLE[right] - TABLE[left])
    raw = values[left] + ((rho - TABLE[left]) * (values[right] - values[left])) * reciprocal
    if rho == TABLE[-1]:
        raw = values[-1]
    return raw, left, right


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
    for key in parent_arrays:
        exact(arrays["off"][key], arrays["on"][key], "capture off/on: " + label + "/" + key)
        exact(arrays["on"][key], parent_arrays[key], "parent output: " + label + "/" + key)
    raw = gzip.decompress((local / f"{label}.csv.gz").read_bytes())
    if capture_override is not None and capture_override[0] == label:
        raw = capture_override[1]
        need(sha(raw) == capture_override[2], "override SHA")
    else:
        need(sha(raw) == record["runs"]["on"]["capture_sha256"], "capture receipt SHA")
    captured = rows(raw)
    need(len(captured) == record["runs"]["on"]["capture_rows"] == 18603,
         "18603 captured rows: " + label)
    parent_rows = rows(gzip.decompress((PARENT / "raw/cases" / f"{label}.csv.gz").read_bytes()))
    need(len(parent_rows) == 17667
         and [row for row in captured if row["stage"] not in NEW_FIELDS] == parent_rows,
         "ordered parent capture preservation: " + label)
    data = {}
    for row in captured:
        need(row["runtime_call"] == "1" and row["b_zero"] == "0"
             and row["B"] == "1" and row["K"] == "39", "capture call identity")
        k = int(row["k_zero"])
        need(0 <= k < 39, "capture level")
        key = row["stage"], row["field"], k
        need(key not in data, "duplicate capture row")
        if row["stage"] in NEW_FIELDS:
            need(row["one_step_call"] == "1" and row["substep"] == "0"
                 and row["field"] in NEW_FIELDS[row["stage"]]
                 and row["dtype"] == ("bool" if (row["stage"], row["field"]) in BOOL_FIELDS else "f64"),
                 "postfreeze capture row schema")
        data[key] = row
    need(len(data) == 18603, "unique captured rows")
    selected = {}
    counts = {"progb_active": 0, "slope_unmasked": 0,
              "d234_qg_changed": 0, "d234_brs_changed": 0}
    portable_max = {"g3pbg": 0, "pidn0g": 0,
                    "rslope_g": 0, "rslope2_g": 0, "rslope3_g": 0,
                    "rslopeb_g": 0, "rslopegbmax": 0}
    for k in range(39):
        def v(stage: str, name: str) -> float:
            return f64(data[stage, name, k])
        def flag(name: str) -> int:
            row = data["pre2_producer", name, k]
            need(row["raw_hex"] in ("0", "1"), "postfreeze branch bit")
            return int(row["raw_hex"])
        same(v("d234_boundary", "qg_before"),
             v("d1_postmelt_progb", "qg"),
             "postmelt QG to D2-D4 entry")
        same(v("d234_boundary", "brs_before"),
             v("d1_brs_reslope", "brs_after"),
             "postmelt BRS reslope to D2-D4 entry")
        for name, input_name in (("qg_after", "qg_input"), ("brs_after", "brs_input")):
            same(v("d234_boundary", name), v("pre2_producer", input_name),
                 "D2-D4 to pre2 input: " + name)
        for name in ("qg", "brs"):
            same(v("c2c_pre2_consumer", name),
                 v("pre2_producer", "bg" if name == "brs" else "qg_input"),
                 "pre2 to C2c state: " + name)
        same(v("pre2_producer", "den_input"), v("c2c_number_inputs", "den"),
             "pre2 density to C2c")
        for name in ("qg", "avtg", "g3pbg", "rslope3_g", "rslopeb_g", "rslopemu_g"):
            same(v("pre2_producer", "qg_input" if name == "qg" else name),
                 v("c2c_number_inputs", name), "pre2 to C2c operand: " + name)
        qg, brs = v("pre2_producer", "qg_input"), v("pre2_producer", "brs_input")
        active = qg > 1.0e-9 or brs > 1.0e-15
        mask = qg <= 1.0e-9
        need(flag("progb_active") == int(active), "postfreeze ProgB active gate")
        need(flag("graupel_slope_mask") == int(mask), "postfreeze graupel slope mask")
        counts["progb_active"] += int(active)
        counts["slope_unmasked"] += int(not mask)
        for name in ("qg", "brs"):
            counts["d234_" + name + "_changed"] += int(
                word(v("d234_boundary", name + "_before"))
                != word(v("d234_boundary", name + "_after")))
        same(v("pre2_producer", "rslopemu_g"), 1.0, "recorded MUG=0 slope factor")
        if active:
            rho_raw = qg / max(brs, 1.0e-15)
            rho = min(max(rho_raw, 100.0), 900.0)
            same(v("pre2_producer", "rhox"), rho, "postfreeze density clamp")
            same(v("pre2_producer", "bg"), qg / rho, "postfreeze BRS return")
            avtg, left, right = interpolated(rho, AVTG)
            bvtg, _, _ = interpolated(rho, BVTG)
            same(v("pre2_producer", "avtg"), avtg, "postfreeze avtg interpolation")
            same(v("pre2_producer", "bvtg"), bvtg, "postfreeze bvtg interpolation")
            pid = ((math.pi * rho / 6.0) * 4.0e6) * 6.0
            portable_max["pidn0g"] = max(portable_max["pidn0g"], near_ulps(
                v("pre2_producer", "pidn0g"), pid, 4, "postfreeze pidn0g scalar"))
            g3 = math.exp(math.lgamma(3.0 + bvtg))
            portable_max["g3pbg"] = max(portable_max["g3pbg"], near_ulps(
                v("pre2_producer", "g3pbg"), g3, 16, "postfreeze g3pbg gamma"))
            rsmax = math.pow(1.0 / 180000.0, bvtg)
            portable_max["rslopegbmax"] = max(portable_max["rslopegbmax"], near_ulps(
                v("pre2_producer", "rslopegbmax"), rsmax, 8,
                "postfreeze rslopegbmax"))
            if not mask:
                den = v("pre2_producer", "dend_input")
                need(den > 0.0 and qg > 0.0, "positive graupel slope inputs")
                ratio = max(v("pre2_producer", "pidn0g")
                            / max(qg * den, 1.0e-30), 1.0e-30)
                lam = math.exp(math.log(ratio) * 0.25)
                rs = 1.0 / lam
                rs2 = rs * rs
                predictions = {"rslope_g": rs, "rslope2_g": rs2,
                               "rslope3_g": rs2 * rs,
                               "rslopeb_g": math.pow(max(rs, 1.0e-30), bvtg)}
                for name, pred in predictions.items():
                    portable_max[name] = max(portable_max[name], near_ulps(
                        v("pre2_producer", name), pred, 8,
                        "postfreeze active graupel slope: " + name))
            if k == 23:
                selected["density_raw"] = rho_raw
                selected["table_interval"] = [left, right]
                selected["rho_upper_margin"] = 900.0 - rho_raw
        if k == 23:
            selected.update({"d234": {name: v("d234_boundary", name)
                                      for name in NEW_FIELDS["d234_boundary"]},
                             "pre2": {name: flag(name) if ("pre2_producer", name) in BOOL_FIELDS
                                      else v("pre2_producer", name)
                                      for name in NEW_FIELDS["pre2_producer"]},
                             "c2c": {name: v("c2c_pre2_consumer", name)
                                     for name in NEW_FIELDS["c2c_pre2_consumer"]}})
            need(not mask and active and 800.0 < rho_raw < 900.0
                 and selected["table_interval"] == [7, 8],
                 "selected upper-interior active graupel branch")
            for name in ("qg", "brs"):
                same(v("d234_boundary", name + "_before"),
                     v("d234_boundary", name + "_after"),
                     "selected D2-D4 mass/volume unchanged")
    return {"label": label, "selected_native16": selected,
            "branch_counts": counts, "max_python_ulp_by_field": portable_max}


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
    need(receipt["schema"] == "kdm6.native_c2c_pre2_producers_paired.v1"
         and build["schema"] == "kdm6.native_c2c_pre2_upstream_build.v1", "receipt schema")
    need(receipt["plan"] == {"qg_bg17_rel": [0.001]}, "prespecified joint plan")
    need([(r["label"], r["direction"], r["nominal_step"])
          for r in receipt["cases"]] == list(LABELS), "ordered signed endpoint plan")
    need(receipt["parent_npz_sha256"] == sha((EVIDENCE /
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
    return {"schema": "kdm6.native_c2c_pre2_upstream_results.v1",
            "calls": 3, "levels_per_call": 39,
            "native16": {r["label"]: r["selected_native16"] for r in results},
            "branch_counts_by_call": {r["label"]: r["branch_counts"] for r in results},
            "max_python_ulp_by_call": {r["label"]: r["max_python_ulp_by_field"] for r in results},
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("verified 3 postfreeze pre2 producer calls x 39 levels")


if __name__ == "__main__":
    main()
