#!/usr/bin/env python3
"""Replay full-call D1 graupel melt amount production and its connected AD."""

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
REPO = HERE.parents[2]
PARENT = EVIDENCE / "native_d1_progb_pid_cpp_ad_2026-11-09"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
NATIVE_PRODUCER = EVIDENCE / "native_d1_melt_producer_ad_2026-11-04"
RUNNER = EVIDENCE / "native_nc_process_graph_cpp_ad_2026-11-08/cpp"
MELT_SOURCE = EVIDENCE / "native_d1_melt_state_ad_2026-11-04/executed_cpp/melt_freeze.cpp"
MELT_SOURCE_PACKET = HERE / "executed_cpp/melt_freeze.cpp"
NATIVE_PRODUCER_REPLAY = NATIVE_PRODUCER / "replay.py"
SLOPE_SOURCE = REPO / "libtorch/src/slope.cpp"
CONSTANTS_SOURCE = REPO / "libtorch/include/kdm6/constants.h"
PROGB_HEADER = REPO / "libtorch/include/kdm6/progb.h"
EXECUTED_PROGB_SOURCE = PRE2 / "executed_cpp/progb.cpp"
MANIFEST_SHA = "e7ddff087c90a4393f4050461067545223fe13adbc05a6ac42f80e3e41ebd364"
PARENT_REPLAY_SHA = "9a7ab154967171526e6080b1f7f3e33476165fc6d7b4825c7847bafdef870ff4"
NATIVE_PRODUCER_REPLAY_SHA = "5c945b47cd018c53d63c4a120a92063ae491da2c4fa7173a4f6bf5a1667ef2fd"
MELT_PARENT_SOURCE_SHA = "de60df10d9bc23c2903549e5f192d3af15c4b7a21ae55655aa6c706570de1c6e"
SLOPE_SOURCE_SHA = "202f7b197ae9f12df9cbca18d92ea0920123b54c4d2b8dbd357aa89e5fc246ec"
CONSTANTS_SOURCE_SHA = "f9e41a49e36414f9247f1a645051ba78b4dc7847bdc084669e4a96516a2a3f74"
PROGB_SOURCE_SHA = "00c2527db1e6801d691ca267bb49495e20c1b6710515933a938262f8a6d4ec97"
PROGB_HEADER_SHA = "76b8510077233b84304b159df103107c324be4ed0d7824dc63e3d0d9f878c6dd"
NATIVE_CAPTURE_SHA256 = {
    "baseline": "be33f81ef06b578bc8b3048be34f8df40c02232578acc6f89b292d80522486ad",
    "qg_bg17_rel_1e-03_minus": "547b01323c206ce76ecd614301474221b7e2a0520933df3833e0e83198d70246",
    "qg_bg17_rel_1e-03_plus": "9ca747c116af3f8b0224c71ab403c1d173255dff39fe640d90e69e1da537a346",
}
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
GFAC_STAGE = "d1_gfac_inputs"
GFAC_FIELDS = ("qg", "t", "rslope_g", "n0go", "qcrmin", "t0c", "gfac_melt")
ENTRY_STAGE = "d1_entry_slope_inputs"
ENTRY_FIELDS = ("qg", "brs_input", "dend", "pidn0g", "rhox", "bg", "rslope_g")
PID_STAGE = "d1_entry_pid_inputs"
PID_FIELDS = ("rhox", "cmg", "pidn0g", "n0g", "g1pdgmg", "g1pmg", "active", "midpoint_trace")
MELT_STAGE = "d1_melt_producer"
MELT_FIELDS = (
    "coeres_g", "coeres_s", "cpm", "delta_brs", "delta_brs_capped", "den", "den_safe",
    "dtcld", "gfac", "gfac_raw", "graupel_active", "mass_den", "n0go", "n0sfac", "n0so",
    "ni", "p", "pgmlt", "pgmlt_capped", "pgmlt_capped_g", "pgmlt_dt", "pgmlt_raw",
    "pgmlt_sum", "pgmlt_term1", "pgmlt_term2", "precg1", "precg2", "precs1", "precs2",
    "psmlt", "psmlt_capped", "psmlt_capped_g", "psmlt_dt", "psmlt_raw", "psmlt_sum",
    "psmlt_term1", "psmlt_term2", "qcrmin", "qg", "qi", "qs", "rhox", "rhox_div",
    "rslope2_g", "rslope2_s", "rslope_g", "rslope_s", "rslopeb_g", "rslopeb_s",
    "rslopemu_g", "rslopemu_s", "sfac", "sfac_raw", "snow_active", "t", "t0c", "t1",
    "warm", "work2", "xka_val", "xka_val_g", "xlf",
)
MELT_BOOL_FIELDS = {"warm", "snow_active", "graupel_active"}
MELT_DERIVED_FIELDS = (
    "den_safe", "xka_val", "coeres_s", "psmlt_term1", "psmlt_term2", "psmlt_sum",
    "psmlt_raw", "psmlt_dt", "psmlt_capped", "psmlt_capped_g", "psmlt", "t1",
    "xka_val_g", "coeres_g", "pgmlt_term1", "pgmlt_term2", "pgmlt_sum", "pgmlt_raw",
    "pgmlt_dt", "pgmlt_capped", "pgmlt_capped_g", "pgmlt",
)
MELT_SOURCE_CHECK_FIELDS = tuple(sorted(MELT_BOOL_FIELDS)) + MELT_DERIVED_FIELDS
MELT_FD_SIGNALS = (
    "coeres_g", "pgmlt_term1", "pgmlt_term2", "pgmlt_sum",
    "pgmlt_raw", "pgmlt_dt", "pgmlt",
)
CAP_CROSS = {("qg17_relative", "0.001"), ("brs17_relative", "0.001")}
ENTRY_SIGNALS = tuple(ENTRY_STAGE + "." + name for name in (
    "qg", "brs_input", "pidn0g", "rhox", "bg", "rslope_g"
))
PID_SIGNALS = (PID_STAGE + ".cmg",)
DOMAIN_FLOOR = 1.0e-30
PI = 3.14159265358979323846
BRS_MIN = 1.0e-15
QCRMIN = 1.0e-9
RHO_MIN = 100.0
RHO_MAX = 900.0
DMG = 3.0
ALPHA = struct.unpack(">f", struct.pack(">f", 1.0 / (DMG + 1.0)))[0]
SIGNALS = (
    "c3_pre_mf_d1.pgmlt_capped", "d1_melt_consumer.gfac_melt",
    "d1_melt_consumer.qr2", "d1_melt_consumer.nr2",
    "d1_gfac_inputs.gfac_melt", "d1_gfac_inputs.qg", "d1_gfac_inputs.rslope_g",
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def ulp_distance(a: float, b: float) -> int:
    need(math.isfinite(a) and math.isfinite(b) and a >= 0.0 and b >= 0.0,
         "ULP distance expects finite nonnegative values")
    return abs(int(word(a), 16) - int(word(b), 16))


def source_order_rslope(qg: float, dend: float, pidn0g: float) -> tuple[float, float, float]:
    denominator = max(qg * dend, DOMAIN_FLOOR)
    ratio = pidn0g / denominator
    lamda = math.exp(math.log(max(ratio, DOMAIN_FLOOR)) * ALPHA)
    return 1.0 / lamda, denominator, ratio


def source_order_cmg(rhox: float) -> float:
    return (PI * rhox) / 6.0


def source_order_pidn0g(cmg: float, n0g: float, g1pdgmg: float, g1pmg: float) -> float:
    return ((cmg * n0g) * g1pdgmg) / g1pmg


def xka_scalar(t: float, den: float) -> float:
    safe_t = max(t, 1.0)
    viscos = (1.496e-6 * (safe_t * math.sqrt(safe_t))) / (safe_t + 120.0) / den
    return (1.414e3 * viscos) * den


def source_order_melt_producer(values: dict) -> dict[str, float | bool]:
    """Independent scalar f64 replay of the #553 D1 snow/graupel source order."""
    def x(name: str) -> float:
        return values[MELT_STAGE + "." + name]

    t = x("t")
    qmin, xlf, t0, dt = (x(name) for name in ("qcrmin", "xlf", "t0c", "dtcld"))
    cpm = x("cpm")
    warm = t > t0
    snow_active = warm and x("qs") > 0.0
    graupel_active = warm and x("qg") > 0.0
    den_safe = max(x("mass_den"), qmin)
    xka0 = xka_scalar(t, x("den"))
    coeres_s = (x("rslope2_s") * math.sqrt(max(x("rslope_s") * x("rslopeb_s"), qmin))) * x("rslopemu_s")
    ps1 = ((x("precs1") * x("n0so")) * x("rslope2_s")) * x("rslopemu_s")
    ps2 = ((x("precs2") * x("n0so")) * x("work2")) * coeres_s
    ps_sum = ps1 + ps2
    ps_raw = (((((xka0 / xlf) * (t0 - t)) * x("n0sfac")) * math.pi / 2.0) * ps_sum) / den_safe
    ps_dt = ps_raw * dt
    ps_cap = min(max(ps_dt, -x("qs")), 0.0)
    ps = ps_cap if snow_active else 0.0
    t1 = t + (xlf / cpm) * ps
    xkag = xka_scalar(t1, x("den"))
    coeres_g = (x("rslope2_g") * math.sqrt(max(x("rslope_g") * x("rslopeb_g"), qmin))) * x("rslopemu_g")
    pg1 = ((x("precg1") * x("n0go")) * x("rslope2_g")) * x("rslopemu_g")
    pg2 = ((x("precg2") * x("n0go")) * x("work2")) * coeres_g
    pg_sum = pg1 + pg2
    pg_raw = (((((xkag / xlf) * (t0 - t1)) * math.pi / 2.0) * pg_sum) / den_safe)
    pg_dt = pg_raw * dt
    pg_cap = min(max(pg_dt, -x("qg")), 0.0)
    pg = pg_cap if graupel_active else 0.0
    return {
        "warm": warm, "snow_active": snow_active, "graupel_active": graupel_active,
        "den_safe": den_safe, "xka_val": xka0, "coeres_s": coeres_s,
        "psmlt_term1": ps1, "psmlt_term2": ps2, "psmlt_sum": ps_sum,
        "psmlt_raw": ps_raw, "psmlt_dt": ps_dt, "psmlt_capped": ps_cap,
        "psmlt_capped_g": ps, "psmlt": ps / dt, "t1": t1,
        "xka_val_g": xkag, "coeres_g": coeres_g,
        "pgmlt_term1": pg1, "pgmlt_term2": pg2, "pgmlt_sum": pg_sum,
        "pgmlt_raw": pg_raw, "pgmlt_dt": pg_dt, "pgmlt_capped": pg_cap,
        "pgmlt_capped_g": pg, "pgmlt": pg / dt,
    }


def exact(a: float, b: float, why: str) -> None:
    need(word(a) == word(b), why)


def near_roundoff(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    need(math.isfinite(a) and math.isfinite(b), why + " finite")
    scale = max(abs(a), abs(b), 1.0)
    bound = 16 * math.ulp(scale) + 2e-14 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def near_chain(a: float, b: float, terms: tuple[float, ...], why: str) -> None:
    """Roundoff bound scaled to the new producer signal, including tiny rates."""
    need(math.isfinite(a) and math.isfinite(b), why + " finite")
    bound = 16 * math.ulp(max(abs(a), abs(b))) + 2e-14 * sum(map(abs, terms))
    need(abs(a - b) <= bound, why)


def finite_vector(value: object, count: int, why: str) -> list[float]:
    need(isinstance(value, list) and len(value) == count, why + " length")
    need(all(isinstance(x, (float, int)) and math.isfinite(x) for x in value), why + " finite")
    return [float(x) for x in value]


def fixed_manifest() -> None:
    need(MANIFEST_SHA != "PENDING", "packet manifest SHA has not been pinned")
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_d1_melt_amount_producer_cpp_ad_packet.v1", "manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "executed_cpp")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(data["files"]) == actual, "packet file inventory")
    for name, digest in data["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #566 replay source")
    spec = importlib.util.spec_from_file_location("d1_progb_pid_parent", source)
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.replay()
    need(summary["selected_cases"] == 25 and summary["new_entry_pid_stage_fields"] == 8
         and summary["numeric_stage_tangents_per_direction"] == 247
         and summary["native_d1_applied_words_raw_equal"] == 78
         and summary["native_d1_entry_anchor_words_raw_equal"] == 18,
         "verified #566 parent")
    summary["cap_windows"] = module.parent_replay()["cap_windows"]
    return summary


