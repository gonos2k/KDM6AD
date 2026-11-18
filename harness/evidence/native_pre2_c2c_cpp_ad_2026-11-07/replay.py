#!/usr/bin/env python3
"""Replay archived C++ local pre2→C2c→conditional-NC derivatives."""

from __future__ import annotations

import argparse
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
MANIFEST_SHA = "7adb77912422fdb63530ebae3cba43322d21e8fd9258577069da0932f0187392"
NAMES = ("rho", "brs", "avtg", "bvtg", "g3pbg", "pidn0g", "rslope3_g",
         "rslopeb_g", "nsacw", "ngacw", "naacw", "nc_budget")
BASE_CAPTURE = {
    "rho": ("pre2_producer", "rhox"), "brs": ("pre2_producer", "bg"),
    "avtg": ("pre2_producer", "avtg"), "bvtg": ("pre2_producer", "bvtg"),
    "g3pbg": ("pre2_producer", "g3pbg"), "pidn0g": ("pre2_producer", "pidn0g"),
    "rslope3_g": ("pre2_producer", "rslope3_g"),
    "rslopeb_g": ("pre2_producer", "rslopeb_g"),
    "nsacw": ("naacw_producer", "nsacw"),
    "ngacw": ("naacw_producer", "ngacw"),
    "naacw": ("naacw_producer", "naacw"),
    "nc_budget": ("nc_budget", "nc_clamped"),
}
DIRECTIONS = ("qg_relative", "brs_relative", "joint_relative")
STABLE_H = ("1e-05", "1e-06", "1e-07")


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> int:
    return int.from_bytes(struct.pack(">d", value), "big")


def f64(raw_hex: str) -> float:
    return struct.unpack(">d", int(raw_hex, 16).to_bytes(8, "big"))[0]


def parent_module():
    spec = importlib.util.spec_from_file_location("pre2_cpp_parent", PARENT / "replay.py")
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned packet manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_pre2_c2c_cpp_ad_packet.v1", "manifest schema")
    files = data["files"]
    actual = {str(path.relative_to(HERE)) for folder in ("raw", "cpp")
              for path in (HERE / folder).rglob("*") if path.is_file()}
    need(set(files) == actual, "complete asset inventory")
    for name, digest in files.items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


def source_and_receipts(build: dict, run: dict) -> None:
    need(build["schema"] == "kdm6.native_pre2_c2c_cpp_ad_build.v1"
         and run["schema"] == "kdm6.native_pre2_c2c_cpp_ad_run.v1", "receipt schemas")
    for name, path in (("main_source", "cpp/main.cpp"),
                       ("cmake_source", "cpp/CMakeLists.txt")):
        need(sha((HERE / path).read_bytes()) == build["sha256"][name],
             "runner source receipt: " + name)
    for name, path in (("cmake_cache", "raw/CMakeCache.txt.gz"),
                       ("compile_flags", "raw/compile_flags.make.gz")):
        raw = gzip.decompress((HERE / path).read_bytes())
        need(sha(raw) == build["sha256"][name], "build metadata receipt: " + name)
        if name == "compile_flags":
            need(b"-ffp-contract=off" in raw and b"-DNDEBUG" not in raw,
                 "AD runner no-contraction/assertion flags")
    parent_build = json.loads((PARENT / "raw/build_receipt.json").read_text())
    need(run["archive_sha256"] == build["sha256"]["linked_archive"]
         == parent_build["sha256"]["archive"], "actual linked static archive")
    need(run["executable_sha256"] == build["sha256"]["runner_executable"],
         "executed AD runner hash")
    parent_run = json.loads((PARENT / "raw/run_receipt.json").read_text())
    parent_capture = gzip.decompress((PARENT / "raw/cases/baseline.csv.gz").read_bytes())
    need(sha(parent_capture) == run["input_capture_sha256"]
         == parent_run["cases"][0]["runs"]["on"]["capture_sha256"],
         "selected baseline native-state capture")
    need(run["environment"] == {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
        "KDM6_ICE_FACTORIAL_MODE": "norm_actual", "KDM6_QR_TRANSPORT": "actual_departure",
        "KDM6AD_QNC_LIVE_GUARD": "1",
    } and run["returncode"] == 0, "AD execution environment/return code")


