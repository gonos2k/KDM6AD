#!/usr/bin/env python3
"""Replay selected NC rate producers and cloud-number limiter handoffs."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_nc_budget_terms_2026-11-07"
MANIFEST_SHA = "af7aba15cef316cb02898451ac69561cd41641b04ead8fa5e0288a6c8e0996fa"
LABELS = (("baseline", "baseline", 0.0),
          ("qg_bg17_rel_1e-03_minus", "qg_bg17_rel", -0.001),
          ("qg_bg17_rel_1e-03_plus", "qg_bg17_rel", 0.001))
PRODUCER_NR = ("nc", "nr", "qr", "lenconcr", "avedia_r", "rslopec3",
               "rslope3_r", "nracw", "ncrk1", "ncrk2", "g3pmc", "g6pmc",
               "g4pmr", "g1pmr", "g7pmr", "di100", "dtcld")
PRODUCER_NA = ("qs", "qg", "nsacw", "ngacw", "naacw", "qsum_floor")
LIMIT_COLD = ("gate", "nc", "ncmin", "nraut_before", "nccol_before",
              "niacw_before", "source_sum", "nracw_before", "naacw_before",
              "nracw_after", "naacw_after")
LIMIT_WARM = ("gate", "nc", "ncmin", "nraut_before", "nccol_before",
              "source_sum", "nracw_before", "naacw_before",
              "nracw_after", "naacw_after")
NEW_FIELDS = {"nracw_producer": PRODUCER_NR, "naacw_producer": PRODUCER_NA,
              "nc_limit_cold": LIMIT_COLD, "nc_limit_warm": LIMIT_WARM}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> int:
    return int.from_bytes(struct.pack(">d", value), "big")


def f64(row: dict[str, str]) -> float:
    need(row["dtype"] == "f64", "f64 capture dtype")
    return struct.unpack(">d", int(row["raw_hex"], 16).to_bytes(8, "big"))[0]


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
    spec = importlib.util.spec_from_file_location("nc_budget_parent", PARENT / "replay.py")
    need(spec is not None and spec.loader is not None, "parent loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_rate_producer_packet.v1", "manifest schema")
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
         == receipt["coordinator_source_sha256"], "executed source receipt")
    additions = [line for line in executed.splitlines(keepends=True)
                 if any((f'capture_native_tensor("{stage}",').encode() in line
                        for stage in NEW_FIELDS)]
    stripped = b"".join(line for line in executed.splitlines(keepends=True)
                        if line not in additions)
    need(len(additions) == 44 and stripped == parent, "44 capture-only source additions")
    captured = {(line.split(b'"')[1].decode(), line.split(b'"')[3].decode())
                for line in additions}
    need(captured == {(stage, field) for stage, names in NEW_FIELDS.items()
                      for field in names}, "complete source capture fields")
    for name, path in (("runtime_source", "executed_cpp/runtime.cpp"),
                       ("cmake_source", "executed_cpp/CMakeLists.txt")):
        raw = (HERE / path).read_bytes()
        need(sha(raw) == build["sha256"][name] and raw == (PARENT / path).read_bytes(),
             "parent source identity: " + name)
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
                      ("runner_source_sha256", "producer/run_rates.py.txt")):
        need(receipt[key] == sha((HERE / path).read_bytes()), "producer source receipt")


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
    need(len(captured) == record["runs"]["on"]["capture_rows"] == 16497,
         "16497 captured rows: " + label)
    parent_raw = gzip.decompress((PARENT / "raw/cases" / f"{label}.csv.gz").read_bytes())
    parent_rows = capture_rows(parent_raw)
    need(len(parent_rows) == 14781
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
                 and row["dtype"] == ("bool" if row["field"] == "gate" else "f64"),
                 "producer/limiter row schema")
        data[key] = row
    need(len(data) == 16497, "unique capture rows")
    selected = {}
    limit_active = {"cold": 0, "warm": 0}
    producer_modes = {"big_drop": 0, "rain_active": 0, "qsum_active": 0}
    for k in range(39):
        def v(stage: str, name: str) -> float:
            return f64(data[stage, name, k])
        def same(stage: str, name: str, expected: float) -> None:
            need(word(v(stage, name)) == word(expected),
                 label + ": k=" + str(k) + ": " + stage + "." + name)

        stage = "nracw_producer"
        nc, nr = v(stage, "nc"), v(stage, "nr")
        sc, sr = v(stage, "rslopec3"), v(stage, "rslope3_r")
        ratio4 = v(stage, "g4pmr") / v(stage, "g1pmr")
        ratio7 = v(stage, "g7pmr") / v(stage, "g1pmr")
        big_drop = v(stage, "avedia_r") >= v(stage, "di100")
        rain_active = v(stage, "qr") >= v(stage, "lenconcr")
        mode1 = ((v(stage, "ncrk1") * nc) * nr) * (
            (sc * v(stage, "g3pmc")) + (sr * ratio4))
        mode2 = (((v(stage, "ncrk2") * nc) * nr) * (
            (sc * sc * v(stage, "g6pmc")) + (sr * sr))) * ratio7
        nr_raw = mode1 if big_drop else mode2
        nr_capped = min(nr_raw, nc / v(stage, "dtcld"))
        same(stage, "nracw", nr_capped if rain_active else 0.0)
        producer_modes["big_drop"] += int(big_drop)
        producer_modes["rain_active"] += int(rain_active)

        stage = "naacw_producer"
        qs, qg = v(stage, "qs"), v(stage, "qg")
        qsum = qs + qg
        qsum_active = qsum > v(stage, "qsum_floor")
        na_raw = ((qs * v(stage, "nsacw") + qg * v(stage, "ngacw"))
                  / max(qsum, v(stage, "qsum_floor")))
        same(stage, "naacw", na_raw if qsum_active else 0.0)
        producer_modes["qsum_active"] += int(qsum_active)

        for arm in ("cold", "warm"):
            stage = "nc_limit_" + arm
            gate_row = data[stage, "gate", k]
            need(gate_row["raw_hex"] in ("0", "1"), "limiter gate bit")
            gate = int(gate_row["raw_hex"])
            n, c = v(stage, "nraut_before"), v(stage, "nccol_before")
            w, a = v(stage, "nracw_before"), v(stage, "naacw_before")
            if arm == "cold":
                source_sum = ((((n + c) + w) + v(stage, "niacw_before")) + a) + a
            else:
                source_sum = (((n + c) + w) + a) + a
            same(stage, "source_sum", source_sum)
            value = max(v(stage, "nc"), v(stage, "ncmin"))
            source = source_sum * 20.0
            factor = value / max(source, value) if gate else 1.0
            for name in ("nracw", "naacw"):
                same(stage, name + "_after", v(stage, name + "_before") * factor)
            limit_active[arm] += int(gate and source > value)
            if k == 23:
                selected[stage] = {"gate": bool(gate), "source": source,
                                   "value": value, "factor": factor,
                                   "nracw_before": w, "nracw_after": v(stage, "nracw_after"),
                                   "naacw_before": a, "naacw_after": v(stage, "naacw_after")}
        for name in ("nracw", "naacw"):
            producer = name + "_producer"
            need(word(v(producer, name)) == word(v("nc_limit_cold", name + "_before")),
                 "rate producer to cold limiter: " + name)
            need(word(v("nc_limit_cold", name + "_after"))
                 == word(v("nc_limit_warm", name + "_before")),
                 "cold to warm limiter: " + name)
            need(word(v("nc_limit_warm", name + "_after"))
                 == word(v("nc_budget_producer", name))
                 == word(v("nc_budget", name)),
                 "warm limiter to NC budget: " + name)
        cold_gate = int(data["nc_limit_cold", "gate", k]["raw_hex"])
        warm_gate = int(data["nc_limit_warm", "gate", k]["raw_hex"])
        parent_mask = f64(data["nc_budget", "cold_mask", k])
        need(parent_mask in (0.0, 1.0) and cold_gate == int(parent_mask)
             and warm_gate == 1 - cold_gate, "limiter gates bound to NC budget cold mask")
        for arm in ("cold", "warm"):
            need(word(v("nc_limit_" + arm, "nc"))
                 == word(f64(data["nc_budget", "nc_before", k])),
                 "limiter NC reservoir bound to budget input")
        need(word(v("nc_limit_cold", "ncmin"))
             == word(v("nc_limit_warm", "ncmin")),
             "shared NC limiter floor")
        if k == 23:
            selected["nracw_producer"] = {name: v("nracw_producer", name)
                                            for name in PRODUCER_NR}
            selected["naacw_producer"] = {name: v("naacw_producer", name)
                                           for name in PRODUCER_NA}
            selected["producer_branches"] = {"big_drop": big_drop,
                                              "rain_active": rain_active,
                                              "nracw_cap_active": nr_raw > nc / v("nracw_producer", "dtcld"),
                                              "qsum_active": qsum_active}
    return {"label": label, "native16": selected,
            "limiter_active_levels": limit_active,
            "producer_branch_levels": producer_modes}


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
    need(receipt["schema"] == "kdm6.native_nc_rate_producers_paired.v1"
         and build["schema"] == "kdm6.native_nc_rate_producers_build.v1", "receipt schema")
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
    return {"schema": "kdm6.native_nc_rate_producer_results.v1",
            "calls": 3, "levels_per_call": 39,
            "native16": {r["label"]: r["native16"] for r in results},
            "limiter_active_levels_by_call": {
                r["label"]: r["limiter_active_levels"] for r in results},
            "producer_branch_levels_by_call": {
                r["label"]: r["producer_branch_levels"] for r in results},
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("verified 3 NC-rate producer calls x 39 levels")


if __name__ == "__main__":
    main()
