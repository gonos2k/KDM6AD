#!/usr/bin/env python3
"""Replay the selected native B1/B2 warm-number producer input tangents."""

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
PARENT = EVIDENCE / "native_nc_process_graph_cpp_ad_2026-11-08"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
MANIFEST_SHA = "3e4bbac1042a791cb6c8cb0aea211f7760b3f7423bfb7bd4fc49f8d46618717b"
PARENT_REPLAY_SHA = "5422734758bb3b1d82887c33f8a217471a87dba4192aa185fb2ef11a97207916"
DIRECTIONS = ("qg17_relative", "brs17_relative", "joint17_relative")
NEW_B1 = {
    "qc", "nc", "qr", "nr", "den", "qcr", "lenconcr", "ncmin", "qck1",
    "nraut_coeff", "dtcld", "praut", "nraut",
}
NEW_B2 = {
    "nc", "nr", "qr", "lenconcr", "avedia_r", "rslopec3", "rslope3_r",
    "nracw", "ncrk1", "ncrk2", "g3pmc", "g6pmc", "g4pmr", "g1pmr",
    "g7pmr", "di100", "dtcld",
}
B1_FIXED = {
    "qck1": 3297.941162109375,
    "nraut_coeff": 3.5e9,
    "ncmin": 10.0,
    "dtcld": 20.0,
    "qcr": 8.37758052512072e-05,
}
B2_FIXED = {
    "ncrk1", "ncrk2", "g3pmc", "g6pmc", "g4pmr", "g1pmr",
    "g7pmr", "di100", "dtcld",
}
SIGNALS = (
    "nraut_producer.nraut", "nracw_producer.nracw", "nraut_producer.nr",
    "nraut_producer.qr", "nracw_producer.rslope3_r", "nracw_producer.avedia_r",
)
CAP_CROSS = {("qg17_relative", "0.001"), ("brs17_relative", "0.001")}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def exact(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def ulps(a: float, b: float, limit: int, why: str) -> int:
    need(math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0, why + " positive finite")
    gap = abs(int(word(a), 16) - int(word(b), 16))
    need(gap <= limit, why + " ULP " + str(gap))
    return gap


def near_roundoff(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    scale = max(abs(a), abs(b), 1.0)
    bound = 16 * math.ulp(scale) + 2e-14 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def finite_vector(value: object, n: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == n, why + " length")
    need(all(isinstance(x, (float, int)) and math.isfinite(x) for x in value), why + " finite")
    return [float(x) for x in value]


def fixed_manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    manifest = json.loads(raw)
    need(manifest["schema"] == "kdm6.native_warm_rate_inputs_cpp_ad_packet.v1", "manifest schema")
    actual = {str(path.relative_to(HERE)) for folder in ("raw", "executed_cpp")
              for path in (HERE / folder).rglob("*") if path.is_file()}
    need(set(manifest["files"]) == actual, "packet file inventory")
    for name, digest in manifest["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "packet asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #558 replay source")
    spec = importlib.util.spec_from_file_location("warm_rate_parent", source)
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()
    need(result["baseline_stage_words_raw_equal"] == 127
         and result["joint_endpoint_stage_words_raw_equal"] == 254
         and result["joint_stage_linearity_components"] == 119,
         "verified #558 parent")
    result["upstream_cap_windows"] = module.parent_replay()["directions"]
    return result


def provenance(original: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_warm_rate_inputs_cpp_ad_build.v1", "build schema")
    need(run["schema"] == "kdm6.native_warm_rate_inputs_cpp_ad_run.v1"
         and run["returncode"] == 0, "run schema/status")
    for name, path in {
        "runner_source": PARENT / "cpp/main.cpp",
        "runner_cmake": PARENT / "cpp/CMakeLists.txt",
        "parent_coordinator": PARENT / "executed_cpp/coordinator.cpp",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "warm_source": HERE.parent.parent.parent / "libtorch/src/warm.cpp",
        "input_binary": EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin",
        "output_json": HERE / "raw/cpp_result.json",
    }.items():
        need(sha(path.read_bytes()) == build["sha256"][name], "build source/input SHA: " + name)
    need(run["output_sha256"] == sha(original) == build["sha256"]["output_json"],
         "run output SHA")
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
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    for block in (
        b"        name == \"nraut_producer\" || name == \"nracw_producer\" ||\n",
        b"    capture_native_tensor(\"nraut_producer\", \"qc\", state.qc);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"nc\", state.nc);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"qr\", state.qr);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"nr\", state.nr);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"den\", forcing.dend);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"qcr\", qcr);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"lenconcr\", pre.lenconcr);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"ncmin\", params.autoconv.ncmin_tensor.has_value()\n"
        b"        ? params.autoconv.ncmin_tensor.value() : torch::full_like(state.nc, params.autoconv.ncmin));\n"
        b"    capture_native_tensor(\"nraut_producer\", \"qck1\", torch::full_like(state.nc, params.autoconv.qck1));\n"
        b"    capture_native_tensor(\"nraut_producer\", \"nraut_coeff\", torch::full_like(state.nc, params.autoconv.nraut_coeff));\n"
        b"    capture_native_tensor(\"nraut_producer\", \"dtcld\", torch::full_like(state.nc, dtcld));\n"
        b"    capture_native_tensor(\"nraut_producer\", \"praut\", b1.praut);\n"
        b"    capture_native_tensor(\"nraut_producer\", \"nraut\", b1.nraut);\n",
    ):
        need(source.count(block) == 1, "unique warm producer hook insertion")
        source = source.replace(block, b"", 1)
    need(source == (PARENT / "executed_cpp/coordinator.cpp").read_bytes(),
         "warm producer hook restores #558 source")


def capture(label: str) -> dict[str, dict[str, str]]:
    raw = gzip.decompress((PRE2 / "raw/cases" / (label + ".csv.gz")).read_bytes()).decode()
    need(raw.endswith("status=complete\n"), "complete native capture: " + label)
    rows = csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#"))
    return {row["stage"] + "." + row["field"]: row for row in rows
            if row["k_zero"] == "23"}


def native_b2(values: dict, rows: dict, why: str) -> int:
    count = 0
    for field in NEW_B2:
        key = "nracw_producer." + field
        row = rows[key]
        need(row["dtype"] == "f64" and word(values[key]) == row["raw_hex"].zfill(16),
             why + " native B2 word: " + field)
        count += 1
    return count


def producer_values(values: dict, why: str) -> tuple[int, int, dict[str, float]]:
    b = "nraut_producer."
    a = "nracw_producer."
    need({k.removeprefix(b) for k in values if k.startswith(b)} == NEW_B1,
         why + " B1 inputs")
    need({k.removeprefix(a) for k in values if k.startswith(a)} == NEW_B2,
         why + " B2 inputs")
    for name, expected in B1_FIXED.items():
        exact(values[b + name], expected, why + " B1 parameter word: " + name)
    qc, nc, qr, nr, den, qcr, ncmin, dt = (values[b + k] for k in
                                             ("qc", "nc", "qr", "nr", "den", "qcr", "ncmin", "dtcld"))
    need(qc > qcr and nc > ncmin and qr > values[b + "lenconcr"]
         and qc > 0 and nc > 0 and qr > 0 and nr > 0, why + " B1 strict active/swap")
    praut_raw = values[b + "qck1"] * math.pow(qc, 7.0 / 3.0) * math.pow(nc, -1.0 / 3.0)
    need(praut_raw < qc / dt, why + " B1 praut cap inactive")
    praut = min(praut_raw, qc / dt)
    nr_default = values[b + "nraut_coeff"] * den * praut
    nr_swap = (nr / qr) * praut
    need(nr_swap < nc / dt and nr_default > 0, why + " B1 nraut cap inactive")
    praut_ulps = ulps(praut, values[b + "praut"], 8, why + " B1 praut")
    nraut_ulps = ulps(nr_swap, values[b + "nraut"], 8, why + " B1 nraut")

    need(values[a + "qr"] >= values[a + "lenconcr"]
         and values[a + "avedia_r"] >= values[a + "di100"],
         why + " B2 rain/large-drop branch")
    need(values[a + "nc"] > 0 and values[a + "nr"] > 0 and values[a + "rslope3_r"] > 0,
         why + " B2 positive operands")
    ratio = values[a + "g4pmr"] / values[a + "g1pmr"]
    bracket = values[a + "rslopec3"] * values[a + "g3pmc"] + values[a + "rslope3_r"] * ratio
    nracw_raw = values[a + "ncrk1"] * values[a + "nc"] * values[a + "nr"] * bracket
    need(nracw_raw < values[a + "nc"] / values[a + "dtcld"],
         why + " B2 individual cap inactive")
    nracw_ulps = ulps(nracw_raw, values[a + "nracw"], 4, why + " B2 nracw")
    return max(praut_ulps, nraut_ulps), nracw_ulps, {
        "b1_qc_minus_qcr": qc - qcr,
        "b1_nc_minus_ncmin": nc - ncmin,
        "b1_qr_minus_lenconcr": qr - values[b + "lenconcr"],
        "b1_praut_cap_margin": qc / dt - praut_raw,
        "b1_nraut_cap_margin": nc / dt - nr_swap,
        "b2_avedia_minus_di100": values[a + "avedia_r"] - values[a + "di100"],
        "b2_qr_minus_lenconcr": values[a + "qr"] - values[a + "lenconcr"],
        "b2_nracw_cap_margin": values[a + "nc"] / values[a + "dtcld"] - nracw_raw,
    }


def producer_tangents(values: dict, tangents: dict, why: str) -> dict:
    b, a = "nraut_producer.", "nracw_producer."
    for stage, names in ((b, NEW_B1), (a, NEW_B2)):
        for name in names:
            need(stage + name in tangents, why + " producer tangent inventory")
    for key in (b + "nc", b + "qc", b + "den", b + "qck1", b + "nraut_coeff",
                b + "qcr", b + "lenconcr", b + "ncmin", b + "dtcld", b + "praut",
                a + "nc", a + "rslopec3", a + "ncrk1", a + "g3pmc", a + "g4pmr",
                a + "g1pmr", a + "di100", a + "lenconcr", a + "dtcld"):
        need(tangents[key] == 0.0, why + " fixed operand tangent: " + key)
    nr, qr, praut = (values[b + k] for k in ("nr", "qr", "praut"))
    b1_terms = {
        "nr": praut / qr * tangents[b + "nr"],
        "qr": -(praut * nr / (qr * qr)) * tangents[b + "qr"],
        "praut": nr / qr * tangents[b + "praut"],
    }
    near_roundoff(sum(b1_terms.values()), tangents[b + "nraut"], tuple(b1_terms.values()),
                  why + " B1 input chain")
    nc, nr2, rc3, rr3, k, g3, g4, g1 = (values[a + n] for n in
                                            ("nc", "nr", "rslopec3", "rslope3_r",
                                             "ncrk1", "g3pmc", "g4pmr", "g1pmr"))
    bracket = rc3 * g3 + rr3 * (g4 / g1)
    b2_terms = {
        "nc": k * nr2 * bracket * tangents[a + "nc"],
        "nr": k * nc * bracket * tangents[a + "nr"],
        "rslopec3": k * nc * nr2 * g3 * tangents[a + "rslopec3"],
        "rslope3_r": k * nc * nr2 * (g4 / g1) * tangents[a + "rslope3_r"],
    }
    near_roundoff(sum(b2_terms.values()), tangents[a + "nracw"], tuple(b2_terms.values()),
                  why + " B2 input chain")
    return {"b1_nraut_terms": b1_terms, "b2_nracw_terms": b2_terms}


def replay(*, output_override: tuple[bytes, str] | None = None) -> dict:
    fixed_manifest()
    parent_summary = parent_replay()
    original = (HERE / "raw/cpp_result.json").read_bytes()
    provenance(original)
    raw = original if output_override is None else output_override[0]
    if output_override is not None:
        need(sha(raw) == output_override[1], "override SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_process_graph_cpp_ad.v1", "C++ result schema")
    parent = json.loads((PARENT / "raw/cpp_result.json").read_text())
    baseline, prior_base = data["baseline"], parent["baseline"]
    for name in ("value_final_raw", "graph_final_raw", "pre2_qg_raw", "pre2_brs_raw"):
        need([str(w).zfill(16) for w in baseline[name]] == [str(w).zfill(16) for w in prior_base[name]],
             "parent full baseline raw: " + name)
    need([word(v) for v in baseline["selected"]] == [word(v) for v in prior_base["selected"]],
         "parent pre2 selected baseline")
    need(set(baseline["stage_scalars"]) == set(prior_base["stage_scalars"])
         | {"nraut_producer." + n for n in NEW_B1} | {"nracw_producer." + n for n in NEW_B2},
         "warm producer stage inventory")
    for name, value in prior_base["stage_scalars"].items():
        exact(baseline["stage_scalars"][name], value, "parent baseline stage: " + name)
        need(baseline["stage_types"][name] == prior_base["stage_types"][name], "parent stage dtype")
    need(all(baseline["stage_types"][k] == "f64" for k in baseline["stage_scalars"]
             if k.startswith(("nraut_producer.", "nracw_producer."))), "warm stage f64")
    order = data["stage_numeric_order"]
    need(order == sorted(k for k, v in baseline["stage_types"].items() if v == "f64")
         and len(order) == 149 and len(baseline["stage_scalars"]) == 157,
         "numeric warm stage order")
    need(set(data["vjp"]) == set(parent["vjp"])
         == {"pre2_qg", "pre2_brs", "final_nc16", "final_nccn16"},
         "VJP row inventory")
    for key, row in data["vjp"].items():
        need([word(v) for v in finite_vector(row, 468, "VJP " + key)]
             == [word(v) for v in parent["vjp"][key]], "parent VJP raw: " + key)
    need(set(data["directions"]) == set(DIRECTIONS), "direction names")
    max_b1_ulps = max_b2_ulps = 0
    minima: dict[str, float] = {}
    native_b2_words = 0
    for label, values in (("baseline", baseline["stage_scalars"]),
                          ("qg_bg17_rel_1e-03_minus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["low_stages"]),
                          ("qg_bg17_rel_1e-03_plus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["high_stages"])):
        rows = capture(label)
        native_b2_words += native_b2(values, rows, label)
        for b1_name, b2_name in (("nc", "nc"), ("nr", "nr"), ("qr", "qr"),
                                 ("lenconcr", "lenconcr")):
            exact(values["nraut_producer." + b1_name],
                  values["nracw_producer." + b2_name], label + " shared B1/B2 input")
        for b1_name, other in (("qc", "c2c_number_inputs.qc"),
                               ("den", "pre2_producer.dend_input"),
                               ("ncmin", "c2c_number_inputs.ncmin")):
            exact(values["nraut_producer." + b1_name], values[other],
                  label + " B1 existing capture input")
    all_cases = [("baseline", baseline["stage_scalars"], baseline["value_final_raw"])]
    for name in DIRECTIONS:
        direction, prior = data["directions"][name], parent["directions"][name]
        for key in ("seed_qg17", "seed_brs17"):
            exact(direction[key], prior[key], "parent seed: " + name + "/" + key)
        for key in ("jvp", "final_jvp"):
            need([word(v) for v in direction[key]] == [word(v) for v in prior[key]],
                 "parent JVP raw: " + name + "/" + key)
        new_jvp = dict(zip(order, finite_vector(direction["stage_jvp"], 149, "stage JVP " + name)))
        old_jvp = dict(zip(parent["stage_numeric_order"], prior["stage_jvp"]))
        for stage, value in old_jvp.items():
            exact(new_jvp[stage], value, "parent stage JVP raw: " + name + "/" + stage)
        for stage, target in (("nraut_producer.nraut", "nc_budget.nraut"),
                              ("nracw_producer.nracw", "nc_budget.nracw")):
            gap = abs(int(word(new_jvp[stage]), 16) - int(word(new_jvp[target]), 16))
            need(gap <= 2, "rate producer-to-budget JVP ULP: " + name + "/" + stage)
        need(set(direction["finite_differences"]) == set(prior["finite_differences"]),
             "FD steps: " + name)
        for h, pair in direction["finite_differences"].items():
            prev = prior["finite_differences"][h]
            for side in ("low", "high"):
                need([word(v) for v in pair[side + "_input"]] == [word(v) for v in prev[side + "_input"]],
                     "parent FD input: " + name + "/" + h + "/" + side)
                need([str(w).zfill(16) for w in pair[side + "_final_raw"]]
                     == [str(w).zfill(16) for w in prev[side + "_final_raw"]],
                     "parent FD final raw: " + name + "/" + h + "/" + side)
                for old_stage, value in prev[side + "_stages"].items():
                    exact(pair[side + "_stages"][old_stage], value,
                          "parent FD stage raw: " + name + "/" + h + "/" + side)
                all_cases.append((name + "/" + h + "/" + side,
                                  pair[side + "_stages"], pair[side + "_final_raw"]))
    for label, values, _ in all_cases:
        for name in B2_FIXED:
            exact(values["nracw_producer." + name],
                  baseline["stage_scalars"]["nracw_producer." + name],
                  label + " fixed B2 parameter: " + name)
        for b1_name, other in (("qc", "c2c_number_inputs.qc"),
                               ("den", "pre2_producer.dend_input"),
                               ("ncmin", "c2c_number_inputs.ncmin")):
            exact(values["nraut_producer." + b1_name], values[other],
                  label + " B1 existing stage input")
        b1_ulps, b2_ulps, margins = producer_values(values, label)
        max_b1_ulps = max(max_b1_ulps, b1_ulps)
        max_b2_ulps = max(max_b2_ulps, b2_ulps)
        for key, margin in margins.items():
            minima[key] = min(minima.get(key, margin), margin)
        exact(values["nraut_producer.nraut"], values["nc_budget.nraut"],
              label + " B1-to-budget raw")
        exact(values["nracw_producer.nracw"], values["nc_budget.nracw"],
              label + " B2-to-budget raw")
    jvp = {name: dict(zip(order, data["directions"][name]["stage_jvp"])) for name in DIRECTIONS}
    for stage in order:
        a, b = jvp["qg17_relative"][stage], jvp["brs17_relative"][stage]
        near_roundoff(jvp["joint17_relative"][stage], a + b, (a, b),
                      "joint warm stage linearity: " + stage)
    terms: dict[str, dict] = {}
    for name in DIRECTIONS:
        parts = producer_tangents(baseline["stage_scalars"], jvp[name], name)
        terms[name] = parts
    qg0 = data["directions"]["qg17_relative"]["seed_qg17"]
    brs0 = data["directions"]["brs17_relative"]["seed_brs17"]
    max_captured_fd = max_small_fd = max_one_sided = 0.0
    for name in DIRECTIONS:
        for h, pair in data["directions"][name]["finite_differences"].items():
            if (name, h) in CAP_CROSS:
                need(h in parent_summary["upstream_cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent density-cap crossing")
                continue
            if h != "1e-06":
                need(h not in parent_summary["upstream_cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent non-crossing density cap")
            dq = (pair["high_input"][0] - pair["low_input"][0]) / qg0
            db = (pair["high_input"][1] - pair["low_input"][1]) / brs0
            for stage in SIGNALS:
                observed = pair["high_stages"][stage] - pair["low_stages"][stage]
                predicted = jvp["qg17_relative"][stage] * dq + jvp["brs17_relative"][stage] * db
                base = baseline["stage_scalars"][stage]
                need(abs(observed) > 32 * math.ulp(base), "FD signal resolved: " + name + "/" + stage)
                error = abs(observed - predicted) / max(abs(observed), abs(predicted), math.ulp(base))
                need(error < 1e-6, "FD warm rate/input: " + name + "/" + h + "/" + stage)
                if h == "1e-06":
                    max_small_fd = max(max_small_fd, error)
                else:
                    max_captured_fd = max(max_captured_fd, error)
                for side in ("low", "high"):
                    input_pair = pair[side + "_input"]
                    e_qg = (input_pair[0] - qg0) / qg0
                    e_brs = (input_pair[1] - brs0) / brs0
                    one_observed = pair[side + "_stages"][stage] - base
                    one_predicted = jvp["qg17_relative"][stage] * e_qg + jvp["brs17_relative"][stage] * e_brs
                    one_error = abs(one_observed - one_predicted) / max(
                        abs(one_observed), abs(one_predicted), math.ulp(base))
                    need(one_error < 4 * float(h),
                         "FD warm input one-sided baseline: " + name + "/" + h + "/" + stage)
                    max_one_sided = max(max_one_sided, one_error)
    return {
        "schema": "kdm6.native_warm_rate_inputs_cpp_ad_replay.v1",
        "baseline_and_endpoint_cases": len(all_cases),
        "new_b1_inputs": len(NEW_B1),
        "existing_native_b2_words_raw_equal": native_b2_words,
        "new_numeric_stage_tangents_per_direction": len(order),
        "warm_branch_minimum_margins": minima,
        "max_python_b1_ulps": max_b1_ulps,
        "max_python_b2_ulps": max_b2_ulps,
        "max_captured_no_cap_signal_error": max_captured_fd,
        "max_uncaptured_small_step_signal_error": max_small_fd,
        "max_one_sided_error": max_one_sided,
        "directional_producer_terms": terms,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified native B1/B2 warm-rate input AD: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
