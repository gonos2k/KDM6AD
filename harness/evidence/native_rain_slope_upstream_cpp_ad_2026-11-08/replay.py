#!/usr/bin/env python3
"""Replay the selected D1-to-pre2 rain-slope AD handoffs."""

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


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_warm_rate_inputs_cpp_ad_2026-11-08"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
RUNNER = EVIDENCE / "native_nc_process_graph_cpp_ad_2026-11-08/cpp"
MANIFEST_SHA = "7e085e10c019887cd8360abd1ca98d275fc518d375ca02e492f4b015531c8a99"
PARENT_REPLAY_SHA = "1467472a3147e4c8f612d556876948804f0db3b2fe15cf7cf23e0826aa70bfa0"
DIRECTIONS = ("qg17_relative", "brs17_relative", "joint17_relative")
CAP_CROSS = {("qg17_relative", "0.001"), ("brs17_relative", "0.001")}
NEW_STAGES = {
    "d1_melt_consumer": {"qs_before", "qs_after", "qg_before", "qg_after", "qr_before",
                         "qr1", "qr2", "qr_after", "nr_before", "nr1", "nr2", "nr_after",
                         "brs_before", "brs_after", "warm_mask", "pfrzdtr", "nfrzdtr",
                         "delta_brs_freeze", "sfac_melt", "gfac_melt", "delta_brs_capped"},
    "fd_snap_a": {"nc_before", "nc_candidate", "nc_after", "nr_before", "nr_after"},
    "d234_rain": {"qr_before", "nr_before", "qr_after", "nr_after"},
    "fd_after_d234": {"nc", "nr"},
    "pre2_rain_producer": {"qr_input", "nr_input", "dend_input", "pidnr", "rslope_limit",
                            "rslopermax", "rsloper3max", "qcrmin", "nrmin", "rslope_r",
                            "rslope2_r", "rslope3_r", "avedia_r", "avedia_ratio"},
    "fd_snap_b": {"nc_before", "nc_candidate", "nc_after", "nr_before", "nr_after"},
}
NATIVE_STAGES = {"d1_melt_consumer", "fd_snap_a", "fd_after_d234", "fd_snap_b"}
STATIC_RAIN = {
    "pidnr": 12566.37109375,
    "rslope_limit": 1.0e-3,
    "rslopermax": 2.8571428629220463e-05,
    "rsloper3max": 2.3323614632524137e-14,
    "qcrmin": 1.0e-9,
    "nrmin": 1.0e-2,
    "avedia_ratio": 24.0,
}
SIGNALS = (
    "d1_melt_consumer.qr2", "d1_melt_consumer.nr2", "pre2_rain_producer.qr_input",
    "pre2_rain_producer.nr_input", "pre2_rain_producer.rslope3_r",
    "pre2_rain_producer.avedia_r",
)
VALUE_LINKS = (
    ("d1_melt_consumer.qr_after", "d234_rain.qr_before"),
    ("d1_melt_consumer.nr_after", "fd_snap_a.nr_before"),
    ("fd_snap_a.nr_after", "d234_rain.nr_before"),
    ("d234_rain.qr_after", "pre2_rain_producer.qr_input"),
    ("d234_rain.nr_after", "pre2_rain_producer.nr_input"),
    ("pre2_rain_producer.nr_input", "fd_snap_b.nr_before"),
    ("fd_snap_b.nr_after", "nracw_producer.nr"),
    ("pre2_rain_producer.qr_input", "nracw_producer.qr"),
    ("pre2_rain_producer.rslope3_r", "nracw_producer.rslope3_r"),
    ("pre2_rain_producer.avedia_r", "nracw_producer.avedia_r"),
)
IDENTITY_LINKS = (
    ("d1_melt_consumer.qr2", "d1_melt_consumer.qr_after"),
    ("d1_melt_consumer.nr2", "d1_melt_consumer.nr_after"),
    ("fd_snap_a.nr_before", "fd_snap_a.nr_after"),
    ("d234_rain.qr_before", "d234_rain.qr_after"),
    ("d234_rain.nr_before", "d234_rain.nr_after"),
    ("fd_snap_b.nr_before", "fd_snap_b.nr_after"),
)
ALPHA = float(struct.unpack(">f", struct.pack(">f", 1.0 / 3.0))[0])


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def exact(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def near_ulps(a: float, b: float, maximum: int, why: str) -> int:
    need(math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0, why + " finite positive")
    gap = abs(int(word(a), 16) - int(word(b), 16))
    need(gap <= maximum, why + " ULP " + str(gap))
    return gap


def near_tangent(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    need(math.isfinite(a) and math.isfinite(b), why + " finite")
    scale = max(abs(a), abs(b), 1e-300)
    bound = 64 * math.ulp(scale) + 1e-12 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def finite_vector(value: object, count: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == count, why + " size")
    need(all(isinstance(v, (int, float)) and math.isfinite(v) for v in value), why + " finite")
    return [float(v) for v in value]


def fixed_manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_rain_slope_upstream_cpp_ad_packet.v1", "manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "executed_cpp")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(data["files"]) == actual, "packet file inventory")
    for name, digest in data["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #559 parent replay")
    spec = importlib.util.spec_from_file_location("rain_slope_parent", source)
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.replay()
    need(summary["baseline_and_endpoint_cases"] == 25
         and summary["existing_native_b2_words_raw_equal"] == 51
         and summary["new_numeric_stage_tangents_per_direction"] == 149,
         "verified #559 parent")
    summary["cap_windows"] = module.parent_replay()["upstream_cap_windows"]
    return summary