def provenance(original: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_d1_melt_amount_producer_cpp_ad_build.v1", "build schema")
    need(run["schema"] == "kdm6.native_d1_melt_amount_producer_cpp_ad_run.v1"
         and run["returncode"] == 0, "run schema/status")
    need(sha(NATIVE_PRODUCER_REPLAY.read_bytes()) == NATIVE_PRODUCER_REPLAY_SHA,
         "pinned 2026-11-04 conditional melt formula source")
    for key, path in {
        "runner_source": RUNNER / "main.cpp",
        "runner_cmake": RUNNER / "CMakeLists.txt",
        "parent_coordinator": PARENT / "executed_cpp/coordinator.cpp",
        "executed_coordinator": HERE / "executed_cpp/coordinator.cpp",
        "melt_freeze_source": MELT_SOURCE_PACKET,
        "parent_melt_freeze_source": MELT_SOURCE,
        "slope_source": SLOPE_SOURCE,
        "constants_header": CONSTANTS_SOURCE,
        "progb_source": EXECUTED_PROGB_SOURCE,
        "progb_header": PROGB_HEADER,
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
    parent_source = (PARENT / "executed_cpp/coordinator.cpp").read_bytes()
    source_melt = (HERE / "executed_cpp/melt_freeze.cpp").read_bytes()
    parent_melt = MELT_SOURCE.read_bytes()
    hook_function_before = b'    stage_tensors.clear();\n}\n'
    hook_function_after = (b'    stage_tensors.clear();\n}\n'
                           b'bool stage_hook_enabled() noexcept { return pre2_input_hook_enabled; }\n')
    hook_before = (b'        name == "d1_entry_slope_inputs" || name == "d1_entry_pid_inputs" ||\n'
                   b'        name == "c3_pre_mf_d1" || name == "fd_snap_a" ||\n')
    hook_after = (b'        name == "d1_entry_slope_inputs" || name == "d1_entry_pid_inputs" ||\n'
                  b'        name == "d1_melt_producer" ||\n'
                  b'        name == "c3_pre_mf_d1" || name == "fd_snap_a" ||\n')
    expected_coordinator = parent_source.replace(hook_function_before, hook_function_after, 1)
    need(expected_coordinator != parent_source, "unique D1 melt stage-hook function")
    expected_coordinator = expected_coordinator.replace(hook_before, hook_after, 1)
    need(source == expected_coordinator, "D1 melt coordinator hook restores exact #566 source")
    melt_namespace_before = b'namespace kdm6 {\n'
    melt_namespace_after = (b'namespace kdm6 {\n'
                            b'namespace testing { bool stage_hook_enabled() noexcept; }\n')
    melt_if_before = b'    if (native_capture_active()) {\n'
    melt_if_after = b'    if (native_capture_active() || testing::stage_hook_enabled()) {\n'
    expected_melt = parent_melt.replace(melt_namespace_before, melt_namespace_after, 1)
    need(expected_melt != parent_melt, "unique melt stage-hook declaration")
    expected_melt = expected_melt.replace(melt_if_before, melt_if_after, 1)
    need(source_melt == expected_melt, "D1 melt capture hook restores exact parent melt source")
    patch = gzip.decompress((HERE / "executed_cpp/instrumentation.patch.gz").read_bytes())
    need(sha(SLOPE_SOURCE.read_bytes()) == SLOPE_SOURCE_SHA
         and sha(CONSTANTS_SOURCE.read_bytes()) == CONSTANTS_SOURCE_SHA
         and sha(EXECUTED_PROGB_SOURCE.read_bytes()) == PROGB_SOURCE_SHA
         and sha(PROGB_HEADER.read_bytes()) == PROGB_HEADER_SHA,
         "pinned slope/branch source files")
    need(build["sha256"]["executed_coordinator"] == sha(source)
         and build["sha256"]["parent_coordinator"] == sha(parent_source)
         and build["sha256"]["melt_freeze_source"] == sha(source_melt)
         and build["sha256"]["parent_melt_freeze_source"] == sha(parent_melt),
         "D1 melt source hashes")
    need(b'd1_melt_producer' in patch and b'stage_hook_enabled' in patch,
         "D1 melt instrumentation patch identity")


def capture(label: str) -> dict[str, dict[str, str]]:
    need(label in NATIVE_CAPTURE_SHA256, "native producer capture role")
    capture_path = PRE2 / "raw/cases" / (label + ".csv.gz")
    compressed = capture_path.read_bytes()
    need(sha(compressed) == NATIVE_CAPTURE_SHA256[label], "native producer capture SHA: " + label)
    raw = gzip.decompress(compressed).decode()
    lines = raw.splitlines()
    need(raw.endswith("status=complete\n"), "complete native capture: " + label)
    need(len(lines) >= 4 and lines[2] ==
         "# selected_runtime_call=1; first_one_step_call=1; selected_B_zero=0; K=39; max_rows=20000; max_bytes=6291456",
         "#553 runtime/one-step capture identity: " + label)
    rows = csv.DictReader(line for line in io.StringIO(raw) if not line.startswith("#"))
    selected = {}
    for row in rows:
        if row["k_zero"] != "23":
            continue
        if row["stage"] == MELT_STAGE:
            need((row["one_step_call"], row["runtime_call"], row["substep"], row["b_zero"], row["B"], row["K"])
                 == ("1", "1", "0", "0", "1", "39"),
                 "#553 selected producer call identity: " + label)
        key = row["stage"] + "." + row["field"]
        need(key not in selected, "#553 selected producer field uniqueness: " + label + "/" + key)
        selected[key] = row
    return selected


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


def gfac_values(values: dict, why: str) -> tuple[float, float]:
    """Check the active, unclamped D1 graupel factor in source operation order."""
    qg = values[GFAC_STAGE + ".qg"]
    temp = values[GFAC_STAGE + ".t"]
    rslope = values[GFAC_STAGE + ".rslope_g"]
    n0go = values[GFAC_STAGE + ".n0go"]
    qcrmin = values[GFAC_STAGE + ".qcrmin"]
    t0c = values[GFAC_STAGE + ".t0c"]
    gfac = values[GFAC_STAGE + ".gfac_melt"]
    need(qg > qcrmin > 0.0 and temp > t0c and rslope > 0.0 and n0go > 0.0,
         why + " active unclamped warm graupel branch")
    # The executed expression multiplies first, then divides by max(qg,qcrmin).
    # On the checked qg>qcrmin branch, the denominator is exactly qg.
    exact((rslope * n0go) / qg, gfac, why + " source-order D1 gfac")
    exact(gfac, values["d1_melt_consumer.gfac_melt"], why + " captured consumer gfac")
    exact(qg, values["d1_melt_consumer.qg_before"], why + " captured consumer qg")
    exact(temp, values["c3_pre_mf_d1.t_before"], why + " captured D1 temperature")
    return qg - qcrmin, temp - t0c


def gfac_jvp_terms(values: dict, tangent: dict) -> tuple[float, float, float]:
    qg = values[GFAC_STAGE + ".qg"]
    rslope = values[GFAC_STAGE + ".rslope_g"]
    n0go = values[GFAC_STAGE + ".n0go"]
    return (
        (n0go / qg) * tangent[GFAC_STAGE + ".rslope_g"],
        (rslope / qg) * tangent[GFAC_STAGE + ".n0go"],
        -((rslope * n0go) / (qg * qg)) * tangent[GFAC_STAGE + ".qg"],
    )


def entry_slope_values(values: dict, why: str) -> dict[str, float | int]:
    """Check active entry-slope gates and replay the source-order D1 slope."""
    qg = values[ENTRY_STAGE + ".qg"]
    brs = values[ENTRY_STAGE + ".brs_input"]
    dend = values[ENTRY_STAGE + ".dend"]
    pidn0g = values[ENTRY_STAGE + ".pidn0g"]
    bg = values[ENTRY_STAGE + ".bg"]
    rhox = values[ENTRY_STAGE + ".rhox"]
    rslope = values[ENTRY_STAGE + ".rslope_g"]
    qcrmin = values[GFAC_STAGE + ".qcrmin"]
    exact(qcrmin, QCRMIN, why + " slope/ProgB QCRMIN constant")
    need(qg > qcrmin > 0.0, why + " active graupel slope mask")
    progb_active = qg > qcrmin or brs > BRS_MIN
    need(progb_active, why + " active ProgB gate")
    need(dend > 0.0 and pidn0g > 0.0 and math.isfinite(bg) and math.isfinite(rhox),
         why + " finite positive slope inputs")
    source_rslope, denominator, ratio = source_order_rslope(qg, dend, pidn0g)
    need(denominator > DOMAIN_FLOOR and ratio > DOMAIN_FLOOR,
         why + " unclamped denominator and ratio")
    # Execute the f64 ProgB density path in source order. The output is recorded
    # at entry preamble; this is separate from parent native17 cap-window status.
    bg_denominator = max(brs, BRS_MIN)
    rhox_raw = qg / bg_denominator
    expected_rhox = min(RHO_MAX, max(RHO_MIN, rhox_raw))
    exact(expected_rhox, rhox, why + " entry ProgB density source order")
    expected_bg = qg / expected_rhox
    exact(expected_bg, bg, why + " entry ProgB bg source order")
    distance = ulp_distance(rslope, source_rslope)
    need(distance <= 8, why + " source-order entry rslope_g within 8 ULP")
    exact(qg, values[GFAC_STAGE + ".qg"], why + " D1 consumer qg value handoff")
    exact(rslope, values[GFAC_STAGE + ".rslope_g"], why + " D1 consumer rslope_g value handoff")
    if rhox_raw < RHO_MIN:
        rhox_branch = "lower_clamp"
    elif rhox_raw > RHO_MAX:
        rhox_branch = "upper_cap"
    elif rhox_raw == RHO_MIN:
        rhox_branch = "lower_boundary"
    elif rhox_raw == RHO_MAX:
        rhox_branch = "upper_boundary"
    else:
        rhox_branch = "interior"
    return {
        "qg_to_qcrmin_margin": qg - qcrmin,
        "denominator_to_floor_margin": qg * dend - DOMAIN_FLOOR,
        "ratio_to_floor_margin": ratio - DOMAIN_FLOOR,
        "progb_active": progb_active,
        "brs_to_BRS_MIN_margin": brs - BRS_MIN,
        "rhox_raw": rhox_raw,
        "rhox_branch": rhox_branch,
        "rhox_to_100_margin": rhox - RHO_MIN,
        "rhox_to_900_margin": RHO_MAX - rhox,
        "bg_source_expected": expected_bg,
        "rslope_g_ulp_distance": distance,
        "expected_rslope_g": source_rslope,
        "denominator": denominator,
        "ratio": ratio,
    }


def entry_slope_jvp_terms(values: dict, tangent: dict) -> tuple[float, float, float]:
    qg = values[ENTRY_STAGE + ".qg"]
    dend = values[ENTRY_STAGE + ".dend"]
    pidn0g = values[ENTRY_STAGE + ".pidn0g"]
    rslope = values[ENTRY_STAGE + ".rslope_g"]
    return (
        ALPHA * rslope * (tangent[ENTRY_STAGE + ".qg"] / qg),
        ALPHA * rslope * (tangent[ENTRY_STAGE + ".dend"] / dend),
        -ALPHA * rslope * (tangent[ENTRY_STAGE + ".pidn0g"] / pidn0g),
    )


def pid_values(values: dict, why: str) -> None:
    active = values[PID_STAGE + ".active"]
    midpoint_trace = values[PID_STAGE + ".midpoint_trace"]
    active_value = active is True or (isinstance(active, (int, float)) and active == 1.0)
    qg = values[ENTRY_STAGE + ".qg"]
    brs_input = values[ENTRY_STAGE + ".brs_input"]
    qcrmin = values[GFAC_STAGE + ".qcrmin"]
    active_gate = qg > qcrmin or brs_input > BRS_MIN
    need(active_value == active_gate, why + " active ProgB gate matches source predicate")
    need(midpoint_trace == 0.0, why + " midpoint trace disabled")
    rhox = values[PID_STAGE + ".rhox"]
    cmg = values[PID_STAGE + ".cmg"]
    pidn0g = values[PID_STAGE + ".pidn0g"]
    n0g = values[PID_STAGE + ".n0g"]
    g1pdgmg = values[PID_STAGE + ".g1pdgmg"]
    g1pmg = values[PID_STAGE + ".g1pmg"]
    need(n0g > 0.0 and g1pdgmg > 0.0 and g1pmg > 0.0,
         why + " finite positive Progb constants")
    exact(source_order_cmg(rhox), cmg, why + " source-order cmg")
    exact(source_order_pidn0g(cmg, n0g, g1pdgmg, g1pmg),
          pidn0g, why + " source-order pidn0g")
    exact(rhox, values[ENTRY_STAGE + ".rhox"], why + " parent entry rhox value handoff")
    exact(pidn0g, values[ENTRY_STAGE + ".pidn0g"], why + " parent entry pidn0g value handoff")


def pid_jvp_terms(values: dict, tangent: dict) -> tuple[float, float]:
    cmg = values[PID_STAGE + ".cmg"]
    n0g = values[PID_STAGE + ".n0g"]
    g1pdgmg = values[PID_STAGE + ".g1pdgmg"]
    g1pmg = values[PID_STAGE + ".g1pmg"]
    dcmg = tangent[PID_STAGE + ".cmg"]
    dn0g = tangent[PID_STAGE + ".n0g"]
    return (
        ((dcmg * n0g) * g1pdgmg) / g1pmg,
        ((cmg * dn0g) * g1pdgmg) / g1pmg,
    )


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
    new_keys = ({NEW_STAGE + "." + field for field in NEW_FIELDS}
                | {GFAC_STAGE + "." + field for field in GFAC_FIELDS}
                | {ENTRY_STAGE + "." + field for field in ENTRY_FIELDS}
                | {PID_STAGE + "." + field for field in PID_FIELDS}
                | {MELT_STAGE + "." + field for field in MELT_FIELDS})
    need(set(base["stage_scalars"]) == set(old_base["stage_scalars"]) | new_keys,
         "new D1 amount stage inventory")
    for key, value in old_base["stage_scalars"].items():
        exact(base["stage_scalars"][key], value, "parent baseline stage: " + key)
        need(base["stage_types"][key] == old_base["stage_types"][key], "parent dtype: " + key)
    order = data["stage_numeric_order"]
    need(order == sorted(k for k, typ in base["stage_types"].items() if typ == "f64")
         and len(order) == 306 and len(base["stage_scalars"]) == 318,
         "D1 melt producer stage order")
    need(base["stage_types"][PID_STAGE + ".active"] == "bool",
         "D1 entry PID active dtype")
    for field in set(PID_FIELDS) - {"active"}:
        need(base["stage_types"][PID_STAGE + "." + field] == "f64",
             "D1 entry PID field dtype: " + field)
    for field in MELT_FIELDS:
        expected_type = "bool" if field in MELT_BOOL_FIELDS else "f64"
        need(base["stage_types"][MELT_STAGE + "." + field] == expected_type,
             "D1 melt producer field dtype: " + field)
    for field, expected in (("n0g", 4_000_000.0),
                            ("g1pdgmg", 6.000000000000001), ("g1pmg", 1.0)):
        exact(base["stage_scalars"][PID_STAGE + "." + field], expected,
              "archived live ProgB parameter word: " + field)
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
        jvp[name] = dict(zip(order, finite_vector(direction["stage_jvp"], 306, "D1 JVP " + name)))
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
    native_words = producer_words = native_gfac_words = entry_anchor_words = melt_native_words = 0
    native_capture_receipts = []
    for label, values in (("baseline", base["stage_scalars"]),
                          ("qg_bg17_rel_1e-03_minus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["low_stages"]),
                          ("qg_bg17_rel_1e-03_plus",
                           data["directions"]["joint17_relative"]["finite_differences"]["0.001"]["high_stages"])):
        rows = capture(label)
        native_capture_receipts.append({
            "packet": "native_c2c_pre2_upstream_2026-11-07",
            "file": "raw/cases/" + label + ".csv.gz",
            "sha256": NATIVE_CAPTURE_SHA256[label],
        })
        for field in NEW_FIELDS:
            key = NEW_STAGE + "." + field
            need(rows[key]["dtype"] == "f64" and word(values[key]) == rows[key]["raw_hex"].zfill(16),
                 "native D1 applied word: " + label + "/" + key)
            native_words += 1
        native_gfac_names = {
            "qg": "qg", "t": "t", "rslope_g": "rslope_g", "n0go": "n0go",
            "qcrmin": "qcrmin", "t0c": "t0c", "gfac_melt": "gfac",
        }
        for field, native_field in native_gfac_names.items():
            key = GFAC_STAGE + "." + field
            native_key = "d1_melt_producer." + native_field
            need(rows[native_key]["dtype"] == "f64"
                 and word(values[key]) == rows[native_key]["raw_hex"].zfill(16),
                 "native D1 gfac input word: " + label + "/" + key)
            native_gfac_words += 1
        native_entry_names = {
            "qg": ("d1_upstream_entry", "qg"),
            "brs_input": ("d1_upstream_entry", "brs"),
            "dend": ("d1_upstream_entry", "dend"),
            "rhox": ("d1_upstream_producer", "rhox"),
            "bg": ("d1_upstream_producer", "bg"),
            "rslope_g": ("d1_melt_producer", "rslope_g"),
        }
        for field, (native_stage, native_field) in native_entry_names.items():
            key = ENTRY_STAGE + "." + field
            native_key = native_stage + "." + native_field
            need(rows[native_key]["dtype"] == "f64"
                 and word(values[key]) == rows[native_key]["raw_hex"].zfill(16),
                 "native D1 entry input word: " + label + "/" + key)
            entry_anchor_words += 1
        for field in MELT_FIELDS:
            key = MELT_STAGE + "." + field
            native_row = rows[key]
            if field in MELT_BOOL_FIELDS:
                expected_raw = "1" if bool(values[key]) else "0"
                need(native_row["dtype"] == "bool" and native_row["raw_hex"] == expected_raw,
                     "native D1 melt producer bool word: " + label + "/" + field)
            else:
                need(native_row["dtype"] == "f64"
                     and word(values[key]) == native_row["raw_hex"].zfill(16),
                     "native D1 melt producer f64 word: " + label + "/" + field)
            melt_native_words += 1
        # pidn0g is newly live-captured by this stage. #553 did not record an
        # independent native pidn0g word, so it is checked by the source replay
        # and the connected FD/JVP chain only.
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
    minimum_gfac_qg_margin = math.inf
    minimum_gfac_temperature_margin = math.inf
    minimum_entry_qg_margin = math.inf
    minimum_entry_denominator_margin = math.inf
    minimum_entry_ratio_margin = math.inf
    maximum_entry_slope_ulp_distance = 0
    entry_branch_rows = []
    melt_margins = {
        "warm_temperature_K": math.inf,
        "snow_lower_amount": math.inf,
        "snow_upper_amount": math.inf,
        "graupel_lower_amount": math.inf,
        "graupel_upper_amount": math.inf,
        "mass_den_floor": math.inf,
        "graupel_sqrt_floor": math.inf,
        "t1_one_kelvin": math.inf,
    }
    for field in PID_FIELDS:
        if field != "active":
            need(math.isfinite(float(base["stage_scalars"][PID_STAGE + "." + field])),
                 "finite PID stage value: " + field)
    for label, values in all_cases:
        need(set(values) == set(base["stage_scalars"]), "D1 case stage inventory: " + label)
        melt_replay = source_order_melt_producer(values)
        for field in MELT_SOURCE_CHECK_FIELDS:
            actual = values[MELT_STAGE + "." + field]
            expected = melt_replay[field]
            if field in MELT_BOOL_FIELDS:
                need(bool(actual) == bool(expected), "D1 melt source-order gate: " + label + "/" + field)
            else:
                exact(actual, expected, "D1 melt source-order: " + label + "/" + field)
        exact(values[MELT_STAGE + ".psmlt_capped_g"], values["c3_pre_mf_d1.psmlt_capped"],
              "D1 snow applied amount value handoff: " + label)
        exact(values[MELT_STAGE + ".pgmlt_capped_g"], values["c3_pre_mf_d1.pgmlt_capped"],
              "D1 graupel applied amount A value handoff: " + label)
        for producer, consumer in (("t", "c3_pre_mf_d1.t_before"),
                                   ("qg", GFAC_STAGE + ".qg"),
                                   ("rslope_g", GFAC_STAGE + ".rslope_g")):
            exact(values[MELT_STAGE + "." + producer], values[consumer],
                  "D1 melt input value handoff: " + label + "/" + producer)
        exact(values[MELT_STAGE + ".gfac"], values[GFAC_STAGE + ".gfac_melt"],
              "D1 producer gfac value handoff: " + label)
        def m(field: str) -> float:
            return values[MELT_STAGE + "." + field]
        need(all(bool(m(field)) for field in MELT_BOOL_FIELDS),
             "D1 selected melt gates active: " + label)
        margins = {
            "warm_temperature_K": m("t") - m("t0c"),
            "snow_lower_amount": m("psmlt_dt") + m("qs"),
            "snow_upper_amount": -m("psmlt_dt"),
            "graupel_lower_amount": m("pgmlt_dt") + m("qg"),
            "graupel_upper_amount": -m("pgmlt_dt"),
            "mass_den_floor": m("mass_den") - m("qcrmin"),
            "graupel_sqrt_floor": m("rslope_g") * m("rslopeb_g") - m("qcrmin"),
            "t1_one_kelvin": m("t1") - 1.0,
        }
        for field, margin in margins.items():
            need(margin > 0.0, "D1 selected melt interior margin: " + label + "/" + field)
            melt_margins[field] = min(melt_margins[field], margin)
        for field in ("t1", "xka_val_g", "psmlt_capped_g", "cpm", "den", "den_safe", "xlf", "t0c", "dtcld"):
            exact(m(field), base["stage_scalars"][MELT_STAGE + "." + field],
                  "fixed selected melt thermal input: " + label + "/" + field)
        minimum_amount_margin = min(minimum_amount_margin, d1_values(values, label))
        qg_margin, temperature_margin = gfac_values(values, label)
        minimum_gfac_qg_margin = min(minimum_gfac_qg_margin, qg_margin)
        minimum_gfac_temperature_margin = min(minimum_gfac_temperature_margin, temperature_margin)
        entry_diag = entry_slope_values(values, label)
        minimum_entry_qg_margin = min(minimum_entry_qg_margin, entry_diag["qg_to_qcrmin_margin"])
        minimum_entry_denominator_margin = min(
            minimum_entry_denominator_margin, entry_diag["denominator_to_floor_margin"])
        minimum_entry_ratio_margin = min(minimum_entry_ratio_margin, entry_diag["ratio_to_floor_margin"])
        maximum_entry_slope_ulp_distance = max(
            maximum_entry_slope_ulp_distance, int(entry_diag["rslope_g_ulp_distance"]))
        entry_branch_rows.append({"case": label, **entry_diag})
        for field in ("qcrmin", "t0c", "n0go"):
            exact(values[GFAC_STAGE + "." + field],
                  base["stage_scalars"][GFAC_STAGE + "." + field],
                  "fixed D1 gfac input across cases: " + label + "/" + field)
        exact(values[ENTRY_STAGE + ".dend"],
              base["stage_scalars"][ENTRY_STAGE + ".dend"],
              "fixed D1 entry forcing across cases: " + label + "/dend")
        pid_values(values, label)
        for field in ("n0g", "g1pdgmg", "g1pmg", "midpoint_trace"):
            exact(values[PID_STAGE + "." + field],
                  base["stage_scalars"][PID_STAGE + "." + field],
                  "fixed D1 PID input across cases: " + label + "/" + field)
        need(values[PID_STAGE + ".active"] == base["stage_scalars"][PID_STAGE + ".active"],
             "fixed D1 PID active control across cases: " + label)
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
        dgfac_terms = gfac_jvp_terms(base["stage_scalars"], tangent)
        dgfac = tangent[GFAC_STAGE + ".gfac_melt"]
        near_roundoff(dgfac, math.fsum(dgfac_terms), dgfac_terms,
                      "D1 gfac three-input chain: " + name)
        exact(dgfac, tangent["d1_melt_consumer.gfac_melt"],
              "D1 gfac stage-to-consumer tangent: " + name)
        exact(tangent[GFAC_STAGE + ".qg"], tangent["d1_melt_consumer.qg_before"],
              "D1 qg input tangent link: " + name)
        exact(tangent[GFAC_STAGE + ".t"], tangent["c3_pre_mf_d1.t_before"],
              "D1 temperature input tangent link: " + name)
        for field in ("qcrmin", "t0c", "n0go"):
            exact(tangent[GFAC_STAGE + "." + field], 0.0,
                  "constant D1 gfac input tangent: " + name + "/" + field)
        terms[name].update({
            "dgfac_from_rslope_g": dgfac_terms[0],
            "dgfac_from_n0go": dgfac_terms[1],
            "dgfac_from_qg": dgfac_terms[2],
        })
        entry_terms = entry_slope_jvp_terms(base["stage_scalars"], tangent)
        entry_drslope = tangent[ENTRY_STAGE + ".rslope_g"]
        near_roundoff(entry_drslope, math.fsum(entry_terms), entry_terms,
                      "D1 entry slope three-input chain: " + name)
        exact(tangent[ENTRY_STAGE + ".dend"], 0.0,
              "fixed D1 entry forcing tangent: " + name + "/dend")
        exact(tangent[ENTRY_STAGE + ".qg"], tangent[GFAC_STAGE + ".qg"],
              "D1 entry QG tangent handoff: " + name)
        exact(entry_drslope, tangent[GFAC_STAGE + ".rslope_g"],
              "D1 entry rslope_g tangent handoff: " + name)
        terms[name].update({
            "drslope_g_from_qg": entry_terms[0],
            "drslope_g_from_dend": entry_terms[1],
            "drslope_g_from_pidn0g": entry_terms[2],
            "drslope_g": entry_drslope,
        })
        dcmg = tangent[PID_STAGE + ".cmg"]
        dcmg_expected = (PI * tangent[PID_STAGE + ".rhox"]) / 6.0
        near_roundoff(dcmg, dcmg_expected, (dcmg_expected,),
                      "D1 entry cmg JVP chain: " + name)
        pid_terms = pid_jvp_terms(base["stage_scalars"], tangent)
        dpidn0g = tangent[PID_STAGE + ".pidn0g"]
        near_roundoff(dpidn0g, math.fsum(pid_terms), pid_terms,
                      "D1 entry pidn0g product JVP chain: " + name)
        exact(tangent[PID_STAGE + ".rhox"], tangent[ENTRY_STAGE + ".rhox"],
              "D1 entry PID rhox tangent handoff: " + name)
        exact(dpidn0g, tangent[ENTRY_STAGE + ".pidn0g"],
              "D1 entry PID pidn0g tangent handoff: " + name)
        for field in ("n0g", "g1pdgmg", "g1pmg", "midpoint_trace"):
            exact(tangent[PID_STAGE + "." + field], 0.0,
                  "fixed D1 PID parameter tangent: " + name + "/" + field)
        terms[name].update({
            "dcmg_from_rhox": dcmg_expected,
            "dpidn0g_from_cmg": pid_terms[0],
            "dpidn0g_from_n0g": pid_terms[1],
            "dcmg": dcmg,
            "dpidn0g": dpidn0g,
        })
        def p(field: str) -> float:
            return base["stage_scalars"][MELT_STAGE + "." + field]

        def d(field: str) -> float:
            return tangent[MELT_STAGE + "." + field]

        for field in ("t", "cpm", "psmlt_capped_g", "xlf", "t0c", "den", "den_safe", "dtcld"):
            need(d(field) == 0.0, "fixed selected melt thermal tangent: " + name + "/" + field)
        for producer, consumer in (("t", "c3_pre_mf_d1.t_before"),
                                   ("psmlt_capped_g", "c3_pre_mf_d1.psmlt_capped"),
                                   ("qg", GFAC_STAGE + ".qg"),
                                   ("rslope_g", GFAC_STAGE + ".rslope_g"),
                                   ("gfac", GFAC_STAGE + ".gfac_melt")):
            exact(d(producer), tangent[consumer],
                  "D1 melt producer tangent handoff: " + name + "/" + producer)
        t1_terms = (
            d("t"),
            (p("psmlt_capped_g") / p("cpm")) * d("xlf"),
            -(p("xlf") * p("psmlt_capped_g") / (p("cpm") ** 2)) * d("cpm"),
            (p("xlf") / p("cpm")) * d("psmlt_capped_g"),
        )
        near_chain(d("t1"), math.fsum(t1_terms), t1_terms,
                   "D1 snow-heated t1 tangent: " + name)
        xka_tangent = p("xka_val_g") * (1.5 / p("t1") - 1.0 / (p("t1") + 120.0)) * d("t1")
        near_chain(d("xka_val_g"), xka_tangent, (xka_tangent,),
                   "D1 graupel xka tangent: " + name)
        coeres_terms = (
            p("coeres_g") * d("rslope2_g") / p("rslope2_g"),
            0.5 * p("coeres_g") * d("rslope_g") / p("rslope_g"),
            0.5 * p("coeres_g") * d("rslopeb_g") / p("rslopeb_g"),
            p("coeres_g") * d("rslopemu_g") / p("rslopemu_g"),
        )
        near_chain(d("coeres_g"), math.fsum(coeres_terms), coeres_terms,
                   "D1 graupel coeres tangent: " + name)
        term1_parts = tuple(p("pgmlt_term1") * d(field) / p(field)
                            for field in ("precg1", "n0go", "rslope2_g", "rslopemu_g"))
        term2_parts = tuple(p("pgmlt_term2") * d(field) / p(field)
                            for field in ("precg2", "n0go", "work2", "coeres_g"))
        near_chain(d("pgmlt_term1"), math.fsum(term1_parts), term1_parts,
                   "D1 graupel term1 tangent: " + name)
        near_chain(d("pgmlt_term2"), math.fsum(term2_parts), term2_parts,
                   "D1 graupel term2 tangent: " + name)
        sum_terms = (d("pgmlt_term1"), d("pgmlt_term2"))
        near_chain(d("pgmlt_sum"), math.fsum(sum_terms), sum_terms,
                   "D1 graupel term sum tangent: " + name)
        raw_terms = (
            p("pgmlt_raw") * d("xka_val_g") / p("xka_val_g"),
            -p("pgmlt_raw") * d("xlf") / p("xlf"),
            p("pgmlt_raw") * (d("t0c") - d("t1")) / (p("t0c") - p("t1")),
            p("pgmlt_raw") * d("pgmlt_sum") / p("pgmlt_sum"),
            -p("pgmlt_raw") * d("den_safe") / p("den_safe"),
        )
        near_chain(d("pgmlt_raw"), math.fsum(raw_terms), raw_terms,
                   "D1 graupel raw-rate tangent: " + name)
        candidate_terms = (p("dtcld") * d("pgmlt_raw"), p("pgmlt_raw") * d("dtcld"))
        near_chain(d("pgmlt_dt"), math.fsum(candidate_terms), candidate_terms,
                   "D1 graupel time candidate tangent: " + name)
        exact(d("pgmlt_capped"), d("pgmlt_dt"),
              "D1 graupel inactive cap tangent: " + name)
        exact(d("pgmlt_capped_g"), d("pgmlt_capped"),
              "D1 graupel active gate tangent: " + name)
        exact(d("pgmlt_capped_g"), da,
              "D1 graupel applied amount A tangent handoff: " + name)
        rate_terms = (d("pgmlt_capped_g") / p("dtcld"),
                      -p("pgmlt_capped_g") * d("dtcld") / (p("dtcld") ** 2))
        near_chain(d("pgmlt"), math.fsum(rate_terms), rate_terms,
                   "D1 graupel applied rate tangent: " + name)
        terms[name].update({
            "dpgmlt_term1": d("pgmlt_term1"),
            "dpgmlt_term2": d("pgmlt_term2"),
            "dpgmlt_sum": d("pgmlt_sum"),
            "dpgmlt_raw": d("pgmlt_raw"),
            "dpgmlt_dt": d("pgmlt_dt"),
            "dA_from_producer": d("pgmlt_capped_g"),
        })
    for field in order:
        a, b = jvp["qg17_relative"][field], jvp["brs17_relative"][field]
        near_roundoff(jvp["joint17_relative"][field], a + b, (a, b),
                      "joint D1 stage linearity: " + field)
    qg0 = data["directions"]["qg17_relative"]["seed_qg17"]
    brs0 = data["directions"]["brs17_relative"]["seed_brs17"]
    max_captured_fd = max_small_fd = max_one_sided = 0.0
    max_entry_fd_relative_error = max_entry_one_sided_relative_error = 0.0
    max_pid_fd_relative_error = max_pid_one_sided_relative_error = 0.0
    fd_resolved_signals = fd_unresolved_zero_signals = 0
    entry_fd_resolved_signals = entry_fd_rounding_floor_cases = 0
    entry_one_sided_rounding_floor_cases = 0
    pid_fd_resolved_signals = pid_fd_rounding_floor_cases = 0
    pid_one_sided_rounding_floor_cases = 0
    melt_fd_resolved_signals = 0
    max_melt_captured_fd = max_melt_small_fd = max_melt_one_sided = 0.0
    minimum_accepted_rhox_upper_margin = math.inf
    fd_branch_classifications = []
    for name in DIRECTIONS:
        for h, pair in data["directions"][name]["finite_differences"].items():
            if (name, h) in CAP_CROSS:
                need(h in parent_summary["cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent density cap crossing")
                fd_branch_classifications.append({
                    "direction": name, "h": h, "classification": "captured_density_cap_crossing",
                    "used_for_smooth_fd_check": False,
                })
                continue
            if h != "1e-06":
                need(h not in parent_summary["cap_windows"][name]["recorded_cap_crossing_steps"],
                     "parent non-crossing density cap")
            fd_branch_classifications.append({
                "direction": name,
                "h": h,
                "classification": ("small_step_no_independent_cap_capture" if h == "1e-06"
                                   else "captured_no_cap_crossing"),
                "used_for_smooth_fd_check": True,
            })
            for side in ("low", "high"):
                rhox = pair[side + "_stages"][ENTRY_STAGE + ".rhox"]
                need(800.0 < rhox < 900.0,
                     "accepted endpoint remains in the declared rhox numeric segment: "
                     + name + "/" + h + "/" + side)
                minimum_accepted_rhox_upper_margin = min(
                    minimum_accepted_rhox_upper_margin, 900.0 - rhox)
            dq = (pair["high_input"][0] - pair["low_input"][0]) / qg0
            db = (pair["high_input"][1] - pair["low_input"][1]) / brs0
            for field in (*SIGNALS, *ENTRY_SIGNALS, *PID_SIGNALS):
                observed = pair["high_stages"][field] - pair["low_stages"][field]
                predicted = jvp["qg17_relative"][field] * dq + jvp["brs17_relative"][field] * db
                baseline = base["stage_scalars"][field]
                threshold = 32 * math.ulp(baseline)
                is_entry_signal = field in ENTRY_SIGNALS
                is_pid_signal = field in PID_SIGNALS
                is_new_signal = is_entry_signal or is_pid_signal
                if abs(observed) <= threshold:
                    need(not is_new_signal,
                         "new D1 producer FD signal resolved above 32 ULP: " + name + "/" + h + "/" + field)
                    need(abs(predicted) <= threshold,
                         "D1 FD unresolved signal has nonzero tangent: " + name + "/" + h + "/" + field)
                    fd_unresolved_zero_signals += 1
                    continue
                fd_resolved_signals += 1
                residual = abs(observed - predicted)
                scale = max(abs(observed), abs(predicted))
                error = residual / max(scale, math.ulp(baseline))
                if is_new_signal:
                    if is_entry_signal:
                        entry_fd_resolved_signals += 1
                    bound = max(1e-6 * scale, 4 * math.ulp(baseline))
                    need(residual <= bound,
                         "D1 producer FD signal derivative: " + name + "/" + h + "/" + field)
                    if residual > 1e-6 * scale:
                        if is_entry_signal:
                            entry_fd_rounding_floor_cases += 1
                        else:
                            pid_fd_rounding_floor_cases += 1
                    if is_pid_signal:
                        pid_fd_resolved_signals += 1
                        max_pid_fd_relative_error = max(max_pid_fd_relative_error, error)
                    else:
                        max_entry_fd_relative_error = max(max_entry_fd_relative_error, error)
                else:
                    need(error < 1e-6, "D1 FD signal derivative: " + name + "/" + h + "/" + field)
                if not is_new_signal:
                    if h == "1e-06":
                        max_small_fd = max(max_small_fd, error)
                    else:
                        max_captured_fd = max(max_captured_fd, error)
                for side in ("low", "high"):
                    inp = pair[side + "_input"]
                    one_obs = pair[side + "_stages"][field] - baseline
                    one_pred = (jvp["qg17_relative"][field] * (inp[0] - qg0) / qg0
                                + jvp["brs17_relative"][field] * (inp[1] - brs0) / brs0)
                    one_residual = abs(one_obs - one_pred)
                    one_scale = max(abs(one_obs), abs(one_pred))
                    one_error = one_residual / max(one_scale, math.ulp(baseline))
                    if is_new_signal:
                        one_bound = max(4 * float(h) * one_scale, 4 * math.ulp(baseline))
                        need(one_residual <= one_bound,
                             "D1 producer one-sided FD: " + name + "/" + h + "/" + field)
                        if one_residual > 4 * float(h) * one_scale:
                            if is_entry_signal:
                                entry_one_sided_rounding_floor_cases += 1
                            else:
                                pid_one_sided_rounding_floor_cases += 1
                        if is_pid_signal:
                            max_pid_one_sided_relative_error = max(
                                max_pid_one_sided_relative_error, one_error)
                        else:
                            max_entry_one_sided_relative_error = max(
                                max_entry_one_sided_relative_error, one_error)
                    else:
                        need(one_error < 4 * float(h),
                             "D1 FD one-sided baseline: " + name + "/" + h + "/" + field)
                    if not is_new_signal:
                        max_one_sided = max(max_one_sided, one_error)
            for signal in MELT_FD_SIGNALS:
                field = MELT_STAGE + "." + signal
                observed = pair["high_stages"][field] - pair["low_stages"][field]
                predicted = jvp["qg17_relative"][field] * dq + jvp["brs17_relative"][field] * db
                baseline = base["stage_scalars"][field]
                ulp = math.ulp(baseline)
                need(abs(observed) > 32 * ulp,
                     "D1 melt FD signal resolved above 32 ULP: " + name + "/" + h + "/" + signal)
                error = abs(observed - predicted) / max(abs(observed), abs(predicted), ulp)
                need(error < 1e-6,
                     "D1 melt FD signal derivative: " + name + "/" + h + "/" + signal)
                melt_fd_resolved_signals += 1
                if h == "1e-06":
                    max_melt_small_fd = max(max_melt_small_fd, error)
                else:
                    max_melt_captured_fd = max(max_melt_captured_fd, error)
                for side in ("low", "high"):
                    inp = pair[side + "_input"]
                    one_observed = pair[side + "_stages"][field] - baseline
                    one_predicted = (
                        jvp["qg17_relative"][field] * (inp[0] - qg0) / qg0
                        + jvp["brs17_relative"][field] * (inp[1] - brs0) / brs0
                    )
                    one_error = abs(one_observed - one_predicted) / max(
                        abs(one_observed), abs(one_predicted), ulp)
                    need(one_error < 4 * float(h),
                         "D1 melt FD one-sided baseline: " + name + "/" + h + "/" + signal)
                    max_melt_one_sided = max(max_melt_one_sided, one_error)
    return {
        "schema": "kdm6.native_d1_melt_amount_producer_cpp_ad_replay.v1",
        "selected_cases": len(all_cases),
        "parent_stage_fields": len(NEW_FIELDS),
        "parent_gfac_stage_fields": len(GFAC_FIELDS),
        "parent_entry_slope_stage_fields": len(ENTRY_FIELDS),
        "new_entry_pid_stage_fields": len(PID_FIELDS),
        "new_melt_producer_stage_fields": len(MELT_FIELDS),
        "melt_source_order_cases": len(all_cases),
        "melt_source_order_fields_per_case": len(MELT_SOURCE_CHECK_FIELDS),
        "native_melt_producer_words_raw_equal": melt_native_words,
        "melt_minimum_branch_margins": melt_margins,
        "melt_amount_parent_value_handoff_cases": len(all_cases),
        "melt_amount_parent_jvp_handoff_directions": len(DIRECTIONS),
        "native_d1_applied_words_raw_equal": native_words,
        "parent_native_d1_gfac_words_raw_equal": native_gfac_words,
        "native_d1_entry_anchor_words_raw_equal": entry_anchor_words,
        "native_capture_receipts": native_capture_receipts,
        "cmg_pidn0g_native_anchor": "no independent #553 producer tap; source-order replay and parent handoff",
        "cmg_pidn0g_native_anchor_words_raw_equal": 0,
        "d1_entry_slope_source_expression": (
            "ratio=pidn0g/max(qg*dend,1e-30); "
            "rslope_g=1/exp(log(max(ratio,1e-30))*float32(1/(DMG+1)))"
        ),
        "source_pins": {
            "slope_source_sha256": SLOPE_SOURCE_SHA,
            "constants_header_sha256": CONSTANTS_SOURCE_SHA,
            "executed_progb_source_sha256": PROGB_SOURCE_SHA,
            "progb_header_sha256": PROGB_HEADER_SHA,
            "parent_melt_source_sha256": MELT_PARENT_SOURCE_SHA,
            "executed_melt_source_sha256": sha(MELT_SOURCE_PACKET.read_bytes()),
        },
        "native_amount_and_factor_handoffs_raw_equal": producer_words,
        "numeric_stage_tangents_per_direction": len(order),
        "entry_pid_source_order_cases": len(all_cases),
        "entry_cmg_source_order_cases": len(all_cases),
        "entry_pidn0g_parent_value_handoff_cases": len(all_cases),
        "entry_pidn0g_parent_jvp_handoff_directions": len(DIRECTIONS),
        "pid_midpoint_trace": base["stage_scalars"][PID_STAGE + ".midpoint_trace"],
        "pid_active_all_cases": all(values[PID_STAGE + ".active"] == 1 for _, values in all_cases),
        "pid_parameter_words": {
            field: base["stage_scalars"][PID_STAGE + "." + field]
            for field in ("n0g", "g1pdgmg", "g1pmg")
        },
        "cmg_source_expression": "(PI * rhox) / 6.0",
        "pidn0g_source_expression": "((cmg * n0g) * g1pdgmg) / g1pmg",
        "minimum_uncapped_amount_margin": minimum_amount_margin,
        "minimum_parent_gfac_qg_branch_margin": minimum_gfac_qg_margin,
        "minimum_parent_gfac_temperature_branch_margin": minimum_gfac_temperature_margin,
        "minimum_entry_qg_branch_margin": minimum_entry_qg_margin,
        "minimum_entry_denominator_floor_margin": minimum_entry_denominator_margin,
        "minimum_entry_ratio_floor_margin": minimum_entry_ratio_margin,
        "minimum_accepted_rhox_upper_margin": minimum_accepted_rhox_upper_margin,
        "maximum_entry_slope_formula_ulp_distance": maximum_entry_slope_ulp_distance,
        "entry_slope_branch_checks": entry_branch_rows,
        "fd_branch_classifications": fd_branch_classifications,
        "fd_resolved_signal_count": fd_resolved_signals,
        "fd_unresolved_zero_signal_count": fd_unresolved_zero_signals,
        "entry_fd_resolved_signal_count": entry_fd_resolved_signals,
        "entry_fd_rounding_floor_cases": entry_fd_rounding_floor_cases,
        "entry_one_sided_rounding_floor_cases": entry_one_sided_rounding_floor_cases,
        "pid_fd_resolved_signal_count": pid_fd_resolved_signals,
        "pid_fd_rounding_floor_cases": pid_fd_rounding_floor_cases,
        "pid_one_sided_rounding_floor_cases": pid_one_sided_rounding_floor_cases,
        "melt_fd_resolved_signal_count": melt_fd_resolved_signals,
        "max_captured_melt_signal_error": max_melt_captured_fd,
        "max_small_step_melt_signal_error": max_melt_small_fd,
        "max_melt_one_sided_error": max_melt_one_sided,
        "pidn0g_fd_via_parent_entry_slope_handoff": True,
        "directional_applied_terms": terms,
        "max_captured_no_cap_signal_error": max_captured_fd,
        "max_uncaptured_small_step_signal_error": max_small_fd,
        "max_one_sided_error": max_one_sided,
        "max_entry_fd_relative_error": max_entry_fd_relative_error,
        "max_entry_one_sided_relative_error": max_entry_one_sided_relative_error,
        "max_pid_fd_relative_error": max_pid_fd_relative_error,
        "max_pid_one_sided_relative_error": max_pid_one_sided_relative_error,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main() -> None:
    print("verified native D1 melt amount producer AD: " + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
