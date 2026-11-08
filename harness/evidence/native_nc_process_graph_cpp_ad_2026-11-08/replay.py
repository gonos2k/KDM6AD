#!/usr/bin/env python3
"""Replay the selected native NC/NCCN process graph and directional ledger."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
from functools import lru_cache
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
NC16 = EVIDENCE / "native_nc16_vjp_branch_window_2026-11-06"
MANIFEST_SHA = "c788c237bf54ca5d89860e9401a95bcfd4b46a209ee3a75018142bae4dc8b7a7"
PARENT_REPLAY_SHA = "13f8fdd9b305022b31e557f73afdadb91e6399ad4593ca5224ce621554bdfd58"
STAGES = {
    "pre2_producer", "c2c_number_inputs", "naacw_producer", "nc_limit_cold",
    "nc_limit_warm", "nc_budget", "fd_state_update", "fd_reclass",
    "fd_satadj_inner", "fd_cleanup", "fd_dsd",
}
DIRECTIONS = ("qg17_relative", "brs17_relative", "joint17_relative")
SIGNALS = (
    "naacw_producer.ngacw", "naacw_producer.naacw", "nc_budget.nraut",
    "nc_budget.nracw", "nc_budget.nc_clamped", "fd_dsd.nc_after",
)
NC_TIMELINE = (
    "nc_budget.nc_clamped", "fd_state_update.nc_after", "fd_reclass.nc",
    "fd_satadj_inner.nc_input", "fd_satadj_inner.nc_after_activation",
    "fd_satadj_inner.nc_final", "fd_cleanup.nc", "fd_dsd.nc_after",
)
C2C_NONZERO = {
    "c2c_number_inputs.qg", "c2c_number_inputs.avtg", "c2c_number_inputs.g3pbg",
    "c2c_number_inputs.rslope3_g", "c2c_number_inputs.rslopeb_g",
}
CAP_CROSS = {("qg17_relative", "0.001"), ("brs17_relative", "0.001")}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def words(array: np.ndarray) -> list[str]:
    return [format(int(w), "016x") for w in np.asarray(array, dtype="<f8").reshape(-1).view("<u8")]


def exact_float(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def near_roundoff(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    scale = max(abs(a), abs(b), 1.0)
    bound = 16 * math.ulp(scale) + 2e-14 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def finite_vector(value: object, count: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == count, why + " size")
    need(all(isinstance(v, (int, float)) and math.isfinite(v) for v in value), why + " finite")
    return [float(v) for v in value]


def fixed_manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_process_graph_cpp_ad_packet.v1", "manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "cpp", "executed_cpp")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(data["files"]) == actual, "packet file inventory")
    for name, digest in data["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "packet asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #556 replay source")
    spec = importlib.util.spec_from_file_location("nc_process_parent", source)
    need(spec is not None and spec.loader is not None, "#556 replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    need(result["baseline_final_values_raw_equal"] == 468
         and result["baseline_pre2_inputs_raw_equal"] == 78
         and result["parent_fd_endpoints_raw_equal"] == 18,
         "verified #556 parent")
    return result


def provenance(raw: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_nc_process_graph_cpp_ad_build.v1", "build schema")
    need(run["schema"] == "kdm6.native_nc_process_graph_cpp_ad_run.v1" and run["returncode"] == 0,
         "run schema/status")
    for name, path in {
        "runner_source": HERE / "cpp/main.cpp",
        "runner_cmake": HERE / "cpp/CMakeLists.txt",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "parent_coordinator": PARENT / "executed_cpp/coordinator.cpp",
        "input_binary": PARENT / "raw/input.bin",
        "output_json": HERE / "raw/cpp_result.json",
    }.items():
        need(sha(path.read_bytes()) == build["sha256"][name], "build source/input SHA: " + name)
    need(run["output_sha256"] == sha(raw) == build["sha256"]["output_json"], "run output SHA")
    need(run["input_sha256"] == build["sha256"]["input_binary"], "run input SHA")
    need(run["archive_sha256"] == build["sha256"]["library_archive"], "run archive SHA")
    need(run["executable_sha256"] == build["sha256"]["runner_executable"], "run executable SHA")
    need(run["environment"] == {
        "KDM6AD_QNC_LIVE_GUARD": "1", "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
        "KDM6_QR_TRANSPORT": "actual_departure", "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1"}, "run environment")
    for key, archive in (("runner_flags", "runner_flags.make.gz"),
                         ("core_flags", "core_flags.make.gz"),
                         ("bridge_flags", "bridge_flags.make.gz")):
        flags = gzip.decompress((HERE / "raw" / archive).read_bytes()).decode()
        need(sha(flags.encode()) == build["sha256"][key], "build flags SHA: " + key)
        need("-ffp-contract=off" in flags, "FP contract: " + key)
        if key == "runner_flags":
            need("-DNDEBUG" not in flags, "runner assertions enabled")
        else:
            need("KDM6_NATIVE_SCALAR_CAPTURE" in flags, "capture build: " + key)
    cache = gzip.decompress((HERE / "raw/runner_cache.txt.gz").read_bytes())
    need(sha(cache) == build["sha256"]["runner_cache"], "runner cache SHA")

    # Only the live stage map and one record call are new relative to #556.
    executed = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    for block in (
        b"#include <map>\n",
        b"thread_local std::map<std::string, torch::Tensor> stage_tensors;\n",
        b"    stage_tensors.clear();\n",
        b"void record_stage(const char* stage, const char* field, const torch::Tensor& value) {\n"
        b"    if (!pre2_input_hook_enabled) return;\n"
        b"    const std::string name(stage);\n"
        b"    if (name == \"pre2_producer\" || name == \"c2c_number_inputs\" ||\n"
        b"        name == \"naacw_producer\" || name == \"nc_limit_cold\" ||\n"
        b"        name == \"nc_limit_warm\" || name == \"nc_budget\" ||\n"
        b"        name == \"fd_state_update\" || name == \"fd_reclass\" ||\n"
        b"        name == \"fd_satadj_inner\" || name == \"fd_cleanup\" ||\n"
        b"        name == \"fd_dsd\") {\n"
        b"        stage_tensors[name + \".\" + field] = value;\n"
        b"    }\n"
        b"}\n"
        b"std::map<std::string, torch::Tensor> stage_hook_values() { return stage_tensors; }\n",
        b"    testing::record_stage(stage, name, value);\n",
    ):
        need(executed.count(block) == 1, "unique stage hook insertion")
        executed = executed.replace(block, b"", 1)
    need(executed == (PARENT / "executed_cpp/coordinator.cpp").read_bytes(),
         "stage hook restores #556 source")


def capture(label: str) -> dict[str, dict[str, str]]:
    raw = gzip.decompress((PRE2 / "raw/cases" / (label + ".csv.gz")).read_bytes()).decode()
    need(raw.endswith("status=complete\n"), "complete native capture: " + label)
    rows = csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#"))
    selected = {r["stage"] + "." + r["field"]: r for r in rows
                if int(r["k_zero"]) == 23 and r["stage"] in STAGES}
    need(len(selected) == 127, "selected stage capture inventory")
    return selected


def compare_stages(values: dict, types: dict, parent: dict, why: str) -> None:
    need(set(values) == set(parent) == set(types), why + " keys")
    for name, value in values.items():
        need(isinstance(value, (int, float)) and math.isfinite(value), why + " finite: " + name)
        kind = types[name]
        need(kind in ("bool", "f64") and parent[name]["dtype"] == kind,
             why + " dtype: " + name)
        bits = int(value != 0) if kind == "bool" else int(word(value), 16)
        need(bits == int(parent[name]["raw_hex"], 16), why + " raw word: " + name)


def budget_and_branch(values: dict, final_words: list[str], why: str) -> None:
    s = values
    need(s["nc_limit_cold.gate"] == 0 and s["nc_limit_warm.gate"] == 1,
         why + " cloud limiter gates")
    for stage in ("nc_limit_cold", "nc_limit_warm"):
        for rate in ("nracw", "naacw"):
            exact_float(s[stage + "." + rate + "_before"], s[stage + "." + rate + "_after"],
                        why + " no cloud rate rescale")
        need(s[stage + ".nc"] - 20.0 * s[stage + ".source_sum"] > 0,
             why + " cloud number margin")
    for consumer, producer in (
        ("nc_budget.nraut", "nc_limit_warm.nraut_before"),
        ("nc_budget.nccol", "nc_limit_warm.nccol_before"),
        ("nc_budget.nracw", "nc_limit_warm.nracw_after"),
        ("nc_budget.naacw", "nc_limit_warm.naacw_after"),
        ("nc_budget.niacw", "nc_limit_cold.niacw_before"),
    ):
        exact_float(s[consumer], s[producer], why + " limiter-to-budget: " + consumer)
    nc = "nc_budget."
    rate = ((((-s[nc + "nraut"] - s[nc + "nccol"]) - s[nc + "nracw"])
             - s[nc + "niacw"] * s[nc + "cold_mask"]) - s[nc + "naacw"]) - s[nc + "naacw"]
    exact_float(rate, s[nc + "dnc_rate_sum"], why + " source-order NC rate sum")
    base = s[nc + "nc_before"] + s[nc + "dnc_amount"]
    exact_float(base, s[nc + "nc_base"], why + " NC base")
    candidate = base + rate * s[nc + "dtcld"]
    exact_float(candidate, s[nc + "nc_unclamped"], why + " NC candidate")
    exact_float(max(candidate, 0.0), s[nc + "nc_clamped"], why + " NC clamp")
    exact_float(s[nc + "nc_clamped"], s["fd_state_update.nc_after"], why + " NC state update")
    exact_float(s["fd_state_update.nc_after"], s["fd_reclass.nc"], why + " NC reclass")
    a = "fd_satadj_inner."
    need(s[a + "activated_fraction"] == 1.0 and s[a + "ncact"] == 5e6
         and s[a + "cloud_complete_evap"] == 0 and s[a + "nccn_floor_active"] == 1
         and s[a + "nccn_cap_active"] == 0, why + " activation/reservoir gates")
    exact_float(max(0.0, s[a + "nc_input"] + s[a + "ncact"] * 20.0),
                s[a + "nc_after_activation"], why + " activation NC")
    exact_float(max(0.0, s[a + "nccn_input"] - s[a + "ncact"] * 20.0),
                s[a + "nccn_after_activation"], why + " activation NCCN")
    exact_float(s[a + "nccn_after_activation"] + s[a + "nc_evap_amount"],
                s[a + "nccn_final_raw"], why + " raw NCCN")
    exact_float(max(1e8, min(2e10, s[a + "nccn_final_raw"])),
                s[a + "nccn_final"], why + " NCCN reservoir clamp")
    exact_float(s[a + "nc_final"], s["fd_cleanup.nc"], why + " NC cleanup")
    exact_float(s["fd_cleanup.nc"], s["fd_dsd.nc_after"], why + " NC DSD")
    exact_float(s[a + "nccn_final"], s["fd_cleanup.nccn"], why + " NCCN cleanup")
    exact_float(s["fd_cleanup.nccn"], s["fd_dsd.nccn_after"], why + " NCCN DSD")
    need(word(s["fd_dsd.nc_after"]) == str(final_words[8 * 39 + 15]).zfill(16),
         why + " final packed NC16")
    need(word(s["fd_dsd.nccn_after"]) == str(final_words[7 * 39 + 15]).zfill(16),
         why + " final packed NCCN16")


def replay(*, output_override: tuple[bytes, str] | None = None) -> dict:
    fixed_manifest()
    parent_summary = parent_replay()
    original = (HERE / "raw/cpp_result.json").read_bytes()
    provenance(original)
    raw = original if output_override is None else output_override[0]
    if output_override is not None:
        need(sha(raw) == output_override[1], "override SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_process_graph_cpp_ad.v1", "result schema")
    parent = json.loads((PARENT / "raw/cpp_result.json").read_text())
    for field in ("value_final_raw", "graph_final_raw", "pre2_qg_raw", "pre2_brs_raw"):
        need([str(w).zfill(16) for w in data["baseline"][field]]
             == [str(w).zfill(16) for w in parent["baseline"][field]],
             "parent baseline raw: " + field)
    need([word(v) for v in finite_vector(data["baseline"]["selected"], 2, "selected pre2")]
         == [word(v) for v in parent["baseline"]["selected"]], "parent pre2 selected")
    types = data["baseline"]["stage_types"]
    stages = data["baseline"]["stage_scalars"]
    compare_stages(stages, types, capture("baseline"), "baseline stage")
    numeric_order = data["stage_numeric_order"]
    need(numeric_order == sorted(k for k in stages if types[k] == "f64")
         and len(numeric_order) == 119 and len(stages) == 127, "numeric stage order")
    budget_and_branch(stages, data["baseline"]["value_final_raw"], "baseline")
    for key in ("pre2_qg", "pre2_brs"):
        need([word(v) for v in finite_vector(data["vjp"][key], 468, "VJP " + key)]
             == [word(v) for v in parent["vjp"][key]], "parent pre2 VJP raw: " + key)
    with np.load(NC16 / "raw/nc16_result.npz", allow_pickle=False) as z:
        need([word(v) for v in finite_vector(data["vjp"]["final_nc16"], 468, "final NC VJP")]
             == words(z["vjp_nc16"]), "parent NC16 VJP raw")
    nccn_vjp = finite_vector(data["vjp"]["final_nccn16"], 468, "final NCCN VJP")
    need(all(v == 0.0 for v in nccn_vjp), "NCCN16 VJP at active floor")
    need(set(data["vjp"]) == {"pre2_qg", "pre2_brs", "final_nc16", "final_nccn16"},
         "VJP output inventory")
    need(set(data["directions"]) == set(DIRECTIONS), "directions")

    jvp_by_name = {name: dict(zip(numeric_order, finite_vector(data["directions"][name]["stage_jvp"],
                                                         119, "stage JVP " + name)))
                   for name in DIRECTIONS}
    qg0 = data["directions"]["qg17_relative"]["seed_qg17"]
    brs0 = data["directions"]["brs17_relative"]["seed_brs17"]
    need(qg0 > 0 and brs0 > 0, "positive native17 input seeds")
    diagnostics: dict[str, dict] = {}
    captured_no_cap_max = 0.0
    extra_small_step_max = 0.0
    one_sided_max = 0.0
    parent_raw_endpoints = 0
    joint_stage_capture_words = 0
    for name in DIRECTIONS:
        direction = data["directions"][name]
        prior = parent["directions"][name]
        need([word(direction[k]) for k in ("seed_qg17", "seed_brs17")]
             == [word(prior[k]) for k in ("seed_qg17", "seed_brs17")],
             "parent relative seed: " + name)
        need([word(v) for v in finite_vector(direction["jvp"], 2, "pre2 JVP")]
             == [word(v) for v in prior["jvp"]], "parent pre2 JVP raw: " + name)
        stage_jvp = jvp_by_name[name]
        final_jvp = finite_vector(direction["final_jvp"], 2, "final JVP " + name)
        seed_qg, seed_brs = direction["seed_qg17"], direction["seed_brs17"]
        for index, output in enumerate(("final_nc16", "final_nccn16")):
            terms = (data["vjp"][output][6 * 39 + 16] * seed_qg,
                     data["vjp"][output][11 * 39 + 16] * seed_brs)
            near_roundoff(final_jvp[index], sum(terms), terms, "final JVP/VJP: " + name)
        need(final_jvp[1] == 0.0, "final NCCN16 JVP: " + name)
        for key in ("nc_budget.nc_before", "nc_budget.nccol", "nc_budget.niacw",
                    "nc_budget.cold_mask",
                    "nc_budget.dnc_amount", "fd_satadj_inner.ncact",
                    "fd_satadj_inner.nccn_final_raw", "fd_satadj_inner.nccn_final"):
            need(stage_jvp[key] == 0.0, "zero branch/process tangent: " + name + "/" + key)
        need({k for k in numeric_order if k.startswith("c2c_number_inputs.") and stage_jvp[k] != 0.0}
             == C2C_NONZERO, "five changing C2c inputs: " + name)
        for key in NC_TIMELINE:
            exact_float(stage_jvp[key], final_jvp[0], "NC tangent storage: " + name + "/" + key)
        for key in ("ngacw", "naacw"):
            near_roundoff(stage_jvp["naacw_producer." + key],
                          parent_summary["partial_pre2_mediated_chain"][name][key],
                          (stage_jvp["naacw_producer." + key],),
                          "local C2c mediated tangent: " + name + "/" + key)
        terms = {
            "naacw_twice": -40.0 * stage_jvp["nc_budget.naacw"],
            "nracw": -20.0 * stage_jvp["nc_budget.nracw"],
            "nraut": -20.0 * stage_jvp["nc_budget.nraut"],
            "nccol": -20.0 * stage_jvp["nc_budget.nccol"],
            "niacw_masked": -20.0 * stage_jvp["nc_budget.niacw"] * stages["nc_budget.cold_mask"],
            "nc_before": stage_jvp["nc_budget.nc_before"],
            "inline_amount": stage_jvp["nc_budget.dnc_amount"],
        }
        near_roundoff(sum(terms.values()), final_jvp[0], tuple(terms.values()),
                      "full NC budget derivative: " + name)
        near_roundoff(terms["naacw_twice"],
                      parent_summary["partial_pre2_mediated_chain"][name]["nc_budget"],
                      (terms["naacw_twice"],), "#556 conditional NC contribution: " + name)

        max_fd = 0.0
        need(set(direction["finite_differences"]) == set(prior["finite_differences"]),
             "parent FD steps: " + name)
        for h, pair in direction["finite_differences"].items():
            prev = prior["finite_differences"][h]
            need([word(v) for v in pair["low_input"] + pair["high_input"]]
                 == [word(v) for v in prev["low_input"] + prev["high_input"]],
                 "parent represented FD input: " + name + "/" + h)
            for side in ("low", "high"):
                need([str(w).zfill(16) for w in pair[side + "_final_raw"]]
                     == [str(w).zfill(16) for w in prev[side + "_final_raw"]],
                     "parent full FD final state: " + name + "/" + h + "/" + side)
                parent_raw_endpoints += 1
                stage_values = pair[side + "_stages"]
                need(set(stage_values) == set(stages), "FD stage inventory: " + name + "/" + h)
                budget_and_branch(stage_values, pair[side + "_final_raw"],
                                  "FD " + name + "/" + h + "/" + side)
                if name == "joint17_relative" and h == "0.001":
                    label = "qg_bg17_rel_1e-03_" + ("minus" if side == "low" else "plus")
                    compare_stages(stage_values, types, capture(label), "joint stage capture: " + label)
                    joint_stage_capture_words += len(stage_values)
            if (name, h) in CAP_CROSS:
                need(h in parent_summary["directions"][name]["recorded_cap_crossing_steps"],
                     "recorded density cap crossing")
                continue
            need(h not in parent_summary["directions"][name]["recorded_cap_crossing_steps"],
                 "unflagged density cap crossing")
            eps_qg = (pair["high_input"][0] - pair["low_input"][0]) / qg0
            eps_brs = (pair["high_input"][1] - pair["low_input"][1]) / brs0
            for key in SIGNALS:
                observed = pair["high_stages"][key] - pair["low_stages"][key]
                predicted = (jvp_by_name["qg17_relative"][key] * eps_qg
                             + jvp_by_name["brs17_relative"][key] * eps_brs)
                need(abs(observed) > 32 * math.ulp(stages[key]),
                     "FD signal resolution: " + name + "/" + h + "/" + key)
                error = abs(observed - predicted) / max(abs(observed), abs(predicted), math.ulp(stages[key]))
                need(error < 1e-6, "FD signal derivative: " + name + "/" + h + "/" + key)
                max_fd = max(max_fd, error)
                if h == "1e-06":
                    extra_small_step_max = max(extra_small_step_max, error)
                else:
                    captured_no_cap_max = max(captured_no_cap_max, error)
                for side in ("low", "high"):
                    input_pair = pair[side + "_input"]
                    e_qg = (input_pair[0] - qg0) / qg0
                    e_brs = (input_pair[1] - brs0) / brs0
                    value = pair[side + "_stages"][key]
                    one_observed = value - stages[key]
                    one_predicted = (jvp_by_name["qg17_relative"][key] * e_qg
                                     + jvp_by_name["brs17_relative"][key] * e_brs)
                    one_error = abs(one_observed - one_predicted) / max(
                        abs(one_observed), abs(one_predicted), math.ulp(stages[key]))
                    need(one_error < 4 * float(h),
                         "FD one-sided baseline: " + name + "/" + h + "/" + key)
                    one_sided_max = max(one_sided_max, one_error)
        diagnostics[name] = {"final_jvp": final_jvp, "budget_terms": terms,
                             "max_unflagged_signal_error": max_fd}
    return {
        "schema": "kdm6.native_nc_process_graph_cpp_ad_replay.v1",
        "baseline_stage_words_raw_equal": len(stages),
        "joint_endpoint_stage_words_raw_equal": joint_stage_capture_words,
        "parent_full_state_endpoints_raw_equal": parent_raw_endpoints,
        "numeric_stage_tangents_per_direction": len(numeric_order),
        "final_vjp_components_per_seed": 468,
        "recorded_cap_crossing_pairs": 2,
        "captured_no_cap_pairs": 7,
        "extra_small_step_pairs_without_cap_capture": 3,
        "max_captured_no_cap_signal_error": captured_no_cap_max,
        "max_uncaptured_small_step_signal_error": extra_small_step_max,
        "max_one_sided_error": one_sided_max,
        "directions": diagnostics,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified full-call native NC/NCCN process graph: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