def parent_word(parent: dict, stage: str, name: str) -> int:
    row = parent[stage, name, 23]
    need(row["dtype"] == "f64", "selected captured f64 dtype")
    return int(row["raw_hex"], 16)


def selected_parent() -> dict:
    raw = gzip.decompress((PARENT / "raw/cases/baseline.csv.gz").read_bytes())
    rows = parent_module().rows(raw)
    out = {}
    for row in rows:
        if row["k_zero"] == "23":
            key = row["stage"], row["field"], 23
            need(key not in out, "duplicate selected parent field")
            out[key] = row
    return out


def validate_baseline(record: dict, parent: dict) -> None:
    need(record["output_order"] == list(NAMES), "12 named C++ stage outputs")
    base = record["baseline"]
    need(len(base["values"]) == len(base["raw_hex"]) == len(NAMES),
         "baseline output vector size")
    for name, value, raw in zip(NAMES, base["values"], base["raw_hex"]):
        need(math.isfinite(value) and word(value) == int(raw, 16),
             "baseline value/word roundtrip: " + name)
        stage, field = BASE_CAPTURE[name]
        need(int(raw, 16) == parent_word(parent, stage, field),
             "native baseline C++ output: " + name)
    qg = f64(parent["pre2_producer", "qg_input", 23]["raw_hex"])
    brs = f64(parent["pre2_producer", "brs_input", 23]["raw_hex"])
    need(qg > 1e-9 and brs > 1e-15 and 800 < qg / brs < 900,
         "selected pre2 active upper-interior baseline")
    need(f64(parent["nc_limit_warm", "source_sum", 23]["raw_hex"]) * 20
         < f64(parent["nc_budget", "nc_before", 23]["raw_hex"]),
         "selected no-scale NC limiter baseline")
    need(word(f64(parent["nc_budget", "nc_before", 23]["raw_hex"]))
         == word(f64(parent["c2c_number_inputs", "nc", 23]["raw_hex"])),
         "selected C2c NC to budget NC handoff")
    need(f64(parent["nc_budget", "cold_mask", 23]["raw_hex"]) == 0.0
         and f64(parent["nc_budget", "dnc_amount", 23]["raw_hex"]) == 0.0,
         "selected warm zero-inline NC budget")


