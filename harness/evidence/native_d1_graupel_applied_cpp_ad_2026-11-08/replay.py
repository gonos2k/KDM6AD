#!/usr/bin/env python3
"""Replay selected native D1 graupel applied-amount and number-factor AD."""

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
PARENT = EVIDENCE / "native_rain_slope_upstream_cpp_ad_2026-11-08"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
RUNNER = EVIDENCE / "native_nc_process_graph_cpp_ad_2026-11-08/cpp"
MELT_SOURCE = EVIDENCE / "native_d1_melt_state_ad_2026-11-04/executed_cpp/melt_freeze.cpp"
MANIFEST_SHA = "c65410e87cbe47ef784d6671d5fe27054eb62bf947faaa8cbb3d35154c17a150"
PARENT_REPLAY_SHA = "0574a4b4b362d8a77ed00c9ffdfb1d69f17a4a31ce55c9b5f4f8089b90365ee9"
DIRECTIONS = ("qg17_relative", "brs17_relative", "joint17_relative")
NEW_STAGE = "c3_pre_mf_d1"
NEW_FIELDS = {
    "qi_before", "t_before", "pinuc_qi", "pimlt_qi", "pfrzdtc_qi",
    "qi_after_store1", "qi_after_store2", "ni_before", "ninuc", "pimlt_ni",
    "nfrzdtc", "ni_after_store1", "ni_after_store2", "qc_before", "nc_before",
    "qv_before", "pre_cpm", "cpm_safe", "psmlt_capped", "pgmlt_capped",
    "qc_after_store1", "qc_after_store2", "nc_after_store1", "nc_after_store2",
    "t_after_melt", "t_after_d1",
}
CAP_CROSS = {("qg17_relative", "0.001"), ("brs17_relative", "0.001")}
SIGNALS = (
    "c3_pre_mf_d1.pgmlt_capped", "d1_melt_consumer.gfac_melt",
    "d1_melt_consumer.qr2", "d1_melt_consumer.nr2",
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def exact(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def near_roundoff(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    need(math.isfinite(a) and math.isfinite(b), why + " finite")
    scale = max(abs(a), abs(b), 1.0)
    bound = 16 * math.ulp(scale) + 2e-14 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def finite_vector(value: object, count: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == count, why + " length")
    need(all(isinstance(x, (float, int)) and math.isfinite(x) for x in value), why + " finite")
    return [float(x) for x in value]


def fixed_manifest() -> None:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_d1_graupel_applied_cpp_ad_packet.v1", "manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "executed_cpp")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(data["files"]) == actual, "packet file inventory")
    for name, digest in data["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #561 replay source")
    spec = importlib.util.spec_from_file_location("d1_graupel_parent", source)
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.replay()
    need(summary["selected_cases"] == 25 and summary["new_stage_fields"] == 51
         and summary["numeric_stage_tangents_per_direction"] == 200
         and summary["d1_postgraupel_value_links_checked"] == 50
         and summary["d1_postgraupel_tangent_links_checked"] == 6,
         "verified #561 parent")
    summary["cap_windows"] = module.parent_replay()["cap_windows"]
    return summary


def provenance(original: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_d1_graupel_applied_cpp_ad_build.v1", "build schema")
    need(run["schema"] == "kdm6.native_d1_graupel_applied_cpp_ad_run.v1"
         and run["returncode"] == 0, "run schema/status")
    for key, path in {
        "runner_source": RUNNER / "main.cpp",
        "runner_cmake": RUNNER / "CMakeLists.txt",
        "parent_coordinator": PARENT / "executed_cpp/coordinator.cpp",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "melt_freeze_source": MELT_SOURCE,
        "input_binary": EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin",
        "output_json": HERE / "raw/cpp_result.json",
    }.items():
        need(sha(path.read_bytes()) == build["sha256"][key], "source/input SHA: " + key)
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
        need(sha(flags.encode()) == build["sha256"][key], "flags SHA: " + key)
        need("-ffp-contract=off" in flags, "FP contract: " + key)
        if key == "runner_flags":
            need("-DNDEBUG" not in flags, "runner assertions")
        else:
            need("KDM6_NATIVE_SCALAR_CAPTURE" in flags, "capture build: " + key)
    cache = gzip.decompress((HERE / "raw/runner_cache.txt.gz").read_bytes())
    need(sha(cache) == build["sha256"]["runner_cache"], "runner cache SHA")
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    hook = b'        name == "d1_melt_consumer" || name == "c3_pre_mf_d1" || name == "fd_snap_a" ||\n'
    parent_line = b'        name == "d1_melt_consumer" || name == "fd_snap_a" ||\n'
    need(source.count(hook) == 1, "unique D1 amount live hook")
    need(source.replace(hook, parent_line, 1)
         == (PARENT / "executed_cpp/coordinator.cpp").read_bytes(),
         "D1 amount hook restores #561 source")


def capture(label: str) -> dict[str, dict[str, str]]:
    raw = gzip.decompress((PRE2 / "raw/cases" / (label + ".csv.gz")).read_bytes()).decode()
    need(raw.endswith("status=complete\n"), "complete native capture: " + label)
    rows = csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#"))
    return {r["stage"] + "." + r["field"]: r for r in rows if r["k_zero"] == "23"}


def d1_values(values: dict, why: str) -> float:
    a = values["c3_pre_mf_d1.pgmlt_capped"]
    g = values["d1_melt_consumer.gfac_melt"]
    qg = values["d1_melt_consumer.qg_before"]
    mask = values["d1_melt_consumer.warm_mask"]
    need(mask == 1.0 and -qg < a < 0.0 and g > 0,
         why + " signed uncapped warm graupel amount")
    need(values["d1_melt_consumer.pfrzdtr"] == 0.0
         and values["d1_melt_consumer.nfrzdtr"] == 0.0,
         why + " inactive subsequent rain freeze")
    qr2 = values["d1_melt_consumer.qr1"] - a * mask
    nr2 = values["d1_melt_consumer.nr1"] - g * a
    exact(qr2, values["d1_melt_consumer.qr2"], why + " source-order QR2")
    exact(nr2, values["d1_melt_consumer.nr2"], why + " source-order NR2")
    exact(values["d1_melt_consumer.qr2"], values["d1_melt_consumer.qr_after"],
          why + " D1 final QR")
    exact(values["d1_melt_consumer.nr2"], values["d1_melt_consumer.nr_after"],
          why + " D1 final NR")
    return min(a + qg, -a)


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
    prior = json.loads((PARENT / "raw/cpp_result.json").read_text())
    base, old_base = data["baseline"], prior["baseline"]
    for key in ("value_final_raw", "graph_final_raw", "pre2_qg_raw", "pre2_brs_raw"):
        need([str(v).zfill(16) for v in base[key]] == [str(v).zfill(16) for v in old_base[key]],
             "parent full baseline raw: " + key)
    need([word(v) for v in base["selected"]] == [word(v) for v in old_base["selected"]],
         "parent pre2 selected")
    new_keys = {NEW_STAGE + "." + field for field in NEW_FIELDS}
    need(set(base["stage_scalars"]) == set(old_base["stage_scalars"]) | new_keys,
         "new D1 amount stage inventory")
    for key, value in old_base["stage_scalars"].items():
        exact(base["stage_scalars"][key], value, "parent baseline stage: " + key)
        need(base["stage_types"][key] == old_base["stage_types"][key], "parent dtype: " + key)
    order = data["stage_numeric_order"]
    need(order == sorted(k for k, typ in base["stage_types"].items() if typ == "f64")
         and len(order) == 226 and len(base["stage_scalars"]) == 234,
         "D1 amount stage order")
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
        jvp[name] = dict(zip(order, finite_vector(direction["stage_jvp"], 226, "D1 JVP " + name)))
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
    native_words = producer_words = 0
    for label, values in (("baseline", base["stage_scalars"]),
                          ("qg_bg17_rel_1e-03_minus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["low_stages"]),
                          ("qg_bg17_rel_1e-03_plus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["high_stages"])):
        rows = capture(label)
        for field in NEW_FIELDS:
            key = NEW_STAGE + "." + field
            need(rows[key]["dtype"] == "f64" and word(values[key]) == rows[key]["raw_hex"].zfill(16),
                 "native D1 applied word: " + label + "/" + key)
            native_words += 1
        for consumer, producer in (("c3_pre_mf_d1.pgmlt_capped", "d1_melt_producer.pgmlt_capped_g"),
                                   ("d1_melt_consumer.gfac_melt", "d1_melt_producer.gfac")):
            need(word(values[consumer]) == rows[producer]["raw_hex"].zfill(16),
                 "D1 producer-to-consumer native word: " + label + "/" + consumer)
            producer_words += 1
        p = values["c3_pre_mf_d1.pgmlt_capped"]
        need(word(p / 20.0) == rows["d1_melt_producer.pgmlt"]["raw_hex"].zfill(16),
             "D1 signed amount/rate distinction: " + label)
        need(all(rows["d1_melt_producer." + k]["raw_hex"].zfill(16) == word(p)
                 for k in ("pgmlt_dt", "pgmlt_capped", "pgmlt_capped_g")),
             "D1 producer cap/gate inactive: " + label)
        need(rows["d1_melt_producer.graupel_active"]["raw_hex"] == "1"
             and rows["d1_melt_producer.warm"]["raw_hex"] == "1",
             "D1 native producer masks: " + label)
    minimum_amount_margin = math.inf
    for label, values in all_cases:
        need(set(values) == set(base["stage_scalars"]), "D1 case stage inventory: " + label)
        minimum_amount_margin = min(minimum_amount_margin, d1_values(values, label))
    terms: dict[str, dict[str, float]] = {}
    for name in DIRECTIONS:
        tangent = jvp[name]
        for key in ("d1_melt_consumer.warm_mask", "d1_melt_consumer.pfrzdtr",
                    "d1_melt_consumer.nfrzdtr"):
            need(tangent[key] == 0.0, "fixed D1 gate/freeze tangent: " + name + "/" + key)
        for key in ("d1_melt_consumer.qr1", "d1_melt_consumer.nr1"):
            need(tangent[key] == 0.0, "pre-graupel rain tangent: " + name + "/" + key)
        a = base["stage_scalars"]["c3_pre_mf_d1.pgmlt_capped"]
        g = base["stage_scalars"]["d1_melt_consumer.gfac_melt"]
        da = tangent["c3_pre_mf_d1.pgmlt_capped"]
        dg = tangent["d1_melt_consumer.gfac_melt"]
        mask = base["stage_scalars"]["d1_melt_consumer.warm_mask"]
        qr_terms = (tangent["d1_melt_consumer.qr1"], -mask * da,
                    -a * tangent["d1_melt_consumer.warm_mask"])
        nr_terms = (tangent["d1_melt_consumer.nr1"], -g * da, -a * dg)
        near_roundoff(tangent["d1_melt_consumer.qr2"], sum(qr_terms), qr_terms,
                      "D1 graupel QR applied tangent: " + name)
        near_roundoff(tangent["d1_melt_consumer.nr2"], sum(nr_terms), nr_terms,
                      "D1 graupel NR applied tangent: " + name)
        terms[name] = {"qr_from_amount": qr_terms[1],
                       "nr_from_amount": nr_terms[1], "nr_from_gfac": nr_terms[2],
                       "dpgmlt_capped": da, "dgfac_melt": dg}
    for field in order:
        a, b = jvp["qg17_relative"][field], jvp["brs17_relative"][field]
        near_roundoff(jvp["joint17_relative"][field], a + b, (a, b),
                      "joint D1 stage linearity: " + field)
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
                     "D1 FD signal resolved: " + name + "/" + field)
                error = abs(observed - predicted) / max(abs(observed), abs(predicted), math.ulp(baseline))
                need(error < 1e-6, "D1 FD signal derivative: " + name + "/" + h + "/" + field)
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
                         "D1 FD one-sided baseline: " + name + "/" + h + "/" + field)
                    max_one_sided = max(max_one_sided, one_error)
    return {
        "schema": "kdm6.native_d1_graupel_applied_cpp_ad_replay.v1",
        "selected_cases": len(all_cases),
        "new_stage_fields": len(NEW_FIELDS),
        "native_d1_applied_words_raw_equal": native_words,
        "native_amount_and_factor_handoffs_raw_equal": producer_words,
        "numeric_stage_tangents_per_direction": len(order),
        "minimum_uncapped_amount_margin": minimum_amount_margin,
        "directional_applied_terms": terms,
        "max_captured_no_cap_signal_error": max_captured_fd,
        "max_uncaptured_small_step_signal_error": max_small_fd,
        "max_one_sided_error": max_one_sided,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified native D1 graupel applied-amount AD: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