def provenance(original: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_rain_slope_upstream_cpp_ad_build.v1", "build schema")
    need(run["schema"] == "kdm6.native_rain_slope_upstream_cpp_ad_run.v1"
         and run["returncode"] == 0, "run schema/status")
    paths = {
        "runner_source": RUNNER / "main.cpp",
        "runner_cmake": RUNNER / "CMakeLists.txt",
        "parent_coordinator": PARENT / "executed_cpp/coordinator.cpp",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "slope_source": HERE.parent.parent.parent / "libtorch/src/slope.cpp",
        "cloud_dsd_source": HERE.parent.parent.parent / "libtorch/src/cloud_dsd.cpp",
        "runtime_source": PRE2 / "executed_cpp/runtime.cpp",
        "input_binary": EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin",
        "output_json": HERE / "raw/cpp_result.json",
    }
    for key, path in paths.items():
        need(sha(path.read_bytes()) == build["sha256"][key], "source/input SHA: " + key)
    need(run["output_sha256"] == sha(original) == build["sha256"]["output_json"], "run output SHA")
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
        need(sha(flags.encode()) == build["sha256"][key], "flags SHA: " + key)
        need("-ffp-contract=off" in flags, "FP contract: " + key)
        if key == "runner_flags":
            need("-DNDEBUG" not in flags, "runner assertions")
        else:
            need("KDM6_NATIVE_SCALAR_CAPTURE" in flags, "capture build: " + key)
    cache = gzip.decompress((HERE / "raw/runner_cache.txt.gz").read_bytes())
    need(sha(cache) == build["sha256"]["runner_cache"], "runner cache SHA")
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    additions = [line for line in source.splitlines(keepends=True)
                 if line.startswith((b"        name == \"d1_melt_consumer\"",
                                     b"        name == \"d234_rain\"",
                                     b"        name == \"pre2_rain_producer\""))
                 or b'capture_native_tensor("d234_rain"' in line
                 or b'capture_native_tensor("pre2_rain_producer"' in line]
    need(len(additions) == 21, "unique D1/pre2 rain hook insertion count")
    stripped = b"".join(line for line in source.splitlines(keepends=True) if line not in additions)
    need(stripped == (PARENT / "executed_cpp/coordinator.cpp").read_bytes(),
         "rain hook restores #559 source")


def capture(label: str) -> dict[str, dict[str, str]]:
    raw = gzip.decompress((PRE2 / "raw/cases" / (label + ".csv.gz")).read_bytes()).decode()
    need(raw.endswith("status=complete\n"), "complete native capture: " + label)
    rows = csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#"))
    return {r["stage"] + "." + r["field"]: r for r in rows if r["k_zero"] == "23"}


def rain_value(values: dict, why: str) -> tuple[dict[str, float], dict[str, int]]:
    p = "pre2_rain_producer."
    for key, expected in STATIC_RAIN.items():
        exact(values[p + key], expected, why + " rain constant: " + key)
    qr, nr, den = (values[p + key] for key in ("qr_input", "nr_input", "dend_input"))
    need(qr > values[p + "qcrmin"] and nr > values[p + "nrmin"] and den > 0,
         why + " active rain slope")
    need(values["d1_melt_consumer.warm_mask"] == 1.0, why + " D1 warm mask")
    ratio = values[p + "pidnr"] * nr / max(qr * den, 1e-30)
    need(ratio > 1e-30, why + " rain ratio domain")
    lam = math.exp(math.log(max(ratio, 1e-30)) * ALPHA)
    need(961.0 < lam < 35000.0, why + " rain lambda snap interior")
    rslope_raw = 1.0 / lam
    need(rslope_raw < values[p + "rslope_limit"], why + " rain rslope cap inactive")
    r = min(rslope_raw, values[p + "rslope_limit"])
    r2 = r * r
    r3 = r2 * r
    avedia = r * math.pow(values[p + "avedia_ratio"], 0.3333333)
    gaps = {
        "rslope_r": near_ulps(r, values[p + "rslope_r"], 16, why + " rslope_r"),
        "rslope2_r": near_ulps(r2, values[p + "rslope2_r"], 16, why + " rslope2_r"),
        "rslope3_r": near_ulps(r3, values[p + "rslope3_r"], 32, why + " rslope3_r"),
        "avedia_r": near_ulps(avedia, values[p + "avedia_r"], 16, why + " avedia_r"),
    }
    return {
        "qr_minus_qcrmin": qr - values[p + "qcrmin"],
        "nr_minus_nrmin": nr - values[p + "nrmin"],
        "den_positive": den,
        "lambda_minus_min": lam - 961.0,
        "max_minus_lambda": 35000.0 - lam,
        "rslope_cap_margin": values[p + "rslope_limit"] - rslope_raw,
    }, gaps


def replay(*, output_override: tuple[bytes, str] | None = None) -> dict:
    fixed_manifest()
    parent_summary = parent_replay()
    original = (HERE / "raw/cpp_result.json").read_bytes()
    provenance(original)
    raw = original if output_override is None else output_override[0]
    if output_override is not None:
        need(sha(raw) == output_override[1], "override SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_process_graph_cpp_ad.v1", "C++ schema")
    prior = json.loads((PARENT / "raw/cpp_result.json").read_text())
    base, old_base = data["baseline"], prior["baseline"]
    for key in ("value_final_raw", "graph_final_raw", "pre2_qg_raw", "pre2_brs_raw"):
        need([str(v).zfill(16) for v in base[key]] == [str(v).zfill(16) for v in old_base[key]],
             "parent final/pre2 raw: " + key)
    need([word(v) for v in base["selected"]] == [word(v) for v in old_base["selected"]],
         "parent pre2 selected")
    new_keys = {stage + "." + field for stage, fields in NEW_STAGES.items() for field in fields}
    need(set(base["stage_scalars"]) == set(old_base["stage_scalars"]) | new_keys,
         "new rain stage inventory")
    for key, value in old_base["stage_scalars"].items():
        exact(base["stage_scalars"][key], value, "parent baseline stage: " + key)
        need(base["stage_types"][key] == old_base["stage_types"][key], "parent dtype: " + key)
    order = data["stage_numeric_order"]
    need(order == sorted(k for k, typ in base["stage_types"].items() if typ == "f64")
         and len(order) == 200 and len(base["stage_scalars"]) == 208,
         "rain numeric stage order")
    need(set(data["vjp"]) == set(prior["vjp"])
         == {"pre2_qg", "pre2_brs", "final_nc16", "final_nccn16"}, "VJP inventory")
    for key, row in data["vjp"].items():
        need([word(v) for v in finite_vector(row, 468, "VJP " + key)]
             == [word(v) for v in prior["vjp"][key]], "parent VJP raw: " + key)
    need(set(data["directions"]) == set(DIRECTIONS), "directions")
    jvp = {}
    for name in DIRECTIONS:
        direction, old = data["directions"][name], prior["directions"][name]
        for field in ("seed_qg17", "seed_brs17"):
            exact(direction[field], old[field], "parent seed: " + name)
        for field in ("jvp", "final_jvp"):
            need([word(v) for v in direction[field]] == [word(v) for v in old[field]],
                 "parent JVP raw: " + name + "/" + field)
        jvp[name] = dict(zip(order, finite_vector(direction["stage_jvp"], 200, "rain JVP " + name)))
        old_jvp = dict(zip(prior["stage_numeric_order"], old["stage_jvp"]))
        for field, value in old_jvp.items():
            exact(jvp[name][field], value, "parent stage JVP raw: " + name + "/" + field)
        need(set(direction["finite_differences"]) == set(old["finite_differences"]),
             "parent FD steps")
        for h, pair in direction["finite_differences"].items():
            prev = old["finite_differences"][h]
            for side in ("low", "high"):
                need([word(v) for v in pair[side + "_input"]] == [word(v) for v in prev[side + "_input"]],
                     "parent FD input: " + name + "/" + h + "/" + side)
                need([str(v).zfill(16) for v in pair[side + "_final_raw"]]
                     == [str(v).zfill(16) for v in prev[side + "_final_raw"]],
                     "parent FD final: " + name + "/" + h + "/" + side)
                for field, value in prev[side + "_stages"].items():
                    exact(pair[side + "_stages"][field], value,
                          "parent FD stage raw: " + name + "/" + h + "/" + side)
    all_cases = [("baseline", base["stage_scalars"])]
    all_cases += [(name + "/" + h + "/" + side, pair[side + "_stages"])
                  for name in DIRECTIONS for h, pair in data["directions"][name]["finite_differences"].items()
                  for side in ("low", "high")]
    native_words = 0
    for label, values in (("baseline", base["stage_scalars"]),
                          ("qg_bg17_rel_1e-03_minus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["low_stages"]),
                          ("qg_bg17_rel_1e-03_plus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["high_stages"])):
        rows = capture(label)
        for stage in NATIVE_STAGES:
            for field in NEW_STAGES[stage]:
                key = stage + "." + field
                need(rows[key]["dtype"] == "f64"
                     and word(values[key]) == rows[key]["raw_hex"].zfill(16),
                     "native D1/snap word: " + label + "/" + key)
                native_words += 1
    min_margins: dict[str, float] = {}
    max_ulps = {key: 0 for key in ("rslope_r", "rslope2_r", "rslope3_r", "avedia_r")}
    for label, values in all_cases:
        need(set(values) == set(base["stage_scalars"]), "rain case stage inventory: " + label)
        need(values["d1_melt_consumer.pfrzdtr"] == 0.0
             and values["d1_melt_consumer.nfrzdtr"] == 0.0,
             "D1 post-graupel freeze terms inactive: " + label)
        for first, second in VALUE_LINKS + IDENTITY_LINKS:
            exact(values[first], values[second], "rain value handoff: " + label + "/" + first)
        exact(values["pre2_rain_producer.dend_input"], values["pre2_producer.dend_input"],
              "rain DEND forcing handoff: " + label)
        for key in STATIC_RAIN:
            exact(values["pre2_rain_producer." + key], base["stage_scalars"]["pre2_rain_producer." + key],
                  "immutable rain parameter: " + label + "/" + key)
        margins, gaps = rain_value(values, label)
        for key, margin in margins.items():
            min_margins[key] = min(min_margins.get(key, margin), margin)
        for key, gap in gaps.items():
            max_ulps[key] = max(max_ulps[key], gap)
    for field in ("d1_melt_consumer.qr_before", "d1_melt_consumer.qr1",
                  "d1_melt_consumer.nr_before", "d1_melt_consumer.nr1"):
        need(all(jvp[name][field] == 0.0 for name in DIRECTIONS), "D1 pre-graupel zero JVP: " + field)
    for name in DIRECTIONS:
        tangent = jvp[name]
        need(tangent["d1_melt_consumer.pfrzdtr"] == 0.0
             and tangent["d1_melt_consumer.nfrzdtr"] == 0.0,
             "D1 post-graupel freeze tangents inactive: " + name)
        for first, second in VALUE_LINKS + IDENTITY_LINKS:
            exact(tangent[first], tangent[second], "rain tangent handoff: " + name + "/" + first)
        need(tangent["pre2_rain_producer.dend_input"] == 0.0,
             "fixed DEND tangent: " + name)
        for field in STATIC_RAIN:
            need(tangent["pre2_rain_producer." + field] == 0.0,
                 "fixed rain parameter tangent: " + name + "/" + field)
        p = "pre2_rain_producer."
        qr, nr, den = (base["stage_scalars"][p + field] for field in ("qr_input", "nr_input", "dend_input"))
        r, r3 = (base["stage_scalars"][p + field] for field in ("rslope_r", "rslope3_r"))
        log_ratio_tangent = (tangent[p + "nr_input"] / nr
                             - tangent[p + "qr_input"] / qr
                             - tangent[p + "dend_input"] / den)
        predicted_r = -ALPHA * r * log_ratio_tangent
        predicted_r3 = -3.0 * ALPHA * r3 * log_ratio_tangent
        predicted_avedia = math.pow(base["stage_scalars"][p + "avedia_ratio"], 0.3333333) * predicted_r
        near_tangent(tangent[p + "rslope_r"], predicted_r, (predicted_r,),
                     "rain rslope input chain: " + name)
        near_tangent(tangent[p + "rslope3_r"], predicted_r3, (predicted_r3,),
                     "rain rslope3 input chain: " + name)
        near_tangent(tangent[p + "avedia_r"], predicted_avedia, (predicted_avedia,),
                     "rain avedia input chain: " + name)
    for field in order:
        a, b = jvp["qg17_relative"][field], jvp["brs17_relative"][field]
        near_tangent(jvp["joint17_relative"][field], a + b, (a, b),
                     "joint rain stage linearity: " + field)
    joint = jvp["joint17_relative"]
    b = base["stage_scalars"]
    p, q = "pre2_rain_producer.", "nracw_producer."
    nr = b[p + "nr_input"]
    qr = b[p + "qr_input"]
    r3 = b[p + "rslope3_r"]
    coefficient = b[q + "ncrk1"] * b[q + "nc"] * b[q + "nr"] * (b[q + "g4pmr"] / b[q + "g1pmr"])
    direct_nr = parent_summary["directional_producer_terms"]["joint17_relative"]["b2_nracw_terms"]["nr"]
    nested = {
        "direct_nr": direct_nr,
        "slope_via_nr": -coefficient * r3 * 3.0 * ALPHA * joint[p + "nr_input"] / nr,
        "slope_via_qr": coefficient * r3 * 3.0 * ALPHA * joint[p + "qr_input"] / qr,
    }
    near_tangent(sum(nested.values()), joint[q + "nracw"], tuple(nested.values()),
                 "joint B2 nested NR/QR chain")
    qg0 = data["directions"]["qg17_relative"]["seed_qg17"]
    brs0 = data["directions"]["brs17_relative"]["seed_brs17"]
    max_captured_fd = max_small_fd = max_one_sided = 0.0
    for name in DIRECTIONS:
        for h, pair in data["directions"][name]["finite_differences"].items():
            if (name, h) in CAP_CROSS:
                need(h in parent_summary["cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent density cap crossing")
                continue
            if h != "1e-06":
                need(h not in parent_summary["cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent non-crossing density cap")
            dq = (pair["high_input"][0] - pair["low_input"][0]) / qg0
            db = (pair["high_input"][1] - pair["low_input"][1]) / brs0
            for field in SIGNALS:
                observed = pair["high_stages"][field] - pair["low_stages"][field]
                predicted = jvp["qg17_relative"][field] * dq + jvp["brs17_relative"][field] * db
                baseline = base["stage_scalars"][field]
                need(abs(observed) > 32 * math.ulp(baseline),
                     "rain FD signal resolved: " + name + "/" + field)
                error = abs(observed - predicted) / max(abs(observed), abs(predicted), math.ulp(baseline))
                need(error < 1e-6, "rain FD signal derivative: " + name + "/" + h + "/" + field)
                if h == "1e-06":
                    max_small_fd = max(max_small_fd, error)
                else:
                    max_captured_fd = max(max_captured_fd, error)
                for side in ("low", "high"):
                    inp = pair[side + "_input"]
                    one_obs = pair[side + "_stages"][field] - baseline
                    one_pred = (jvp["qg17_relative"][field] * (inp[0] - qg0) / qg0
                                + jvp["brs17_relative"][field] * (inp[1] - brs0) / brs0)
                    one_error = abs(one_obs - one_pred) / max(abs(one_obs), abs(one_pred), math.ulp(baseline))
                    need(one_error < 4 * float(h),
                         "rain FD one-sided baseline: " + name + "/" + h + "/" + field)
                    max_one_sided = max(max_one_sided, one_error)
    return {
        "schema": "kdm6.native_rain_slope_upstream_cpp_ad_replay.v1",
        "selected_cases": len(all_cases),
        "d1_postgraupel_value_links_checked": 2 * len(all_cases),
        "d1_postgraupel_tangent_links_checked": 2 * len(DIRECTIONS),
        "native_d1_and_snap_words_raw_equal": native_words,
        "new_stage_fields": len(new_keys),
        "numeric_stage_tangents_per_direction": len(order),
        "f32_reciprocal_dmr": ALPHA,
        "max_python_ulp_by_field": max_ulps,
        "minimum_branch_margins": min_margins,
        "joint_b2_nested_terms": nested,
        "max_captured_no_cap_signal_error": max_captured_fd,
        "max_uncaptured_small_step_signal_error": max_small_fd,
        "max_one_sided_error": max_one_sided,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified native D1-to-pre2 rain-slope input AD: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