def vjp_and_directions(record: dict, parent: dict) -> tuple[dict, dict]:
    base = record["baseline"]["values"]
    qg = f64(parent["pre2_producer", "qg_input", 23]["raw_hex"])
    brs = f64(parent["pre2_producer", "brs_input", 23]["raw_hex"])
    need(set(record["vjp_rows"]) == set(NAMES)
         and set(record["directions"]) == set(DIRECTIONS), "VJP/direction inventory")
    for name, row in record["vjp_rows"].items():
        need(len(row) == 2 and all(math.isfinite(x) for x in row),
             "finite two-input C++ VJP: " + name)
    expected_seed = {"qg_relative": [qg, 0.0], "brs_relative": [0.0, brs],
                     "joint_relative": [qg, brs]}
    diagnostics = {}
    branches = {}
    u = 2.0**-53
    for direction in DIRECTIONS:
        data = record["directions"][direction]
        seed = data["seed"]
        need(len(seed) == 2 and all(word(a) == word(b)
             for a, b in zip(seed, expected_seed[direction])), "relative seed: " + direction)
        jvp = data["jvp"]
        need(len(jvp) == len(NAMES) and all(math.isfinite(x) for x in jvp),
             "finite C++ JVP: " + direction)
        max_transpose = 0.0
        for name, j, base_value in zip(NAMES, jvp, base):
            terms = [g * v for g, v in zip(record["vjp_rows"][name], seed)]
            contraction = math.fsum(terms)
            tolerance = max(4 * u * sum(abs(t) for t in terms)
                            + 4 * math.ulp(contraction), 8 * math.ulp(base_value))
            gap = abs(j - contraction)
            need(gap <= tolerance, "C++ JVP/VJP transpose: " + direction + "/" + name)
            max_transpose = max(max_transpose, gap / tolerance)
        steps = data["finite_differences"]
        expected_steps = ({"0.0001", *STABLE_H} if direction != "joint_relative"
                          else {"0.001", *STABLE_H})
        need(set(steps) == expected_steps, "prespecified FD steps: " + direction)
        stable_max = 0.0
        key_signal_max = 0.0
        resolved_h1e5 = []
        unresolved_h1e5 = []
        all_signal_max = 0.0
        for h_text, endpoint in steps.items():
            high_input, low_input = endpoint["high_input"], endpoint["low_input"]
            high, low = endpoint["high"], endpoint["low"]
            need(len(high_input) == len(low_input) == 2
                 and len(high) == len(low) == len(NAMES), "FD endpoint dimensions")
            need(all(math.isfinite(v) for group in (high_input, low_input, high, low)
                     for v in group), "finite FD endpoint values")
            h = float(h_text)
            for i, (center, step) in enumerate(zip((qg, brs), seed)):
                need(word(high_input[i]) == word(center + step * h)
                     and word(low_input[i]) == word(center - step * h),
                     "represented FD input: " + direction + "/" + h_text)
            upper_rho_raw = high_input[0] / max(high_input[1], 1e-15)
            lower_rho_raw = low_input[0] / max(low_input[1], 1e-15)
            for observed, raw_rho in ((high[0], upper_rho_raw), (low[0], lower_rho_raw)):
                need(word(observed) == word(min(max(raw_rho, 100.0), 900.0)),
                     "FD endpoint ProgB density/clamp")
            high_cap = upper_rho_raw > 900.0
            low_cap = lower_rho_raw > 900.0
            crossing = h_text == "0.0001" and direction != "joint_relative"
            if crossing:
                need((high_cap, low_cap) == ((True, False) if direction == "qg_relative"
                                               else (False, True)), "recorded 900-cap crossing")
            else:
                need(not high_cap and not low_cap
                     and 800.0 < upper_rho_raw < 900.0
                     and 800.0 < lower_rho_raw < 900.0,
                     "fixed 800–900 density interval")
            for input_values, output_values in ((high_input, high), (low_input, low)):
                need(input_values[0] > 1e-9 and input_values[1] > 1e-15,
                     "active ProgB and slope FD endpoints")
                qc = f64(parent["c2c_number_inputs", "qc", 23]["raw_hex"])
                qs = f64(parent["c2c_number_inputs", "qs", 23]["raw_hex"])
                nc = f64(parent["c2c_number_inputs", "nc", 23]["raw_hex"])
                ncmin = f64(parent["c2c_number_inputs", "ncmin", 23]["raw_hex"])
                qcrmin = f64(parent["c2c_number_inputs", "qcrmin", 23]["raw_hex"])
                qsum_floor = f64(parent["c2c_number_inputs", "qsum_floor", 23]["raw_hex"])
                dt = f64(parent["c2c_number_inputs", "dtcld", 23]["raw_hex"])
                need(qc > qcrmin and qs > qcrmin and input_values[0] > qcrmin
                     and nc > ncmin and qs + input_values[0] > qsum_floor,
                     "fixed C2c species, number and qsum gates")
                need(0.0 < qs / max(qc, qcrmin) < 1.0
                     and 0.0 < input_values[0] / max(qc, qcrmin) < 1.0,
                     "fixed interior snow/graupel Wilt branches")
                need(0.0 < output_values[8] < nc / dt
                     and 0.0 < output_values[9] < nc / dt,
                     "fixed inactive individual C2c number caps")
                need(word(output_values[8]) == word(base[8]),
                     "fixed snow number-rate producer")
                need(output_values[8] > 0 and output_values[9] > 0
                     and all(output_values[i] > 0.0 for i in (5, 6, 7, 10, 11)),
                     "active C2c and NC FD endpoints")
                nc_before = f64(parent["nc_budget", "nc_before", 23]["raw_hex"])
                fixed = sum(f64(parent["nc_budget", name, 23]["raw_hex"])
                            for name in ("nraut", "nccol", "nracw"))
                need((fixed + 2 * output_values[10]) * 20 < nc_before,
                     "fixed-other-rate NC no-rescale domain")
                need(nc_before > 0.0 and output_values[11] > 0.0,
                     "fixed inactive NC output clamp")
            dx = [a - b for a, b in zip(high_input, low_input)]
            max_error = 0.0
            for i, name in enumerate(NAMES):
                observed = high[i] - low[i]
                predicted = math.fsum(g * delta for g, delta
                                      in zip(record["vjp_rows"][name], dx))
                residual = abs(observed - predicted) / max(1.0, abs(predicted))
                max_error = max(max_error, residual)
                if not crossing:
                    need(residual <= 1e-6,
                         "fixed-branch C++ FD/VJP: " + direction + "/" + h_text + "/" + name)
                    if h_text == "1e-05":
                        output_ulp = math.ulp(base[i])
                        observed_resolvable = abs(observed) > 32 * output_ulp
                        predicted_resolvable = abs(predicted) > 32 * output_ulp
                        need(observed_resolvable == predicted_resolvable,
                             "FD signal classification: " + direction + "/" + name)
                        if observed_resolvable:
                            resolved_h1e5.append(name)
                        else:
                            unresolved_h1e5.append(name)
                    if h_text == "1e-05" and observed_resolvable:
                        signal = abs(observed - predicted) / max(
                            abs(observed), abs(predicted), output_ulp)
                        need(signal <= 1e-6,
                             "independent resolved-output signal FD: " + direction + "/" + name)
                        all_signal_max = max(all_signal_max, signal)
                        if name in ("ngacw", "naacw", "nc_budget"):
                            key_signal_max = max(key_signal_max, signal)
            if not crossing:
                stable_max = max(stable_max, max_error)
            branches[h_text] = branches.get(h_text, {})
            branches[h_text][direction] = {"upper_cap_high": high_cap,
                                            "upper_cap_low": low_cap,
                                            "max_normalized_residual": max_error}
        diagnostics[direction] = {"max_transpose_fraction_of_roundoff_bound": max_transpose,
                                  "max_fixed_branch_normalized_fd_residual": stable_max,
                                  "max_key_signal_relative_fd_residual_h1e5": key_signal_max,
                                  "max_all_resolved_signal_relative_fd_residual_h1e5": all_signal_max,
                                  "resolved_outputs_h1e5": resolved_h1e5,
                                  "unresolved_outputs_h1e5": unresolved_h1e5}
    return diagnostics, branches


def replay(*, output_override: tuple[bytes, str] | None = None) -> dict:
    manifest()
    parent_module().replay()
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    source_and_receipts(build, run)
    archived = (HERE / "raw/cpp_result.json").read_bytes()
    if output_override is not None:
        archived = output_override[0]
        need(sha(archived) == output_override[1], "override output SHA")
    else:
        need(sha(archived) == run["output_sha256"], "archived C++ output receipt")
    record = json.loads(archived)
    need(record["schema"] == "kdm6.native_pre2_c2c_cpp_ad.v1", "C++ result schema")
    parent = selected_parent()
    validate_baseline(record, parent)
    diagnostics, branches = vjp_and_directions(record, parent)
    return {"schema": "kdm6.native_pre2_c2c_cpp_ad_results.v1",
            "baseline_outputs_raw_equal": len(NAMES),
            "input_order": ["postfreeze_pre2_qg16", "postfreeze_pre2_brs16"],
            "output_order": list(NAMES),
            "direction_names": list(DIRECTIONS),
            "branch_windows": branches,
            "portable_diagnostics": diagnostics,
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("verified conditional C++ pre2/C2c AD: 2 inputs, 12 outputs, 3 directions")


if __name__ == "__main__":
    main()
