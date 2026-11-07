#!/usr/bin/env python3
"""Replay the archived full-call C++ AD bridge into post-D2–D4 pre2 inputs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
from functools import lru_cache

import numpy as np


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
NC16 = EVIDENCE / "native_nc16_vjp_branch_window_2026-11-06"
FD = EVIDENCE / "native_nc16_fd_expanded_2026-11-06"
LOCAL = EVIDENCE / "native_pre2_c2c_cpp_ad_2026-11-07"
LOCAL_CPP_SHA = "e8714b776afd9b21da03f20fe640dafc1640d4d07e97705e1a13fdbee46c83bb"
PARENT_REPLAY_SHA = {
    "fd": "0322ecba06c051913199042d2fe163fde0744876eb0065a3a81fe7b1bd9222d2",
    "pre2": "140f9a0b0fe1f9d89f534562e4ef71040feb55bbb89d28fcb949d237ce393b1c",
    "local": "db2d3adfb5ba890506f113d9f5e33388b6796b0df3c122312ea4caa90f1b2764",
}
MANIFEST_SHA = "7e3bba4706026c2162f9f165ee3a0db7980b34a674ababd225ef25985cbf2cfd"
QG17 = 6 * 39 + 16
BRS17 = 11 * 39 + 16
LEVEL16 = 15  # packed C ABI order; the capture calls this k_zero=23
DIRECTIONS = {
    "qg17_relative": ("qg17_rel", QG17, (True, False)),
    "brs17_relative": ("bg17_rel", BRS17, (False, True)),
    "joint17_relative": ("qg_bg17_rel", None, (True, True)),
}
STEPS = {"0.001": "1e-03", "0.0001": "1e-04", "1e-05": "1e-05"}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(x: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(x)))[0], "016x")


def words(array: np.ndarray) -> list[str]:
    return [format(int(v), "016x") for v in np.asarray(array, dtype="<f8").reshape(-1).view("<u8")]


def fixed_manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    manifest = json.loads(raw)
    need(manifest["schema"] == "kdm6.native_pre2_input_cpp_ad_packet.v1", "manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "cpp", "executed_cpp", "producer")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(manifest["files"]) == actual, "packet file inventory")
    for name, digest in manifest["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "packet asset SHA: " + name)


@lru_cache(maxsize=1)
def verified_parent_replays() -> tuple[dict, dict, dict]:
    summaries = []
    for key, folder in (("fd", FD), ("pre2", PRE2), ("local", LOCAL)):
        source = folder / "replay.py"
        need(sha(source.read_bytes()) == PARENT_REPLAY_SHA[key], "pinned parent replay: " + key)
        spec = importlib.util.spec_from_file_location("native_pre2_input_parent_" + key, source)
        need(spec is not None and spec.loader is not None, "parent replay loader: " + key)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        summaries.append(module.replay())
    need(summaries[0]["calls"] == 37 and summaries[1]["calls"] == 3,
         "verified FD/pre2 parent call counts")
    need(summaries[2]["baseline_outputs_raw_equal"] == 12,
         "verified local C2c AD parent")
    return summaries[0], summaries[1], summaries[2]


def provenance(result_raw: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_pre2_input_cpp_ad_build.v1", "build receipt schema")
    need(run["schema"] == "kdm6.native_pre2_input_cpp_ad_run.v1" and run["returncode"] == 0,
         "run receipt schema/status")
    checks = {
        "runner_source": HERE / "cpp/main.cpp",
        "runner_cmake": HERE / "cpp/CMakeLists.txt",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "parent_coordinator": PRE2 / "executed_cpp/coordinator.cpp",
        "input_binary": HERE / "raw/input.bin",
        "output_json": HERE / "raw/cpp_result.json",
    }
    for name, path in checks.items():
        need(sha(path.read_bytes()) == build["sha256"][name], "build asset SHA: " + name)
    need(run["output_sha256"] == sha(result_raw)
         == build["sha256"]["output_json"], "run output SHA")
    need(run["input_sha256"] == build["sha256"]["input_binary"], "run input SHA")
    need(run["archive_sha256"] == build["sha256"]["library_archive"], "run archive SHA")
    need(run["executable_sha256"] == build["sha256"]["runner_executable"], "run executable SHA")
    need(run["environment"] == {
        "KDM6AD_QNC_LIVE_GUARD": "1", "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
        "KDM6_QR_TRANSPORT": "actual_departure", "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1"}, "run controls")
    runner_flags = gzip.decompress((HERE / "raw/runner_flags.make.gz").read_bytes()).decode()
    library_flags = gzip.decompress((HERE / "raw/library_flags.make.gz").read_bytes()).decode()
    core_flags = gzip.decompress((HERE / "raw/core_flags.make.gz").read_bytes()).decode()
    need(sha(runner_flags.encode()) == build["sha256"]["runner_flags"], "runner flags SHA")
    need(sha(library_flags.encode()) == build["sha256"]["library_flags"], "library flags SHA")
    need(sha(core_flags.encode()) == build["sha256"]["core_flags"], "core target flags SHA")
    need("-ffp-contract=off" in runner_flags and "-DNDEBUG" not in runner_flags,
         "runner f64/assertion flags")
    need("-ffp-contract=off" in library_flags and "KDM6_NATIVE_SCALAR_CAPTURE" in library_flags,
         "bridge f64/capture flags")
    need("-ffp-contract=off" in core_flags and "KDM6_NATIVE_SCALAR_CAPTURE" in core_flags,
         "coordinator/runtime f64/capture flags")
    cache = gzip.decompress((HERE / "raw/runner_cache.txt.gz").read_bytes())
    need(sha(cache) == build["sha256"]["runner_cache"], "runner cache SHA")
    need("-ffp-contract=off" in (HERE / "cpp/CMakeLists.txt").read_text(), "runner CMake FP contract")

    # Removing the three opt-in hook insertions restores the #553 executed source.
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    parent = (PRE2 / "executed_cpp/coordinator.cpp").read_bytes()
    blocks = (
        b"#include <utility>\n",
        b"// Isolated evidence hook: retain the post-D2-D4 pre2 inputs as live tensors.\n"
        b"namespace testing {\n"
        b"thread_local bool pre2_input_hook_enabled = false;\n"
        b"thread_local torch::Tensor pre2_input_qg;\n"
        b"thread_local torch::Tensor pre2_input_brs;\n"
        b"void enable_pre2_input_hook(bool enabled) {\n"
        b"    pre2_input_hook_enabled = enabled;\n"
        b"    pre2_input_qg = torch::Tensor();\n"
        b"    pre2_input_brs = torch::Tensor();\n"
        b"}\n"
        b"std::pair<torch::Tensor, torch::Tensor> pre2_input_hook_values() {\n"
        b"    TORCH_CHECK(pre2_input_qg.defined() && pre2_input_brs.defined(), \"pre2 hook not populated\");\n"
        b"    return {pre2_input_qg, pre2_input_brs};\n"
        b"}\n"
        b"}  // namespace testing\n",
        b"    if (testing::pre2_input_hook_enabled) {\n"
        b"        testing::pre2_input_qg = working.qg;\n"
        b"        testing::pre2_input_brs = working.brs;\n"
        b"    }\n",
    )
    for block in blocks:
        need(source.count(block) == 1, "unique graph hook insertion")
        source = source.replace(block, b"", 1)
    need(source == parent, "graph hook source restores parent")
    need(b"working.qg" in blocks[2] and b"working.brs" in blocks[2], "live pre2 inputs")


def parent_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(NC16 / "raw/nc16_result.npz", allow_pickle=False) as z:
        state, forcing, xland = (z[k].copy() for k in ("state", "forcing", "xland"))
    need(state.shape == (12, 39) and state.dtype == np.float64, "parent state shape")
    need(forcing.shape == (4, 39) and forcing.dtype == np.float64, "parent forcing shape")
    need(xland.shape == (1,) and xland.dtype == np.float32, "parent xland shape")
    expected = (b"KDM6_PRE2_INPUT" + state.astype("<f8", copy=False).tobytes()
                + forcing.astype("<f8", copy=False).tobytes()
                + xland.astype("<f4", copy=False).tobytes() + struct.pack("<d", 20.0))
    need((HERE / "raw/input.bin").read_bytes() == expected, "input binary/parent NPZ")
    return state, forcing, xland


def capture(label: str) -> list[dict[str, str]]:
    path = PRE2 / "raw/cases" / (label + ".csv.gz")
    raw = gzip.decompress(path.read_bytes()).decode()
    need(raw.endswith("status=complete\n"), "complete pre2 capture: " + label)
    return list(csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#")))


def pre2_words(rows: list[dict[str, str]], field: str) -> list[str]:
    selected = [r for r in rows if r["stage"] == "pre2_producer" and r["field"] == field]
    need(len(selected) == 39 and all(r["dtype"] == "f64" for r in selected), "pre2 capture dtype/count")
    by_level = {int(r["k_zero"]): r["raw_hex"].zfill(16) for r in selected}
    need(set(by_level) == set(range(39)), "pre2 capture levels")
    return [by_level[38 - i] for i in range(39)]


def numeric_vector(value: object, n: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == n, why + " length")
    need(all(isinstance(x, (int, float)) and math.isfinite(x) for x in value), why + " finite")
    return [float(x) for x in value]


def replay(*, output_override: tuple[bytes, str] | None = None) -> dict:
    fixed_manifest()
    fd_parent, _, _ = verified_parent_replays()
    raw = (HERE / "raw/cpp_result.json").read_bytes() if output_override is None else output_override[0]
    if output_override is None:
        provenance(raw)
    else:
        need(sha(raw) == output_override[1], "override SHA")
        # Keep the original build/source/input receipts pinned; only the output is substituted.
        provenance((HERE / "raw/cpp_result.json").read_bytes())
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_pre2_input_cpp_ad.v1", "result schema")
    state, _, _ = parent_inputs()
    baseline = data["baseline"]
    with np.load(NC16 / "raw/nc16_result.npz", allow_pickle=False) as z:
        for key, parent_key in (("value_final_raw", "value_output"),
                                ("graph_final_raw", "graph_output")):
            actual = [str(x).zfill(16) for x in baseline[key]]
            need(actual == words(z[parent_key]), "baseline final state raw: " + key)
    captured = capture("baseline")
    for key, field in (("pre2_qg_raw", "qg_input"), ("pre2_brs_raw", "brs_input")):
        need([str(x).zfill(16) for x in baseline[key]] == pre2_words(captured, field),
             "39-layer pre2 input raw: " + field)
    selected = numeric_vector(baseline["selected"], 2, "baseline selected")
    need([word(v) for v in selected]
         == [str(baseline[k][LEVEL16]).zfill(16) for k in ("pre2_qg_raw", "pre2_brs_raw")],
         "selected native16 pre2 words")
    local_raw = (LOCAL / "raw/cpp_result.json").read_bytes()
    need(sha(local_raw) == LOCAL_CPP_SHA, "parent local C2c AD SHA")
    local = json.loads(local_raw)
    need([word(v) for v in selected]
         == [word(local["directions"]["qg_relative"]["seed"][0]),
             word(local["directions"]["brs_relative"]["seed"][1])],
         "local process graph starts at captured pre2 inputs")
    vjp = {k: numeric_vector(data["vjp"][k], 468, "VJP " + k)
           for k in ("pre2_qg", "pre2_brs")}
    need(set(data["vjp"]) == set(vjp), "VJP outputs")
    need(set(data["directions"]) == set(DIRECTIONS), "direction names")
    known_caps = {(x["direction"], x["h"]): x["captured_cap_crossing"]
                  for x in fd_parent["comparisons"]}
    diagnostics: dict[str, dict] = {}
    mediated: dict[str, dict[str, float]] = {}
    for name, (prefix, _, active) in DIRECTIONS.items():
        direction = data["directions"][name]
        expected_seed = [float(state[6, 16]) if active[0] else 0.0,
                         float(state[11, 16]) if active[1] else 0.0]
        actual_seed = [direction["seed_qg17"], direction["seed_brs17"]]
        need([word(v) for v in actual_seed] == [word(v) for v in expected_seed],
             "relative input seed: " + name)
        jvp = numeric_vector(direction["jvp"], 2, "JVP " + name)
        for index, out in enumerate(("pre2_qg", "pre2_brs")):
            terms = [vjp[out][QG17] * expected_seed[0], vjp[out][BRS17] * expected_seed[1]]
            contraction = sum(terms)
            bound = 2e-12 * sum(map(abs, terms)) + 32 * math.ulp(jvp[index])
            need(abs(jvp[index] - contraction) <= bound, "JVP/VJP transpose: " + name + "/" + out)
        need(set(direction["finite_differences"]) == set(STEPS) | {"1e-06"},
             "FD steps: " + name)
        max_captured_no_cap_error = 0.0
        max_uncaptured_small_step_error = 0.0
        max_one_sided_error = 0.0
        crossings = []
        for h, pair in direction["finite_differences"].items():
            step = float(h)
            low_input = numeric_vector(pair["low_input"], 2, "FD low input")
            high_input = numeric_vector(pair["high_input"], 2, "FD high input")
            for slot, enabled in enumerate(active):
                original = float(state[6, 16] if slot == 0 else state[11, 16])
                need(word(low_input[slot]) == word(original * (1.0 - step) if enabled else original)
                     and word(high_input[slot]) == word(original * (1.0 + step) if enabled else original),
                     "represented FD input: " + name + "/" + h)
            low = numeric_vector(pair["low"], 2, "FD low pre2")
            high = numeric_vector(pair["high"], 2, "FD high pre2")
            for side, values in (("low", low), ("high", high)):
                actual = [str(x).zfill(16) for x in pair[side + "_final_raw"]]
                need(len(actual) == 468, "FD final state size")
                if h in STEPS:
                    label = prefix + "_" + STEPS[h] + ("_minus" if side == "low" else "_plus")
                    with np.load(FD / "raw/cases" / (label + ".npz"), allow_pickle=False) as z:
                        need(actual == words(z["output"]), "FD parent final state: " + label)
                        need([word(float(z["state"][6, 16])), word(float(z["state"][11, 16]))]
                             == [word(x) for x in (low_input if side == "low" else high_input)],
                             "FD parent input: " + label)
            if name == "joint17_relative" and h == "0.001":
                for side, values in (("minus", low), ("plus", high)):
                    rows = capture("qg_bg17_rel_1e-03_" + side)
                    need([word(x) for x in values]
                         == [pre2_words(rows, field)[LEVEL16]
                             for field in ("qg_input", "brs_input")],
                         "joint parent pre2 input: " + side)
            gap = [high_input[i] - low_input[i] for i in (0, 1)]
            if h in STEPS:
                need((prefix, step) in known_caps, "parent cap observation: " + name + "/" + h)
            crossing = known_caps[(prefix, step)] if h in STEPS else None
            if crossing:
                crossings.append(h)
            for index, out in enumerate(("pre2_qg", "pre2_brs")):
                observed = high[index] - low[index]
                predicted = vjp[out][QG17] * gap[0] + vjp[out][BRS17] * gap[1]
                signal_error = abs(observed - predicted) / max(abs(observed), abs(predicted), math.ulp(selected[index]))
                if not crossing:
                    need(signal_error < 1e-6, "FD signal derivative: " + name + "/" + h + "/" + out)
                    if h in STEPS:
                        max_captured_no_cap_error = max(max_captured_no_cap_error, signal_error)
                    else:
                        max_uncaptured_small_step_error = max(max_uncaptured_small_step_error,
                                                              signal_error)
                    for endpoint_input, endpoint_value in ((low_input, low), (high_input, high)):
                        one_gap = [endpoint_input[0] - float(state[6, 16]),
                                   endpoint_input[1] - float(state[11, 16])]
                        one_observed = endpoint_value[index] - selected[index]
                        one_predicted = (vjp[out][QG17] * one_gap[0]
                                         + vjp[out][BRS17] * one_gap[1])
                        one_error = abs(one_observed - one_predicted) / max(
                            abs(one_observed), abs(one_predicted), math.ulp(selected[index]))
                        need(one_error < 2 * step, "FD one-sided baseline: " + name + "/" + h + "/" + out)
                        max_one_sided_error = max(max_one_sided_error, one_error)
        need(crossings == (["0.001"] if name != "joint17_relative" else []),
             "recorded density-cap crossing: " + name)
        diagnostics[name] = {
            "jvp": jvp,
            "max_captured_no_cap_signal_error": max_captured_no_cap_error,
            "max_uncaptured_small_step_signal_error": max_uncaptured_small_step_error,
            "max_one_sided_error": max_one_sided_error,
            "recorded_cap_crossing_steps": crossings,
        }
        mediated[name] = {output: local["vjp_rows"][output][0] * jvp[0]
                          + local["vjp_rows"][output][1] * jvp[1]
                          for output in ("ngacw", "naacw", "nc_budget")}
    return {
        "schema": "kdm6.native_pre2_input_cpp_ad_replay.v1",
        "baseline_final_values_raw_equal": 468,
        "baseline_pre2_inputs_raw_equal": 78,
        "parent_fd_endpoints_raw_equal": 18,
        "captured_no_cap_pairs": 7,
        "captured_cap_crossing_pairs": 2,
        "extra_small_step_pairs_without_cap_capture": 3,
        "vjp_components_recorded_per_output": 468,
        "vjp_coordinates_independently_fd_checked": 2,
        "directions": diagnostics,
        "partial_pre2_mediated_chain": mediated,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified full-call C++ AD into pre2 inputs: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
