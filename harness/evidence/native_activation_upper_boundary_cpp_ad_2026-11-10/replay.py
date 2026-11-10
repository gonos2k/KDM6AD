#!/usr/bin/env python3
"""Replay the sw=0.48 activation cap boundary for the full-call TH/QV map."""

from __future__ import annotations

import csv
import difflib
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
REPO = HERE.parents[2]
PARENT = EVIDENCE / "native_d1_thermal_input_cpp_ad_2026-11-10"
PRE2 = EVIDENCE / "native_c2c_pre2_upstream_2026-11-07"
NATIVE_PRODUCER = EVIDENCE / "native_d1_melt_producer_ad_2026-11-04"
RUNNER = PARENT / "cpp"
RUNNER_CMAKE = EVIDENCE / "native_nc_process_graph_cpp_ad_2026-11-08/cpp/CMakeLists.txt"
MELT_SOURCE = EVIDENCE / "native_d1_melt_state_ad_2026-11-04/executed_cpp/melt_freeze.cpp"
MELT_SOURCE_PACKET = EVIDENCE / "native_d1_melt_amount_producer_cpp_ad_2026-11-09/executed_cpp/melt_freeze.cpp"
NATIVE_PRODUCER_REPLAY = NATIVE_PRODUCER / "replay.py"
SLOPE_SOURCE = REPO / "libtorch/src/slope.cpp"
CONSTANTS_SOURCE = REPO / "libtorch/include/kdm6/constants.h"
PROGB_HEADER = REPO / "libtorch/include/kdm6/progb.h"
EXECUTED_PROGB_SOURCE = PRE2 / "executed_cpp/progb.cpp"
MANIFEST_SHA = "65e8497cc7e1b79f6d50cdf5e56675b0008e354059cc2d2217f3fe673c15619e"
PARENT_REPLAY_SHA = "933d2109c46c1143b60e729c3379b41e7fae45836786cff55144dae97a6e234f"
ACTIVATION_BOUNDARY_SCHEMA = "kdm6.native_d1_activation_boundary.v1"
ACTIVATION_BOUNDARY_PATH = HERE / "raw/activation_boundary.json"
ACTIVATION_AXES = ("th16", "qv16")
ACTIVATION_BRACKETS = ("sw_percent_0p48", "activated_fraction_ge_1_observed_value")
ACTIVATION_OUTPUTS = (
    "sw_percent", "activated_fraction", "ncact_raw", "ncact",
    "nc_after_activation", "nccn_after_activation", "nccn_final",
    "final_nc16", "final_nccn16",
)
ACTIVATION_ENDPOINT_OUTPUTS = ACTIVATION_OUTPUTS
ACTIVATION_INTERIOR_FD_STEPS = {
    "th16": {
        "fraction_eq_one": (1.0e-4, 1.0e-5, 1.0e-6),
        "fraction_below_one": (1.0e-4, 1.0e-5, 1.0e-6, 1.0e-7),
    },
    "qv16": {
        "fraction_eq_one": (1.0e-3, 1.0e-4, 1.0e-5, 1.0e-6, 1.0e-7),
        "fraction_below_one": (1.0e-5, 1.0e-6, 1.0e-7, 1.0e-8),
    },
}
ACTIVATION_D1_BRANCH_FIELDS = (
    "warm", "snow_active", "graupel_active", "graupel_mask",
    "psmlt_cap_is_raw_candidate", "pgmlt_cap_is_raw_candidate",
)
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
THERMAL_RUNTIME_SOURCE = EVIDENCE / "native_nc_rate_producer_2026-11-07/executed_cpp/runtime.cpp"
THERMAL_RUNTIME_SOURCE_SHA = "d0bf029414d0c04c1c06a8b754e486827449b2574febb0ed49e1d0e3c8baab10"
ACTIVATION_EXECUTED_COORDINATOR = EVIDENCE / "native_d1_coeres_upstream_cpp_ad_2026-11-10/executed_cpp/coordinator.cpp"
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
PRECG2_STAGE = "d1_entry_precg2_inputs"
PRECG2_FIELDS = ("avtg", "bvtg", "bvtg2", "g5pbgo2", "precg2", "mug", "active", "midpoint_trace")
PRECG2_SIGNALS = tuple(PRECG2_STAGE + "." + name for name in ("avtg", "bvtg", "bvtg2", "g5pbgo2", "precg2"))
COERES_STAGE = "d1_entry_coeres_inputs"
COERES_FIELDS = (
    "qg", "rslope_g", "bvtg", "rslopegbmax", "graupel_mask",
    "rslope2_g", "rslopeb_g", "rslopemu_g", "mug", "qcrmin",
)
COERES_SIGNALS = tuple(COERES_STAGE + "." + name for name in ("rslope2_g", "rslopeb_g")) + (
    MELT_STAGE + ".coeres_g",
)
COERES_RB_ULP_LIMIT = 16
COERES_VALUE_ULP_LIMIT = 4
THERMAL_VJP_SCHEMA = "kdm6.native_d1_thermal_stage_vjp.v1"
THERMAL_DIRECTIONS_SCHEMA = "kdm6.native_d1_thermal_directions.v1"
THERMAL_DIRECTION_NAMES = ("th16_abs", "qv16_rel", "th16_abs_qv16_rel_joint")
THERMAL_K_INDEX0 = 15
THERMAL_INPUT_STATE_INDEX = {"th16": 15, "qv16": 54}
THERMAL_STATE_ORDER = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
THERMAL_STAGE_VJP_FIELDS = (
    "d1_melt_producer.t1", "d1_melt_producer.work2",
    "d1_melt_producer.psmlt_capped_g", "d1_melt_producer.pgmlt_raw",
)
THERMAL_OUTPUT_FIELDS = {
    "d1_melt_producer.t1": "t1",
    "d1_melt_producer.work2": "work2",
    "d1_melt_producer.psmlt_capped_g": "psmlt_capped_g",
    "d1_melt_producer.pgmlt_raw": "pgmlt_raw",
}
THERMAL_D1_FD_FIELDS = (
    MELT_STAGE + ".t1", MELT_STAGE + ".work2",
    MELT_STAGE + ".psmlt_capped_g", MELT_STAGE + ".psmlt",
    MELT_STAGE + ".pgmlt_raw", MELT_STAGE + ".pgmlt",
)
THERMAL_STEPS = {
    "th16_abs": ("0.01", "0.001", "0.0001"),
    "qv16_rel": ("0.001", "0.0001"),
    "th16_abs_qv16_rel_joint": ("0.001", "0.0001"),
}
THERMAL_SMOOTH_STEPS = {
    "th16_abs": ("0.001", "0.0001"),
    "qv16_rel": ("0.0001",),
    "th16_abs_qv16_rel_joint": ("0.0001",),
}
THERMAL_CPMD = 1004.5
THERMAL_CPMV = 1846.4
THERMAL_QMIN = 1.0e-15
THERMAL_DEN0 = 1.28
THERMAL_XLF_D1 = 3.50e5
THERMAL_T0C = 273.15
THERMAL_FD_REL_TOL = 5e-6
THERMAL_NATIVE_VJP_PACKET = EVIDENCE / "native_nc16_vjp_branch_window_2026-11-06"
THERMAL_NATIVE_TH_PACKET = EVIDENCE / "native_nc16_fd_expanded_2026-11-06"
THERMAL_NATIVE_QV_PACKET = EVIDENCE / "native_nc_nccn_applied_2026-11-07"
THERMAL_NATIVE_MANIFEST_SHA = {
    "native_nc16_vjp_branch_window_2026-11-06": "8c20d6bac0371e3d95b6a4c55cedee36d9958c49b97e5e5382d095a843712432",
    "native_nc16_fd_expanded_2026-11-06": "2696fb5e1f094a65ad769d464c2cb514fc1af9dfcdb4acaa8914fbdab8cb7c4e",
    "native_nc_nccn_applied_2026-11-07": "a1aec8dfc95317df2294b0982091d2b915532de49203127939357a18ce96ace5",
}
THERMAL_NATIVE_ANCHORS_SHA = "3aeba105f09c33c3119df2af8e2381358ca0db1f4b087b92b41a59c1d3a2be89"
THERMAL_FINAL_FD_SHA = "b55229be8b655db0e1741573dc25bf0bf7cd9ebcc170af06ef004c04e6667e0d"
PROGB_DENSITY_TABLE = (100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0)
PROGB_AVTG_TABLE = (54.9153, 74.2262, 88.8313, 101.0411, 111.7359, 121.3625, 130.1841, 138.3714, 146.0422)
PROGB_BVTG_TABLE = (0.5446, 0.5375, 0.5339, 0.5316, 0.5299, 0.5286, 0.5275, 0.5266, 0.5258)
EPS = 1.0e-15
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


def reject_json_constant(value: str) -> None:
    raise ValueError("nonstandard JSON numeric constant: " + value)


def require_finite_tree(value: object, why: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require_finite_tree(item, why + "/" + str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            require_finite_tree(item, why + "/" + str(index))
    elif isinstance(value, bool) or value is None or isinstance(value, str):
        return
    elif isinstance(value, (int, float)):
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError):
            finite = False
        need(finite, why + " contains a nonfinite number")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def ordered_f64_bits(value: float) -> int:
    bits = int(word(value), 16)
    sign = 1 << 63
    return (~bits & ((1 << 64) - 1)) if bits & sign else (bits | sign)


def module_ulp_distance(a: float, b: float) -> int:
    return abs(ordered_f64_bits(a) - ordered_f64_bits(b))


def finite_final_word(raw: object, why: str) -> float:
    need(isinstance(raw, str) and 1 <= len(raw) <= 16
         and all(char in "0123456789abcdefABCDEF" for char in raw),
         why + " raw f64 word syntax")
    try:
        bits = int(raw, 16)
    except ValueError as exc:
        raise ValueError(why + " raw f64 word syntax") from exc
    need(0 <= bits < 1 << 64, why + " raw f64 word range")
    value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    need(math.isfinite(value), why + " finite final-state f64")
    return value


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


def source_order_bvtg2(bvtg: float, mug: float) -> float:
    return (2.5 + bvtg * 0.5) + mug


def source_order_g5pbgo2(bvtg2: float) -> float:
    return math.exp(math.lgamma(max(bvtg2, EPS)))


def source_order_precg2(avtg: float, g5pbgo2: float) -> float:
    return ((4.0 * 0.31) * math.pow(max(avtg, EPS), 0.5)) * g5pbgo2


def source_order_rslopeb_g(rslope_g: float, bvtg: float) -> float:
    return math.pow(max(rslope_g, EPS), bvtg)


def source_order_coeres_g(rslope2_g: float, rslope_g: float, rslopeb_g: float,
                          rslopemu_g: float, qcrmin: float) -> float:
    return (rslope2_g * math.sqrt(max(rslope_g * rslopeb_g, qcrmin))) * rslopemu_g


def source_order_progb_interpolation(rhox: float, active: bool) -> tuple[float, float, int]:
    if not active:
        return 0.0, 0.0, -1
    right = next((index for index, point in enumerate(PROGB_DENSITY_TABLE) if point > rhox), 8)
    right = min(max(right, 1), 8)
    left = right - 1
    if rhox == PROGB_DENSITY_TABLE[8]:
        return PROGB_AVTG_TABLE[8], PROGB_BVTG_TABLE[8], 7
    width = PROGB_DENSITY_TABLE[right] - PROGB_DENSITY_TABLE[left]
    tmp2 = 1.0 / width
    d1 = rhox - PROGB_DENSITY_TABLE[left]
    avtg_product = d1 * (PROGB_AVTG_TABLE[right] - PROGB_AVTG_TABLE[left])
    avtg_product = avtg_product * tmp2
    bvtg_product = d1 * (PROGB_BVTG_TABLE[right] - PROGB_BVTG_TABLE[left])
    bvtg_product = bvtg_product * tmp2
    return (PROGB_AVTG_TABLE[left] + avtg_product,
            PROGB_BVTG_TABLE[left] + bvtg_product, left)


def xka_scalar(t: float, den: float) -> float:
    safe_t = max(t, 1.0)
    viscos = (1.496e-6 * (safe_t * math.sqrt(safe_t))) / (safe_t + 120.0) / den
    return (1.414e3 * viscos) * den


def source_order_cpm(qv: float) -> float:
    qv_safe = max(qv, THERMAL_QMIN)
    cpd_term = THERMAL_CPMD * (1.0 - qv_safe)
    qv_term = qv_safe * THERMAL_CPMV
    return cpd_term + qv_term


def source_order_work2(t: float, pres: float, den: float) -> float:
    t_safe = max(t, 1.0)
    diffus = 8.794e-5 * math.exp(math.log(t_safe) * 1.81) / pres
    viscos = (1.496e-6 * (t_safe * math.sqrt(t_safe))
              / (t_safe + 120.0) / den)
    den_safe = max(den, THERMAL_QMIN)
    return (math.exp(math.log(viscos / diffus) * 0.3333333)
            / math.sqrt(viscos)
            * math.sqrt(math.sqrt(THERMAL_DEN0 / den_safe)))


def source_order_work2_jvp(t: float, work2: float, dt: float) -> float:
    t_safe = max(t, 1.0)
    need(t_safe == t, "selected work2 temperature above its 1 K floor")
    dlog_viscos_dt = 1.5 / t - 1.0 / (t + 120.0)
    dlog_diffus_dt = 1.81 / t
    dlog_work2_dt = 0.3333333 * (dlog_viscos_dt - dlog_diffus_dt) - 0.5 * dlog_viscos_dt
    return work2 * dlog_work2_dt * dt


def thermal_cpm_work2_values(stages: dict, th: float, qv: float, pii: float,
                             why: str) -> dict[str, float]:
    temperature = th * pii
    exact(temperature, stages[MELT_STAGE + ".t"], why + " TH·PII physical-temperature mapping")
    exact(qv, stages[NEW_STAGE + ".qv_before"], why + " packed QV handoff to D1")
    cpm_expected = source_order_cpm(qv)
    cpm = stages[MELT_STAGE + ".cpm"]
    exact(cpm, cpm_expected, why + " source-order applied cpm")
    cpm_safe = stages[NEW_STAGE + ".cpm_safe"]
    exact(cpm_safe, max(cpm, QCRMIN), why + " cpm safe-floor value")
    need(cpm > QCRMIN, why + " selected cpm clamp inactive")
    work2_expected = source_order_work2(
        temperature, stages[MELT_STAGE + ".p"], stages[MELT_STAGE + ".den"])
    work2 = stages[MELT_STAGE + ".work2"]
    work2_ulp = ulp_distance(work2_expected, work2)
    need(work2_ulp <= 16, why + " independent work2 formula within portable ULP bound")
    return {
        "temperature": temperature,
        "expected_cpm": cpm_expected,
        "expected_work2": work2_expected,
        "work2_ulp_distance": work2_ulp,
    }


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


def native_manifest_asset(packet: Path, expected_manifest_sha: str, relative: str) -> bytes:
    raw_manifest = (packet / "manifest.json").read_bytes()
    need(sha(raw_manifest) == expected_manifest_sha,
         "pinned native parent manifest: " + packet.name)
    manifest_data = json.loads(raw_manifest)
    files = manifest_data["files"]
    need(relative in files, "native parent asset listed in manifest: " + relative)
    raw = (packet / relative).read_bytes()
    need(sha(raw) == files[relative], "native parent asset SHA: " + relative)
    return raw


def native_npz(packet: Path, expected_manifest_sha: str, relative: str) -> dict[str, np.ndarray]:
    raw = native_manifest_asset(packet, expected_manifest_sha, relative)
    with np.load(io.BytesIO(raw), allow_pickle=False) as arrays:
        return {name: np.array(arrays[name], copy=True) for name in arrays.files}


def native_capture_rows(packet: Path, expected_manifest_sha: str, relative: str) -> dict[tuple[str, str, int], dict[str, str]]:
    raw = native_manifest_asset(packet, expected_manifest_sha, relative)
    need(raw.startswith(b"one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex\n"),
         "native capture CSV header: " + relative)
    need(raw.endswith(b"status=complete\n"), "native capture complete: " + relative)
    rows = csv.DictReader(line for line in io.StringIO(gzip.decompress(raw).decode())
                          if not line.startswith("#"))
    selected: dict[tuple[str, str, int], dict[str, str]] = {}
    for row in rows:
        if (row["runtime_call"] == "1" and row["one_step_call"] == "1"
                and row["substep"] == "0" and row["b_zero"] == "0"
                and row["k_zero"] == "23" and row["B"] == "1" and row["K"] == "39"
                and row["stage"] == MELT_STAGE):
            key = (row["stage"], row["field"], int(row["k_zero"]))
            need(key not in selected, "duplicate native selected D1 capture row: " + relative + "/" + str(key))
            selected[key] = row
    for field in MELT_FIELDS:
        need((MELT_STAGE, field, 23) in selected,
             "missing native selected D1 capture field: " + relative + "/" + field)
    return selected


def f64_vector_words(values: list[float], raw_words: list[str], why: str) -> None:
    need(len(values) == len(raw_words), why + " raw word count")
    for index, (value, raw) in enumerate(zip(values, raw_words)):
        need(word(value) == str(raw).zfill(16), why + " raw f64 word at " + str(index))


def stage_bool(value: object, why: str) -> bool:
    need(value in (False, True, 0, 1), why + " bool encoding")
    return bool(value)


def thermal_stage_source_values(stages: dict[str, float], th: float, qv: float,
                                pii: float, why: str) -> dict[str, float | int]:
    thermo = thermal_cpm_work2_values(stages, th, qv, pii, why)
    exact(stages[NEW_STAGE + ".qv_before"], qv, why + " QV packed-input handoff")
    exact(stages[NEW_STAGE + ".pre_cpm"], thermo["expected_cpm"],
          why + " preamble cpm value")
    melt_expected = source_order_melt_producer(stages)
    for field in MELT_SOURCE_CHECK_FIELDS:
        expected = melt_expected[field]
        actual = stages[MELT_STAGE + "." + field]
        if field in MELT_BOOL_FIELDS:
            need(stage_bool(actual, why + "/" + field) == bool(expected),
                 why + " D1 source-order mask: " + field)
        else:
            exact(actual, expected, why + " D1 source-order value: " + field)
    return thermo


def verify_thermal_branch(branch: dict, stages: dict[str, float], th: float,
                          qv: float, pii: float, baseline_upper: bool,
                          why: str) -> dict[str, bool]:
    need(set(branch) == {"input", "d1_branch", "activation"}, why + " branch summary inventory")
    input_info = branch["input"]
    for key, expected in (("th16", th), ("qv16", qv), ("pii16", pii),
                          ("physical_t16", th * pii)):
        exact(float(input_info[key]), expected, why + " branch input " + key)
    d1 = branch["d1_branch"]
    activation = branch["activation"]
    need(set(d1) == {
        "warm", "snow_active", "graupel_active", "graupel_mask",
        "psmlt_cap_is_raw_candidate", "pgmlt_cap_is_raw_candidate", "t", "t1",
        "temperature_margin_k", "qs", "qg", "psmlt_capped", "pgmlt_capped",
        "snow_mass_reserve", "graupel_mass_reserve", "cpm_used", "n0sfac", "work2",
        "pgmlt_raw",
    }, why + " D1 branch summary fields")
    stage_fields = ("warm", "snow_active", "graupel_active")
    for field in stage_fields:
        need(stage_bool(d1[field], why + "/" + field)
             == stage_bool(stages[MELT_STAGE + "." + field], why + "/stage/" + field),
             why + " D1 branch summary matches stage: " + field)
    need(stage_bool(d1["graupel_mask"], why + "/graupel_mask")
         == stage_bool(stages[COERES_STAGE + ".graupel_mask"], why + "/stage/graupel_mask"),
         why + " D1 slope mask branch summary matches stage")
    for key, stage_key in (("t", "t"), ("t1", "t1"), ("qs", "qs"), ("qg", "qg"),
                           ("psmlt_capped", "psmlt_capped"),
                           ("pgmlt_capped", "pgmlt_capped"), ("cpm_used", "cpm"),
                           ("n0sfac", "n0sfac"), ("work2", "work2"), ("pgmlt_raw", "pgmlt_raw")):
        exact(float(d1[key]), stages[MELT_STAGE + "." + stage_key],
              why + " D1 branch value matches stage: " + key)
    exact(float(d1["temperature_margin_k"]),
          stages[MELT_STAGE + ".t"] - stages[MELT_STAGE + ".t0c"],
          why + " D1 temperature branch margin")
    exact(float(d1["snow_mass_reserve"]),
          stages[MELT_STAGE + ".qs"] + stages[MELT_STAGE + ".psmlt_capped"],
          why + " D1 snow-mass reserve")
    exact(float(d1["graupel_mass_reserve"]),
          stages[MELT_STAGE + ".qg"] + stages[MELT_STAGE + ".pgmlt_capped"],
          why + " D1 graupel-mass reserve")
    need(stage_bool(d1["psmlt_cap_is_raw_candidate"], why + "/psmlt cap")
         == (word(stages[MELT_STAGE + ".psmlt_dt"])
             == word(stages[MELT_STAGE + ".psmlt_capped"])),
         why + " D1 snow cap branch summary")
    need(stage_bool(d1["pgmlt_cap_is_raw_candidate"], why + "/pgmlt cap")
         == (word(stages[MELT_STAGE + ".pgmlt_dt"])
             == word(stages[MELT_STAGE + ".pgmlt_capped"])),
         why + " D1 graupel cap branch summary")
    need(set(activation) == {
        "sw_percent", "activated_fraction", "activation_fraction_at_upper_bound",
        "activation_upper_bound_changed_vs_baseline", "ncact_raw", "ncact",
        "nccn_floor_active", "nccn_cap_active",
    }, why + " activation branch summary fields")
    for key, stage_key in (("sw_percent", "sw_percent"),
                           ("activated_fraction", "activated_fraction"),
                           ("ncact_raw", "ncact_raw"), ("ncact", "ncact")):
        exact(float(activation[key]), stages["fd_satadj_inner." + stage_key],
              why + " activation value matches stage: " + key)
    for key, stage_key in (("nccn_floor_active", "nccn_floor_active"),
                           ("nccn_cap_active", "nccn_cap_active")):
        need(stage_bool(activation[key], why + "/" + key)
             == stage_bool(stages["fd_satadj_inner." + stage_key], why + "/stage/" + key),
             why + " activation mask matches stage: " + key)
    is_upper = stage_bool(activation["activation_fraction_at_upper_bound"],
                          why + "/activation upper")
    need(is_upper == (activation["activated_fraction"] >= 1.0),
         why + " activation upper-bound decision")
    need(stage_bool(activation["activation_upper_bound_changed_vs_baseline"],
                    why + "/activation changed") == (is_upper != baseline_upper),
         why + " activation upper-change decision")
    return {
        "warm": stage_bool(d1["warm"], why + "/warm"),
        "snow_active": stage_bool(d1["snow_active"], why + "/snow"),
        "graupel_active": stage_bool(d1["graupel_active"], why + "/graupel"),
        "graupel_mask": stage_bool(d1["graupel_mask"], why + "/graupel_mask"),
        "psmlt_cap_is_raw_candidate": stage_bool(d1["psmlt_cap_is_raw_candidate"], why + "/psmlt cap"),
        "pgmlt_cap_is_raw_candidate": stage_bool(d1["pgmlt_cap_is_raw_candidate"], why + "/pgmlt cap"),
        "activation_upper_bound": is_upper,
        "activation_upper_changed": stage_bool(
            activation["activation_upper_bound_changed_vs_baseline"], why + "/activation changed"),
        "nccn_floor_active": stage_bool(activation["nccn_floor_active"], why + "/floor"),
        "nccn_cap_active": stage_bool(activation["nccn_cap_active"], why + "/cap"),
    }


def fixed_manifest() -> None:
    need(MANIFEST_SHA != "PENDING", "packet manifest SHA has not been pinned")
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "packet manifest SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_activation_upper_boundary_cpp_ad_packet.v1",
         "activation boundary manifest schema")
    actual = {str(p.relative_to(HERE)) for folder in ("raw", "cpp")
              for p in (HERE / folder).rglob("*") if p.is_file()}
    need(set(data["files"]) == actual, "packet file inventory")
    for name, digest in data["files"].items():
        need(sha((HERE / name).read_bytes()) == digest, "asset SHA: " + name)


@lru_cache(maxsize=1)
def parent_replay() -> dict:
    source = PARENT / "replay.py"
    need(sha(source.read_bytes()) == PARENT_REPLAY_SHA, "pinned #568 precg2 replay source")
    spec = importlib.util.spec_from_file_location("d1_melt_amount_parent", source)
    need(spec is not None and spec.loader is not None, "parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.replay()
    need(summary["selected_cases"] == 25 and summary["new_melt_producer_stage_fields"] == 62
         and summary["melt_source_order_cases"] == 25
         and summary["melt_source_order_fields_per_case"] == 25
         and summary["numeric_stage_tangents_per_direction"] == 322
         and summary["new_entry_coeres_stage_fields"] == 10
         and summary["native_d1_coeres_anchor_words_raw_equal"] == 24
         and summary["native_d1_applied_words_raw_equal"] == 78
         and summary["native_melt_producer_words_raw_equal"] == 186,
         "verified #571 coeres parent")
    summary["cap_windows"] = module.parent_replay()["cap_windows"]
    return summary


def provenance(parent_result: bytes, boundary_result: bytes) -> None:
    build = json.loads((HERE / "raw/build_receipt.json").read_text())
    run = json.loads((HERE / "raw/run_receipt.json").read_text())
    need(build["schema"] == "kdm6.native_activation_upper_boundary_cpp_ad_build.v1",
         "activation boundary build schema")
    need(run["schema"] == "kdm6.native_activation_upper_boundary_cpp_ad_run.v1"
         and run["returncode"] == 0, "run schema/status")
    parent_manifest = (PARENT / "manifest.json").read_bytes()
    parent_build = (PARENT / "raw/build_receipt.json").read_bytes()
    need(build["archive_reused_from_parent"] is True,
         "boundary runner reused parent physics archive")
    for key, path in {
        "runner_source": HERE / "cpp/main.cpp",
        "runner_parent_source": RUNNER / "main.cpp",
        "runner_cmake": RUNNER_CMAKE,
        "parent_manifest": PARENT / "manifest.json",
        "parent_build_receipt": PARENT / "raw/build_receipt.json",
        "parent_result": PARENT / "raw/cpp_result.json",
        "input_binary": EVIDENCE / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin",
        "boundary_result": HERE / "raw/activation_boundary.json",
        "executed_coordinator": ACTIVATION_EXECUTED_COORDINATOR,
        "executed_runtime": THERMAL_RUNTIME_SOURCE,
        "melt_freeze_source": MELT_SOURCE_PACKET,
    }.items():
        need(sha(path.read_bytes()) == build["sha256"][key], "source/input SHA: " + key)
    need(sha(parent_manifest) == build["sha256"]["parent_manifest"], "parent manifest SHA")
    need(sha(parent_build) == build["sha256"]["parent_build_receipt"], "parent build receipt SHA")
    need(sha(parent_result) == build["sha256"]["parent_result"]
         == run["default_output_sha256"], "parent default output SHA")
    need(sha(boundary_result) == build["sha256"]["boundary_result"]
         == run["boundary_output_sha256"], "boundary output SHA")
    need(run["boundary_full_call_forwards"] == 190, "boundary full-call forward count")
    need(run["input_sha256"] == build["sha256"]["input_binary"], "run input SHA")
    need(run["archive_sha256"] == build["sha256"]["library_archive"], "run archive SHA")
    need(run["executable_sha256"] == build["sha256"]["runner_executable"], "run executable SHA")
    need(run["environment"] == {
        "KDM6AD_QNC_LIVE_GUARD": "1", "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
        "KDM6_QR_TRANSPORT": "actual_departure", "MKL_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1"}, "run environment")
    flags = gzip.decompress((HERE / "raw/runner_flags.make.gz").read_bytes()).decode()
    need(sha(flags.encode()) == build["sha256"]["runner_flags"], "runner flags SHA")
    need("-ffp-contract=off" in flags, "FP contract")
    need("-DNDEBUG" not in flags, "runner assertions")
    parent_build_data = json.loads(parent_build)
    parent_core_flags = gzip.decompress((PARENT / "raw/core_flags.make.gz").read_bytes()).decode()
    parent_bridge_flags = gzip.decompress((PARENT / "raw/bridge_flags.make.gz").read_bytes()).decode()
    need(sha(parent_core_flags.encode()) == parent_build_data["sha256"]["core_flags"]
         and "KDM6_NATIVE_SCALAR_CAPTURE" in parent_core_flags
         and "-ffp-contract=off" in parent_core_flags,
         "parent core scalar-capture/FP contract flags")
    need(sha(parent_bridge_flags.encode()) == parent_build_data["sha256"]["bridge_flags"]
         and "-ffp-contract=off" in parent_bridge_flags,
         "parent bridge FP contract flags")
    need(build["sha256"]["library_archive"] ==
         parent_build_data["sha256"]["library_archive"],
         "reused archive is the parent archive")
    for key in ("library_dso", "torch_library", "c10_library"):
        need(build["sha256"][key] == parent_build_data["sha256"][key],
             "reused parent build dependency SHA: " + key)
    need(run["archive_sha256"] == build["sha256"]["library_archive"]
         and run["executable_sha256"] == build["sha256"]["runner_executable"],
         "run executable/archive receipt binding")
    need(build["sha256"]["runner_cache"] == sha(gzip.decompress(
        (HERE / "raw/runner_cache.txt.gz").read_bytes())), "packaged runner cache SHA")
    cache = gzip.decompress((HERE / "raw/runner_cache.txt.gz").read_bytes())
    need(sha(cache) == build["sha256"]["runner_cache"], "runner cache SHA")
    runner_source = (HERE / "cpp/main.cpp").read_bytes()
    runner_parent = (RUNNER / "main.cpp").read_bytes()
    runner_patch = gzip.decompress((HERE / "cpp/runner.patch.gz").read_bytes())
    reconstructed_patch = "".join(difflib.unified_diff(
        runner_parent.decode().splitlines(keepends=True),
        runner_source.decode().splitlines(keepends=True),
        fromfile="parent/runner/main.cpp", tofile="executed/runner/main.cpp"))
    need(runner_patch.decode("utf-8") == reconstructed_patch,
         "boundary runner patch restores exact parent runner")
    need(build["sha256"]["runner_source"] == sha(runner_source)
         and build["sha256"]["runner_parent_source"] == sha(runner_parent),
         "boundary runner source identity")
    need(build["sha256"]["executed_runtime"] == THERMAL_RUNTIME_SOURCE_SHA
         and build["sha256"]["melt_freeze_source"] == sha(MELT_SOURCE_PACKET.read_bytes()),
         "boundary build physics source pins")
    need(run["boundary_command"][:-1] == run["default_command"]
         and run["boundary_command"][-1] == "--activation-boundary"
         and Path(run["default_command"][-1]).name == "input.bin",
         "default and boundary runner command modes")
    need(build["paths"]["boundary_result"].endswith("/raw/activation_boundary.json"),
         "boundary result receipt path")


def activation_observation(row: dict, axis: str, coordinate: float, base_th: float,
                          base_qv: float, pii: float, predicate: str,
                          baseline_d1: dict, why: str) -> dict[str, float | bool]:
    need(str(row["input_word"]).zfill(16) == word(coordinate), why + " input f64 word")
    exact(float(row["input"]), coordinate, why + " input coordinate")
    th = coordinate if axis == "th16" else base_th
    qv = coordinate if axis == "qv16" else base_qv
    exact(float(row["th16"]), th, why + " TH input")
    exact(float(row["qv16"]), qv, why + " QV input")
    exact(float(row["physical_t16"]), th * pii, why + " physical T")
    exact(float(row["qv_input"]), qv, why + " live activation QV input")
    qs1 = float(row["qs1"])
    qs1_safe = max(qs1, QCRMIN)
    exact(float(row["qs1_safe"]), qs1_safe, why + " source qs1 floor")
    sw = (qv / qs1_safe - 1.0) * 100.0
    exact(float(row["sw_percent"]), sw, why + " source-order sw_percent")
    need(str(row["sw_percent_word"]).zfill(16) == word(sw), why + " sw raw word")
    sw_positive = sw > 0.0
    need(stage_bool(row["sw_positive"], why + " sw_positive") == sw_positive,
         why + " sw-positive gate")
    ratio = max(sw / 0.48, 0.0)
    expected_fraction = min(1.0, math.pow(max(ratio, 1.0e-15), 0.6))
    fraction = float(row["activated_fraction"])
    need(str(row["activated_fraction_word"]).zfill(16) == word(fraction),
         why + " activation fraction raw word")
    need(ulp_distance(expected_fraction, fraction) <= 16,
         why + " independent activation fraction within portable ULP")
    predicate_value = (sw >= 0.48 if predicate == "sw_percent_gte_0p48"
                       else fraction >= 1.0)
    need(stage_bool(row["predicate"], why + " threshold predicate") == predicate_value,
         why + " recorded predicate follows output value")

    nc = float(row["nc_input"])
    nccn = float(row["nccn_input"])
    dt = float(row["dtcld"])
    rate_cap = max(nccn, 0.0) / dt
    activation_product = (nccn + nc) * fraction
    raw_rate = max(activation_product - nc, 0.0) / dt
    selected_rate = min(raw_rate, rate_cap)
    if not sw_positive:
        selected_rate = 0.0
    exact(float(row["ncact_rate_cap"]), rate_cap, why + " NCCN rate cap")
    exact(float(row["ncact_raw_minus_cap"]), raw_rate - rate_cap,
          why + " raw-rate/cap margin")
    exact(float(row["ncact_raw"]), raw_rate, why + " source-order ncact_raw")
    exact(float(row["ncact"]), selected_rate, why + " selected ncact rate")
    need(stage_bool(row["ncact_cap_active"], why + " ncact cap flag")
         == (raw_rate > rate_cap), why + " ncact rate cap decision")
    need(stage_bool(row["ncact_cap_tie"], why + " ncact tie flag")
         == (raw_rate == rate_cap), why + " ncact cap tie decision")
    exact(float(row["nc_after_activation"]), max(nc + selected_rate * dt, 0.0),
          why + " NC activation store")
    exact(float(row["nccn_after_activation"]), max(nccn - selected_rate * dt, 0.0),
          why + " NCCN activation store")
    d1 = row["d1_branch"]
    for key in ("warm", "snow_active", "graupel_active", "psmlt_raw_candidate",
                "pgmlt_raw_candidate"):
        need(stage_bool(d1[key], why + " D1 " + key) == bool(baseline_d1[key]),
             why + " nearby D1 branch remains fixed: " + key)
    need(math.isfinite(float(row["final_nc16"])) and float(row["final_nc16"]) >= 0.0,
         why + " finite nonnegative NC16")
    need(math.isfinite(float(row["final_nccn16"])) and float(row["final_nccn16"]) >= 0.0,
         why + " finite nonnegative NCCN16")
    return {"sw_percent": sw, "sw_ratio": ratio, "activated_fraction": fraction,
            "ncact_rate_cap": rate_cap, "ncact_raw_minus_cap": raw_rate - rate_cap,
            "ncact": selected_rate, "nc_after_activation": float(row["nc_after_activation"]),
            "nccn_after_activation": float(row["nccn_after_activation"])}


def _activation_observation(row: dict, axis: str, coordinate: float, base_th: float,
                            base_qv: float, pii: float, predicate: str, why: str,
                            baseline_d1: dict[str, object]) -> dict[str, float | bool]:
    need(str(row["input_word"]).zfill(16) == word(coordinate), why + " input raw word")
    exact(float(row["input"]), coordinate, why + " coordinate value")
    th = coordinate if axis == "th16" else base_th
    qv = coordinate if axis == "qv16" else base_qv
    exact(float(row["th16"]), th, why + " TH input")
    exact(float(row["qv16"]), qv, why + " QV input")
    exact(float(row["physical_t16"]), th * pii, why + " physical T input")
    qv_input = float(row["qv_input"])
    need(math.isfinite(qv_input) and qv_input > 0.0,
         why + " finite positive activation-stage QV")
    need(str(row.get("qv_input_word", word(qv_input))).zfill(16) == word(qv_input),
         why + " activation-stage QV raw word")
    qs1 = float(row["qs1"])
    qs1_safe = max(qs1, QCRMIN)
    need(math.isfinite(qs1) and math.isfinite(qs1_safe) and qs1_safe > 0.0,
         why + " finite positive saturation mixing ratio")
    exact(float(row["qs1_safe"]), qs1_safe, why + " saturation mixing ratio safe value")
    expected_sw = (qv_input / qs1_safe - 1.0) * 100.0
    need(math.isfinite(expected_sw), why + " finite source-order supersaturation")
    exact(float(row["sw_percent"]), expected_sw, why + " source-order sw_percent")
    need(str(row["sw_percent_word"]).zfill(16) == word(expected_sw), why + " sw_percent raw word")
    sw_positive = expected_sw > 0.0
    need(stage_bool(row["sw_positive"], why + " sw_positive") == sw_positive,
         why + " sw-positive gate")
    sw_ratio = max(expected_sw / 0.48, 0.0)
    expected_fraction = min(1.0, math.pow(max(sw_ratio, THERMAL_QMIN), 0.6))
    need(math.isfinite(sw_ratio) and math.isfinite(expected_fraction),
         why + " finite activation fraction calculation")
    fraction = float(row["activated_fraction"])
    fraction_ulp = abs(int(str(row["activated_fraction_word"]).zfill(16), 16)
                       - int(word(fraction), 16))
    need(fraction_ulp == 0, why + " activated_fraction raw word")
    need(fraction_ulp == ulp_distance(fraction, float(row["activated_fraction"])),
         why + " activated_fraction self word")
    # Python/libm pow is independent but last-ULP portable; equality to 1 is an
    # observed output state and does not identify which operand torch::minimum chose.
    fraction_distance = ulp_distance(expected_fraction, fraction)
    need(fraction_distance <= 16, why + " activated_fraction source formula within portable ULP")
    need(stage_bool(row["predicate"], why + " threshold predicate")
         == (expected_sw >= 0.48 if predicate == "sw_percent_gte_0p48" else fraction >= 1.0),
         why + " recorded threshold predicate")

    nc = float(row["nc_input"])
    nccn = float(row["nccn_input"])
    dt = float(row["dtcld"])
    need(math.isfinite(nc) and math.isfinite(nccn) and math.isfinite(dt) and dt > 0.0,
         why + " finite activation inputs and positive dt")
    rate_cap = max(nccn, 0.0) / dt
    # ops::fma_acc(-nc, nccn+nc, fraction) is strict two-rounding:
    # first the product (nccn+nc)*fraction, then addition of -nc.
    activation_product = (nccn + nc) * fraction
    expected_raw = max(activation_product - nc, 0.0) / dt
    expected_rate = min(expected_raw, rate_cap)
    if not sw_positive:
        expected_rate = 0.0
    exact(float(row["ncact_rate_cap"]), rate_cap, why + " ncact rate cap")
    exact(float(row["ncact_raw_minus_cap"]), expected_raw - rate_cap,
          why + " ncact raw/cap margin")
    exact(float(row["ncact_raw"]), expected_raw, why + " source-order ncact raw")
    exact(float(row["ncact"]), expected_rate, why + " source-order ncact selected rate")
    need(stage_bool(row["ncact_cap_active"], why + " ncact cap flag")
         == (expected_raw > rate_cap), why + " ncact cap decision")
    need(stage_bool(row["ncact_cap_tie"], why + " ncact tie flag")
         == (expected_raw == rate_cap), why + " ncact tie decision")
    expected_nc = max(nc + expected_rate * dt, 0.0)
    expected_nccn = max(nccn - expected_rate * dt, 0.0)
    need(all(math.isfinite(value) for value in (
        rate_cap, activation_product, expected_raw, expected_rate, expected_nc, expected_nccn)),
        why + " finite activation source arithmetic")
    exact(float(row["nc_after_activation"]), expected_nc, why + " NC activation store")
    exact(float(row["nccn_after_activation"]), expected_nccn,
          why + " NCCN activation store")
    for key in ("nccn_floor_active", "nccn_cap_active"):
        need(type(row[key]) is bool, why + " bool field: " + key)
    exact(float(row["nccn_final"]), float(row["final_nccn16"]),
          why + " activation-stage/final NCCN handoff")
    need(float(row["nccn_final"]) >= 1.0e8,
         why + " final NCCN floor value")
    d1 = row["d1_branch"]
    for row_key, base_key in (
        ("warm", "warm"), ("snow_active", "snow_active"),
        ("graupel_active", "graupel_active"),
        ("psmlt_raw_candidate", "psmlt_cap_is_raw_candidate"),
        ("pgmlt_raw_candidate", "pgmlt_cap_is_raw_candidate"),
    ):
        need(stage_bool(d1[row_key], why + " D1 bool " + row_key)
             == bool(baseline_d1[base_key]),
             why + " D1 branch remains fixed: " + row_key)
    for key in ("t", "t1", "work2", "pgmlt_raw"):
        need(math.isfinite(float(d1[key])), why + " finite D1 diagnostic: " + key)
    return {
        "sw_percent": expected_sw,
        "sw_ratio": sw_ratio,
        "activated_fraction": fraction,
        "ncact_rate_cap": rate_cap,
        "ncact_raw_minus_cap": expected_raw - rate_cap,
        "ncact": expected_rate,
        "nc_after_activation": expected_nc,
        "nccn_after_activation": expected_nccn,
        "dtcld": dt,
        "nccn_final": float(row["nccn_final"]),
        "final_nc16": float(row["final_nc16"]),
        "final_nccn16": float(row["final_nccn16"]),
    }


def _verify_activation_bracket(axis: str, kind: str, bracket: dict, seed_low: float,
                               seed_high: float, base_th: float, base_qv: float, pii: float,
                               baseline_d1: dict[str, object], why: str) -> dict[str, object]:
    predicate = ("sw_percent_gte_0p48" if kind == "sw_percent_0p48"
                 else "activated_fraction_ge_1_observed_value")
    need(bracket["axis"] == axis and bracket["predicate"] == predicate,
         why + " bracket axis/predicate")
    lower = bracket["lower"]
    upper = bracket["upper"]
    lower_x, upper_x = float(lower["input"]), float(upper["input"])
    need(seed_low < seed_high and lower_x < upper_x, why + " ordered numeric bracket")
    lower_word = str(lower["input_word"]).zfill(16)
    upper_word = str(upper["input_word"]).zfill(16)
    lower_bits, upper_bits = int(lower_word, 16), int(upper_word, 16)
    need(lower_bits < upper_bits, why + " positive raw-word ordering")
    need(upper_bits - lower_bits == int(bracket["input_word_gap"]),
         why + " input word-gap arithmetic")
    need(int(bracket["input_word_gap"]) == 1 and stage_bool(bracket["adjacent_f64_words"], why)
         and stage_bool(bracket["adjacent_f64_words"], why) == (lower_bits + 1 == upper_bits),
         why + " adjacent representable f64 endpoints")
    low_observation = _activation_observation(
        lower, axis, lower_x, base_th, base_qv, pii, predicate, why + " lower", baseline_d1)
    high_observation = _activation_observation(
        upper, axis, upper_x, base_th, base_qv, pii, predicate, why + " upper", baseline_d1)
    need(stage_bool(lower["predicate"], why + " lower predicate")
         != stage_bool(upper["predicate"], why + " upper predicate"),
         why + " bracket predicate changes")
    expected_predicates = ((True, False) if axis == "th16" else (False, True))
    need((stage_bool(lower["predicate"], why + " lower orientation"),
          stage_bool(upper["predicate"], why + " upper orientation")) == expected_predicates,
         why + " expected axis predicate orientation")
    trace = bracket["trace"]
    need(isinstance(trace, list) and len(trace) >= 2
         and int(bracket["value_only_calls"]) == len(trace),
         why + " complete bisection trace call inventory")
    trace_low = trace[0]
    trace_high = trace[1]
    exact(float(trace_low["input"]), seed_low, why + " lower trace seed")
    exact(float(trace_high["input"]), seed_high, why + " upper trace seed")
    low_row, high_row = trace[0], trace[1]
    low_row_bits = int(str(low_row["input_word"]).zfill(16), 16)
    high_row_bits = int(str(high_row["input_word"]).zfill(16), 16)
    for trace_index, row in enumerate(trace):
        x = float(row["input"])
        bits = int(str(row["input_word"]).zfill(16), 16)
        exact(x, struct.unpack(">d", bits.to_bytes(8, "big"))[0],
              why + " trace input/word " + str(trace_index))
        observation = _activation_observation(row, axis, x, base_th, base_qv, pii,
                                              predicate, why + " trace " + str(trace_index),
                                              baseline_d1)
        branch_value = stage_bool(row["predicate"], why + " trace predicate")
        need(branch_value == (observation["sw_percent"] >= 0.48
                              if kind == "sw_percent_0p48"
                              else observation["activated_fraction"] >= 1.0),
             why + " trace predicate recomputation")
        if trace_index < 2:
            need(bits == (low_row_bits if trace_index == 0 else high_row_bits),
                 why + " initial trace endpoint ordering")
            continue
        midpoint = low_row_bits + (high_row_bits - low_row_bits) // 2
        need(bits == midpoint, why + " midpoint follows ordered-f64 bisection")
        if branch_value == stage_bool(low_row["predicate"], why + " low bracket predicate"):
            low_row, low_row_bits = row, bits
        else:
            high_row, high_row_bits = row, bits
    need(int(str(low_row["input_word"]).zfill(16), 16) == lower_bits
         and int(str(high_row["input_word"]).zfill(16), 16) == upper_bits,
         why + " bisection trace final bracket binding")
    output_gaps = bracket["output_gaps"]
    gap_fields = ("sw_percent", "activated_fraction", "ncact_raw", "ncact",
                  "nc_after_activation", "nccn_after_activation", "nccn_final",
                  "final_nc16", "final_nccn16")
    need(set(output_gaps) == set(gap_fields), why + " output-gap inventory")
    for name in gap_fields:
        lower_value, upper_value = float(lower[name]), float(upper[name])
        gap = output_gaps[name]
        exact(float(gap["lower"]), lower_value, why + " gap lower " + name)
        exact(float(gap["upper"]), upper_value, why + " gap upper " + name)
        delta = upper_value - lower_value
        need(math.isfinite(delta), why + " finite output delta " + name)
        exact(float(gap["delta"]), delta, why + " output delta " + name)
        distance = module_ulp_distance(lower_value, upper_value)
        need(int(gap["ulp_distance"]) == distance, why + " output ULP gap " + name)
        expected_resolution = ("unresolved_at_f64_output_resolution" if distance <= 1
                               else "resolved_above_one_output_ulp")
        need(gap["resolution_status"] == expected_resolution,
             why + " output resolution classification " + name)
    return {
        "lower": low_observation,
        "upper": high_observation,
        "input_word_gap": upper_bits - lower_bits,
        "value_only_calls": len(trace),
        "output_gaps": output_gaps,
    }


def _activation_branch_signature(row: dict) -> tuple[bool, ...]:
    return (
        bool(row["sw_positive"]), float(row["activated_fraction"]) >= 1.0,
        bool(row["ncact_cap_active"]), bool(row["ncact_cap_tie"]),
        bool(row["nccn_floor_active"]), bool(row["nccn_cap_active"]),
    )


def _activation_d1_signature(row: dict) -> tuple[bool, ...]:
    d1 = row["d1_branch"]
    return tuple(bool(d1[key]) for key in (
        "warm", "snow_active", "graupel_active", "psmlt_raw_candidate",
        "pgmlt_raw_candidate"))


def _verify_activation_interior_point(axis: str, side: str, point: dict,
                                      base_th: float, base_qv: float, pii: float,
                                      baseline_d1: dict[str, object], why: str) -> dict[str, object]:
    need(side in ("fraction_eq_one", "fraction_below_one"), why + " side name")
    input_row = point["input"]
    coordinate = float(input_row[axis])
    coordinate_word = str(input_row["coordinate_word"]).zfill(16)
    need(coordinate_word == word(coordinate), why + " coordinate raw word")
    need(math.isfinite(coordinate), why + " finite interior coordinate")
    expected_th = coordinate if axis == "th16" else base_th
    expected_qv = coordinate if axis == "qv16" else base_qv
    exact(float(input_row["th16"]), expected_th, why + " TH coordinate")
    exact(float(input_row["qv16"]), expected_qv, why + " QV coordinate")
    exact(float(input_row["physical_t16"]), expected_th * pii,
          why + " physical temperature coordinate")

    branch = point["branch"]
    predicate = "activated_fraction_ge_1_observed_value"
    branch_result = _activation_observation(
        branch, axis, coordinate, base_th, base_qv, pii, predicate, why + " branch", baseline_d1)
    fraction = float(branch["activated_fraction"])
    if side == "fraction_eq_one":
        need(fraction >= 1.0, why + " observed fraction-equal-one side")
    else:
        need(fraction < 1.0, why + " observed fraction-below-one side")

    index = THERMAL_INPUT_STATE_INDEX[axis]
    seed = 1.0 if axis == "th16" else expected_qv
    jvp = point["jvp"]
    need(set(jvp) == set(ACTIVATION_OUTPUTS), why + " JVP output inventory")
    vjp_rows = point["vjp_rows"]
    need(set(vjp_rows) == set(ACTIVATION_OUTPUTS), why + " VJP row inventory")
    jvp_values = {key: float(value) for key, value in jvp.items()}
    need(all(math.isfinite(value) for value in jvp_values.values()), why + " finite JVPs")
    exact(jvp_values["final_nccn16"], 0.0, why + " structural final NCCN JVP under floor")
    exact(jvp_values["nccn_final"], 0.0, why + " structural inner NCCN JVP under floor")
    max_vjp_jvp_abs_residual = 0.0
    max_vjp_jvp_rel_residual = 0.0
    for field in ACTIVATION_OUTPUTS:
        row = vjp_rows[field]
        gradient = finite_vector(row["values"], 468, why + " VJP gradient " + field)
        f64_vector_words(gradient, row["raw_hex"], why + " VJP raw words " + field)
        dot = math.fsum((gradient[index] * seed,))
        recorded_dot = float(row["direction_vjp_dot"])
        recorded_jvp = jvp_values[field]
        need(all(math.isfinite(value) for value in (dot, recorded_dot, recorded_jvp)),
             why + " finite VJP/JVP dot values " + field)
        scale = max(abs(dot), abs(recorded_dot), abs(recorded_jvp), 1.0)
        tolerance = 1.0e-8 * scale
        need(abs(recorded_dot - dot) <= tolerance,
             why + " VJP dot reconstruction " + field)
        need(abs(recorded_dot - recorded_jvp) <= tolerance,
             why + " VJP/JVP transpose " + field)
        exact(float(row["dot_minus_jvp"]), recorded_dot - recorded_jvp,
              why + " VJP/JVP residual record " + field)
        abs_residual = abs(recorded_dot - recorded_jvp)
        need(math.isfinite(abs_residual), why + " finite VJP/JVP residual " + field)
        max_vjp_jvp_abs_residual = max(max_vjp_jvp_abs_residual, abs_residual)
        relative_residual = abs_residual / scale
        need(math.isfinite(relative_residual), why + " finite relative VJP/JVP residual " + field)
        max_vjp_jvp_rel_residual = max(max_vjp_jvp_rel_residual, relative_residual)

    fd = point["one_sided_fd"]
    need(fd["coordinate_direction"] == "increasing", why + " one-sided coordinate direction")
    scales = fd["step_scales"]
    expected_steps = ACTIVATION_INTERIOR_FD_STEPS[axis][side]
    need(len(scales) == len(expected_steps), why + " one-sided FD scale count")
    resolved, unresolved = 0, 0
    max_fd_jvp_relative_error = 0.0
    max_fd_jvp_residual_ulp = 0.0
    fd_rows: list[dict[str, object]] = []
    final_nc_relative_errors: list[float] = []
    endpoint_words: set[str] = set()
    for step_row, nominal_step in zip(scales, expected_steps):
        exact(float(step_row["nominal_step"]), nominal_step,
              why + " nominal FD step")
        endpoint = step_row["endpoint"]
        endpoint_coordinate = float(endpoint["input"])
        expected_endpoint_coordinate = (
            float(input_row["th16"]) + nominal_step if axis == "th16"
            else float(input_row["qv16"]) * (1.0 + nominal_step))
        expected_endpoint_word = word(expected_endpoint_coordinate)
        need(math.isfinite(expected_endpoint_coordinate),
             why + " finite expected FD endpoint coordinate")
        endpoint_word = str(endpoint["input_word"]).zfill(16)
        exact(endpoint_coordinate, expected_endpoint_coordinate,
              why + " FD endpoint coordinate follows nominal step")
        need(endpoint_word == expected_endpoint_word,
             why + " FD endpoint raw word follows nominal step")
        need(endpoint_word not in endpoint_words,
             why + " distinct represented FD endpoint per nominal step")
        endpoint_words.add(endpoint_word)
        _activation_observation(
            endpoint, axis, endpoint_coordinate, base_th, base_qv, pii,
            predicate, why + " endpoint " + str(nominal_step), baseline_d1)
        represented_gap = endpoint_coordinate - coordinate
        exact(float(step_row["represented_coordinate_gap"]), represented_gap,
              why + " represented coordinate gap")
        parameter_gap = (represented_gap if axis == "th16"
                         else endpoint_coordinate / coordinate - 1.0)
        need(math.isfinite(represented_gap) and math.isfinite(parameter_gap),
             why + " finite represented FD gaps")
        exact(float(step_row["parameter_gap"]), parameter_gap,
              why + " represented normalized parameter gap")
        need(parameter_gap > 0.0, why + " endpoint is on increasing side")
        same_activation = (_activation_branch_signature(branch)
                           == _activation_branch_signature(endpoint))
        same_d1 = (_activation_d1_signature(branch) == _activation_d1_signature(endpoint))
        need(step_row["same_activation_branch"] is same_activation,
             why + " recorded same-activation-branch flag")
        need(step_row["same_d1_branch"] is same_d1,
             why + " recorded same-D1-branch flag")
        need(same_activation and same_d1,
             why + " FD endpoint remains in same activation and D1 branches")
        outputs = step_row["outputs"]
        need(set(outputs) == set(ACTIVATION_OUTPUTS), why + " FD output inventory")
        for field in ACTIVATION_OUTPUTS:
            out = outputs[field]
            base_value = float(branch[field])
            endpoint_value = float(endpoint[field])
            exact(float(out["base"]), base_value, why + " FD base output " + field)
            exact(float(out["endpoint"]), endpoint_value, why + " FD endpoint output " + field)
            need(str(out["base_raw_hex"]).zfill(16) == word(base_value),
                 why + " FD base output word " + field)
            need(str(out["endpoint_raw_hex"]).zfill(16) == word(endpoint_value),
                 why + " FD endpoint output word " + field)
            fd_value = (endpoint_value - base_value) / parameter_gap
            need(math.isfinite(fd_value), why + " finite FD value " + field)
            exact(float(out["fd"]), fd_value, why + " FD difference " + field)
            exact(float(out["ad_jvp"]), jvp_values[field], why + " FD JVP " + field)
            exact(float(out["fd_minus_jvp"]), fd_value - jvp_values[field],
                  why + " FD residual " + field)
            need(math.isfinite(fd_value - jvp_values[field]),
                 why + " finite FD residual " + field)
            distance = module_ulp_distance(endpoint_value, base_value)
            need(int(out["output_ulp_distance"]) == distance,
                 why + " FD output ULP distance " + field)
            expected_status = ("unresolved_within_32_output_ulps" if distance <= 32
                               else "resolved_over_32_output_ulps")
            need(out["resolution_status"] == expected_status,
                 why + " FD resolution class " + field)
            if distance <= 32:
                unresolved += 1
                relative_error = None
                residual_output_ulps = None
            else:
                resolved += 1
                relative_error = abs(fd_value - jvp_values[field]) / max(
                    abs(fd_value), abs(jvp_values[field]), math.ulp(base_value))
                need(math.isfinite(relative_error), why + " finite FD relative error " + field)
                max_fd_jvp_relative_error = max(max_fd_jvp_relative_error, relative_error)
                if field == "final_nc16":
                    final_nc_relative_errors.append(relative_error)
                residual_output_ulps = (
                    abs(fd_value - jvp_values[field]) * parameter_gap / math.ulp(base_value))
                need(math.isfinite(residual_output_ulps),
                     why + " finite FD output-ULP residual " + field)
                max_fd_jvp_residual_ulp = max(
                    max_fd_jvp_residual_ulp,
                    residual_output_ulps)
            fd_rows.append({
                "nominal_step": nominal_step,
                "field": field,
                "resolution_status": expected_status,
                "relative_error": relative_error,
                "predicted_observed_delta_residual_ulps": residual_output_ulps,
            })
    need(any(error < 1.0e-6 for error in final_nc_relative_errors),
         why + " has at least one resolved final-NC one-sided FD scale below 1e-6")
    return {
        "coordinate": coordinate,
        "branch": branch_result,
        "jvp": jvp_values,
        "vjp_jvp_max_abs_residual": max_vjp_jvp_abs_residual,
        "vjp_jvp_max_relative_residual": max_vjp_jvp_rel_residual,
        "one_sided_fd_resolved_outputs": resolved,
        "one_sided_fd_unresolved_outputs": unresolved,
        "one_sided_fd_checks": fd_rows,
        "final_nc_one_sided_fd_relative_errors": final_nc_relative_errors,
        "max_one_sided_fd_jvp_relative_error": max_fd_jvp_relative_error,
        "max_one_sided_fd_jvp_residual_ulp": max_fd_jvp_residual_ulp,
    }


def verify_activation_boundary(boundary: dict, parent: dict) -> dict[str, object]:
    require_finite_tree(boundary, "activation boundary payload")
    need(boundary["schema"] == ACTIVATION_BOUNDARY_SCHEMA,
         "activation boundary schema")
    thermal = parent["thermal_directions"]
    baseline_input = thermal["input"]
    th0 = float(baseline_input["th16"])
    qv0 = float(baseline_input["qv16"])
    pii = float(baseline_input["pii16"])
    input_meta = boundary["input"]
    for key, expected in (("th16", th0), ("qv16", qv0), ("pii16", pii),
                          ("physical_t16", th0 * pii)):
        exact(float(input_meta[key]), expected, "activation input baseline: " + key)
    for key, expected in (("th16_word", word(th0)), ("qv16_word", word(qv0))):
        need(str(input_meta[key]).zfill(16) == expected, "activation input raw word: " + key)
    need(float(input_meta["dt"]) == 20.0, "activation input dt")
    need(float(input_meta["xland"]) == 2.0, "activation input xland")
    need(input_meta["packed_indices"] == {
        "th16": THERMAL_INPUT_STATE_INDEX["th16"],
        "qv16": THERMAL_INPUT_STATE_INDEX["qv16"],
    }, "activation input packed coordinates")
    thresholds = boundary["thresholds"]
    need(set(thresholds) == {"sw_percent", "observed_activated_fraction_limit"}
         and float(thresholds["sw_percent"]) == 0.48
         and float(thresholds["observed_activated_fraction_limit"]) == 1.0,
         "activation threshold constants")
    need(set(boundary["axes"]) == set(ACTIVATION_AXES), "activation axis inventory")

    baseline_stages = parent["baseline"]["stage_scalars"]
    baseline_summary = thermal["baseline_d1_branch"]
    baseline_d1 = baseline_summary["d1_branch"]
    baseline_obs = _activation_observation(
        boundary["baseline"], "th16", th0, th0, qv0, pii,
        "activated_fraction_ge_1_observed_value", "activation baseline", baseline_d1)
    activation_stage = "fd_satadj_inner."
    baseline_links = (
        ("qv_input", "qv_input"),
        ("sw_percent", "sw_percent"), ("activated_fraction", "activated_fraction"),
        ("ncact_raw", "ncact_raw"), ("ncact", "ncact"),
        ("nc_after_activation", "nc_after_activation"),
        ("nccn_after_activation", "nccn_after_activation"),
        ("nccn_final", "nccn_final"),
    )
    for output_field, stage_field in baseline_links:
        exact(float(boundary["baseline"][output_field]),
              baseline_stages[activation_stage + stage_field],
              "activation baseline stage link: " + output_field)
    baseline_final_raw = parent["baseline"]["value_final_raw"]
    need(word(float(boundary["baseline"]["final_nc16"]))
         == str(baseline_final_raw[8 * 39 + THERMAL_K_INDEX0]).zfill(16),
         "activation baseline final NC16 raw word")
    need(word(float(boundary["baseline"]["final_nccn16"]))
         == str(baseline_final_raw[7 * 39 + THERMAL_K_INDEX0]).zfill(16),
         "activation baseline final NCCN16 raw word")

    baseline_upper = stage_bool(baseline_obs["activated_fraction"] >= 1.0,
                                "activation baseline cap observation")
    counts_by_axis: dict[str, int] = {}
    bisection_summary: dict[str, object] = {}
    interior_summary: dict[str, object] = {}
    adjacent_nc_decomposition: dict[str, object] = {}
    trace_rows = 0
    output_gap_unresolved = 0
    for axis in ACTIVATION_AXES:
        axis_data = boundary["axes"][axis]
        expected_kind = ("absolute potential-temperature K" if axis == "th16"
                         else "relative water-vapor mixing ratio")
        need(axis_data["coordinate_kind"] == expected_kind,
             "activation axis coordinate kind: " + axis)
        expected_seed = ({"fraction_eq_one": th0 + 1e-3,
                          "fraction_below_one": th0 + 1e-2} if axis == "th16"
                         else {"fraction_below_one": qv0 * (1.0 - 1e-3),
                               "fraction_eq_one": qv0 * (1.0 - 1e-4)})
        for key, value in expected_seed.items():
            exact(float(axis_data["bracket_seed"][key]), value,
                  "activation initial bracket seed: " + axis + "/" + key)
        parent_seed_rows = ({
            "fraction_eq_one": ("th16_abs", "0.001", "high"),
            "fraction_below_one": ("th16_abs", "0.01", "high"),
        } if axis == "th16" else {
            "fraction_below_one": ("qv16_rel", "0.001", "low"),
            "fraction_eq_one": ("qv16_rel", "0.0001", "low"),
        })
        parent_activation_fields = (
            "sw_percent", "activated_fraction", "ncact_raw", "ncact",
            "nc_after_activation", "nccn_final",
        )
        for seed_label, (direction_name, step, side) in parent_seed_rows.items():
            expected_coordinate = expected_seed[seed_label]
            parent_pair = thermal["directions"][direction_name]["finite_differences"][step]
            parent_input = parent_pair[side + "_input"]
            exact(float(parent_input[axis]), expected_coordinate,
                  "activation seed native parent coordinate " + axis + "/" + seed_label)
            parent_stages = parent_pair[side + "_stages"]
            trace_seed = axis_data["bisection"][ACTIVATION_BRACKETS[0]]["trace"]
            # Both declared seed evaluations are the first two rows; select by
            # coordinate rather than assuming lower/upper orientation.
            trace_row = next(row for row in trace_seed
                             if word(float(row["input"])) == word(expected_coordinate))
            for field in parent_activation_fields:
                stage_key = "fd_satadj_inner." + field
                exact(float(trace_row[field]), float(parent_stages[stage_key]),
                      "activation seed parent stage anchor: " + axis + "/" + seed_label
                      + "/" + field)
            parent_final = parent_pair[side + "_final_raw"]
            need(word(float(trace_row["final_nc16"]))
                 == str(parent_final[8 * 39 + THERMAL_K_INDEX0]).zfill(16),
                 "activation seed parent final NC anchor: " + axis + "/" + seed_label)
            need(word(float(trace_row["final_nccn16"]))
                 == str(parent_final[7 * 39 + THERMAL_K_INDEX0]).zfill(16),
                 "activation seed parent final NCCN anchor: " + axis + "/" + seed_label)
        need(set(axis_data["bisection"]) == set(ACTIVATION_BRACKETS),
             "activation bisection inventory: " + axis)
        axis_calls = 0
        bisection_summary[axis] = {}
        for kind in ACTIVATION_BRACKETS:
            if axis == "th16":
                seed_low, seed_high = (expected_seed["fraction_eq_one"],
                                       expected_seed["fraction_below_one"])
            else:
                seed_low, seed_high = (expected_seed["fraction_below_one"],
                                       expected_seed["fraction_eq_one"])
            result = _verify_activation_bracket(
                axis, kind, axis_data["bisection"][kind], seed_low, seed_high,
                th0, qv0, pii, baseline_d1, axis + "/" + kind)
            axis_calls += result["value_only_calls"]
            trace_rows += result["value_only_calls"]
            output_gap_unresolved += sum(
                gap["resolution_status"] == "unresolved_at_f64_output_resolution"
                for gap in result["output_gaps"].values())
            bisection_summary[axis][kind] = result
            lo, hi = result["lower"], result["upper"]
            observed_delta = float(hi["nc_after_activation"]) - float(lo["nc_after_activation"])
            activation_delta = ((float(hi["ncact"]) - float(lo["ncact"]))
                                * float(lo["dtcld"]))
            adjacent_nc_decomposition[axis + "/" + kind] = {
                "delta_nc_after_activation": observed_delta,
                "delta_ncact_times_dt": activation_delta,
                "remainder_after_activation_rate_change": observed_delta - activation_delta,
                "delta_final_nc16": float(hi["final_nc16"]) - float(lo["final_nc16"]),
                "final_minus_post_activation_delta": (
                    (float(hi["final_nc16"]) - float(lo["final_nc16"])) - observed_delta),
                "delta_final_nccn16": float(hi["final_nccn16"]) - float(lo["final_nccn16"]),
                "interpretation": "adjacent endpoint arithmetic; not causal attribution",
            }
        if "interior_points" in axis_data:
            points = axis_data["interior_points"]
            need(set(points) == {"fraction_eq_one", "fraction_below_one"},
                 "activation interior point inventory: " + axis)
            interior_summary[axis] = {
                side: _verify_activation_interior_point(
                    axis, side, points[side], th0, qv0, pii, baseline_d1,
                    "activation interior " + axis + "/" + side)
                for side in ("fraction_eq_one", "fraction_below_one")
            }
        counts_by_axis[axis] = axis_calls

    call_counts = boundary["call_counts"]
    need(call_counts["baseline_off_on"] == 2, "activation baseline off/on calls")
    need(call_counts["th16_bisection_calls"] == counts_by_axis["th16"],
         "activation TH bisection call ledger")
    need(call_counts["qv16_bisection_calls"] == counts_by_axis["qv16"],
         "activation QV bisection call ledger")
    need(call_counts["value_only_bisection_forward_calls"] == trace_rows,
         "activation bisection total call ledger")
    interior_calls = 4 if interior_summary else 0
    fd_calls = (sum(len(steps) for sides in ACTIVATION_INTERIOR_FD_STEPS.values()
                     for steps in sides.values()) if interior_summary else 0)
    if interior_summary:
        need(call_counts["interior_ad_forward_calls"] == interior_calls,
             "activation interior AD call ledger")
        need(call_counts["one_sided_fd_value_only_forward_calls"] == fd_calls,
             "activation one-sided FD call ledger")
    need(call_counts["total_full_call_forwards"] == 2 + trace_rows + interior_calls + fd_calls,
         "activation total forward-call ledger")
    return {
        "activation_boundary_schema": boundary["schema"],
        "activation_boundary_input": input_meta,
        "activation_thresholds": thresholds,
        "activation_baseline_observation": boundary["baseline"],
        "activation_bisection_calls_by_axis": counts_by_axis,
        "activation_bisection_trace_rows": trace_rows,
        "activation_bisection_unresolved_output_gaps": output_gap_unresolved,
        "activation_bisection_results": bisection_summary,
        "activation_interior_points": interior_summary,
        "activation_interior_ad_calls": interior_calls,
        "activation_one_sided_fd_calls": fd_calls,
        "activation_adjacent_nc_decomposition": adjacent_nc_decomposition,
        "activation_call_counts": call_counts,
        "activation_baseline_upper_fraction_observed": baseline_upper,
    }


def thermal_vjp_dot(gradient: list[float], direction: list[float]) -> float:
    need(len(gradient) == len(direction) == 12 * 39, "thermal VJP dot vector shape")
    total = 0.0
    for g, v in zip(gradient, direction):
        total += g * v
    return total


def thermal_vjp_direction(data: dict, thermal_vjp: dict, direction_name: str,
                          direction: dict, stages: dict[str, float], order: list[str],
                          base_state: np.ndarray, pii: float) -> dict[str, object]:
    need(direction["normalization"] == {
        "th16_abs": "absolute K potential-temperature increment",
        "qv16_rel": "relative qv increment",
        "th16_abs_qv16_rel_joint": "joint: absolute K potential-temperature and relative qv increments",
    }[direction_name], "thermal direction normalization: " + direction_name)
    need(direction["packed_indices"] == {
        "th16": THERMAL_INPUT_STATE_INDEX["th16"],
        "qv16": THERMAL_INPUT_STATE_INDEX["qv16"],
    }, "thermal packed input indices: " + direction_name)
    base_qv = float(base_state[1, THERMAL_K_INDEX0])
    expected_seed = {
        "th16": 1.0 if direction_name != "qv16_rel" else 0.0,
        "qv16": base_qv if direction_name != "th16_abs" else 0.0,
    }
    for key, expected in expected_seed.items():
        exact(float(direction["seed"][key]), expected,
              "thermal input seed: " + direction_name + "/" + key)
    jvp = direction["jvp"]
    stage_jvp = finite_vector(jvp["stage_jvp"], len(order),
                              "thermal stage JVP " + direction_name)
    stage_tangent = dict(zip(order, stage_jvp))
    final_state = finite_vector(jvp["final_state"], 12 * 39,
                                "thermal final state JVP " + direction_name)
    f64_vector_words(final_state, jvp["final_state_raw"],
                     "thermal final state JVP words " + direction_name)
    final_pair = finite_vector(jvp["final_nc_nccn"], 2,
                               "thermal final NC/NCCN JVP " + direction_name)
    exact(final_pair[0], final_state[8 * 39 + THERMAL_K_INDEX0],
          "thermal NC selected output JVP link: " + direction_name)
    exact(final_pair[1], final_state[7 * 39 + THERMAL_K_INDEX0],
          "thermal NCCN selected output JVP link: " + direction_name)
    need(len(finite_vector(jvp["selected_pre2_qg_brs"], 2,
                            "thermal pre2 selected JVP " + direction_name)) == 2,
         "thermal pre2 selected JVP fields")

    d_source = thermal_d1_jvp_sources(stages, expected_seed["th16"],
                                      expected_seed["qv16"], pii,
                                      "thermal source JVP " + direction_name)
    checks = {
        MELT_STAGE + ".t": d_source["d_temperature"],
        MELT_STAGE + ".cpm": d_source["d_cpm"],
        NEW_STAGE + ".pre_cpm": d_source["d_cpm"],
        NEW_STAGE + ".cpm_safe": d_source["d_cpm"],
        MELT_STAGE + ".work2": d_source["d_work2"],
        MELT_STAGE + ".psmlt_sum": d_source["d_psmlt_sum"],
        MELT_STAGE + ".psmlt_raw": d_source["d_psmlt_raw"],
        MELT_STAGE + ".psmlt_capped_g": d_source["d_psmlt_capped_g"],
        MELT_STAGE + ".psmlt": d_source["d_psmlt"],
        MELT_STAGE + ".t1": d_source["d_t1"],
        MELT_STAGE + ".pgmlt_sum": d_source["d_pgmlt_sum"],
        MELT_STAGE + ".pgmlt_raw": d_source["d_pgmlt_raw"],
        MELT_STAGE + ".pgmlt": d_source["d_pgmlt"],
    }
    for key, expected in checks.items():
        near_chain(stage_tangent[key], expected, (expected,),
                   "thermal source-order JVP " + direction_name + "/" + key)
    if direction_name == "qv16_rel":
        for key in (MELT_STAGE + ".work2", MELT_STAGE + ".psmlt_raw",
                    MELT_STAGE + ".psmlt_capped_g", MELT_STAGE + ".psmlt"):
            exact(stage_tangent[key], 0.0,
                  "structural QV-independent D1 output tangent: " + key)
    if direction_name == "th16_abs":
        exact(stage_tangent[MELT_STAGE + ".cpm"], 0.0,
              "structural TH-independent entry cpm tangent")

    input_direction = [0.0] * (12 * 39)
    input_direction[THERMAL_INPUT_STATE_INDEX["th16"]] = expected_seed["th16"]
    input_direction[THERMAL_INPUT_STATE_INDEX["qv16"]] = expected_seed["qv16"]
    dots = direction["vjp_dot_checks"]
    expected_dot_fields = set(THERMAL_STAGE_VJP_FIELDS) | {"final_nc16", "final_nccn16"}
    need(set(dots) == expected_dot_fields, "thermal VJP dot inventory: " + direction_name)
    for field in THERMAL_STAGE_VJP_FIELDS:
        row = thermal_vjp["rows"][field]
        gradient = finite_vector(row["values"], 12 * 39, "thermal VJP " + field)
        f64_vector_words(gradient, row["raw_hex"], "thermal VJP raw words " + field)
        dot = thermal_vjp_dot(gradient, input_direction)
        stage_idx = order.index(field)
        expected_jvp = stage_tangent[field]
        exact(float(dots[field]["stage_jvp"]), expected_jvp,
              "thermal VJP row JVP link: " + direction_name + "/" + field)
        near_roundoff(float(dots[field]["vjp_dot"]), dot, (dot,),
                      "thermal VJP row dot reconstruction: " + direction_name + "/" + field)
        near_roundoff(float(dots[field]["vjp_dot"]), expected_jvp,
                      (float(dots[field]["vjp_dot"]), expected_jvp),
                      "thermal VJP/JVP transpose check: " + direction_name + "/" + field)
        exact(float(dots[field]["dot_minus_jvp"]), dot - expected_jvp,
              "thermal VJP dot residual: " + direction_name + "/" + field)
        need(stage_idx < len(stage_jvp), "thermal stage JVP row index")
    for key, gradient_name, output_index in (
        ("final_nc16", "final_nc16", 0), ("final_nccn16", "final_nccn16", 1),
    ):
        gradient = finite_vector(data["vjp"][gradient_name], 12 * 39,
                                 "thermal final state VJP " + gradient_name)
        dot = thermal_vjp_dot(gradient, input_direction)
        expected_jvp = final_pair[output_index]
        near_roundoff(float(dots[key]["vjp_dot"]), dot, (dot,),
                      "thermal final-state VJP dot reconstruction: " + direction_name + "/" + key)
        near_roundoff(float(dots[key]["jvp"]), expected_jvp,
                      (float(dots[key]["jvp"]), expected_jvp),
                      "thermal final-state JVP link: " + direction_name + "/" + key)
        near_roundoff(float(dots[key]["vjp_dot"]), expected_jvp,
                      (float(dots[key]["vjp_dot"]), expected_jvp),
                      "thermal final-state VJP/JVP transpose: " + direction_name + "/" + key)
        exact(float(dots[key]["dot_minus_jvp"]), dot - expected_jvp,
              "thermal final-state VJP residual: " + direction_name + "/" + key)
    return {
        "stage_jvp": stage_tangent,
        "final_state_jvp": final_state,
        "final_nc_nccn_jvp": final_pair,
        "source_jvp": d_source,
        "input_direction": input_direction,
    }


def verify_thermal_payload(data: dict, prior: dict, order: list[str]) -> dict[str, object]:
    thermal = data["thermal_directions"]
    need(thermal["schema"] == THERMAL_DIRECTIONS_SCHEMA, "thermal directions schema")
    for role in ("value_final_raw", "graph_final_raw"):
        baseline_words = data["baseline"][role]
        need(isinstance(baseline_words, list) and len(baseline_words) == 468,
             "thermal baseline final state inventory: " + role)
        for index, raw_word in enumerate(baseline_words):
            finite_final_word(raw_word, "thermal baseline " + role + "/" + str(index))
    thermal_vjp = data["thermal_vjp"]
    need(thermal_vjp["schema"] == THERMAL_VJP_SCHEMA, "thermal VJP schema")
    need(thermal_vjp["selected_k_index0"] == THERMAL_K_INDEX0,
         "thermal VJP selected level")
    need(tuple(thermal_vjp["state_order"]) == THERMAL_STATE_ORDER,
         "thermal VJP packed state order")
    need(set(thermal_vjp["rows"]) == set(THERMAL_STAGE_VJP_FIELDS),
         "thermal VJP D1 stage rows")

    baseline_npz = native_npz(
        THERMAL_NATIVE_VJP_PACKET,
        THERMAL_NATIVE_MANIFEST_SHA[THERMAL_NATIVE_VJP_PACKET.name],
        "raw/nc16_result.npz")
    baseline_state = baseline_npz["state"]
    baseline_forcing = baseline_npz["forcing"]
    need(baseline_state.shape == (12, 39) and baseline_state.dtype == np.float64,
         "thermal baseline packed state shape/dtype")
    need(baseline_forcing.shape == (4, 39) and baseline_forcing.dtype == np.float64,
         "thermal baseline packed forcing shape/dtype")
    input_meta = thermal["input"]
    base_th = float(baseline_state[0, THERMAL_K_INDEX0])
    base_qv = float(baseline_state[1, THERMAL_K_INDEX0])
    pii = float(baseline_forcing[1, THERMAL_K_INDEX0])
    stage_jvps: dict[str, dict[str, float]] = {}
    final_state_jvps: dict[str, list[float]] = {}
    final_pair_jvps: dict[str, list[float]] = {}
    d1_branch_rows: list[dict[str, object]] = []
    activation_crossings: list[str] = []
    thermal_fd_rows: list[dict[str, object]] = []
    exact(float(input_meta["th16"]), base_th, "thermal baseline TH16 parent anchor")
    exact(float(input_meta["qv16"]), base_qv, "thermal baseline QV16 parent anchor")
    exact(float(input_meta["pii16"]), pii, "thermal baseline PII16 parent anchor")
    exact(float(input_meta["physical_t16"]), base_th * pii,
          "thermal baseline physical temperature")
    need(str(input_meta["th16_raw"]).zfill(16) == word(base_th)
         and str(input_meta["qv16_raw"]).zfill(16) == word(base_qv),
         "thermal input raw TH/QV words")
    base_stages = data["baseline"]["stage_scalars"]
    thermal_cpm_work2_values(base_stages, base_th, base_qv, pii, "thermal baseline")
    thermal_stage_source_values(base_stages, base_th, base_qv, pii, "thermal baseline")
    base_branch = verify_thermal_branch(
        thermal["baseline_d1_branch"], base_stages, base_th, base_qv, pii,
        stage_bool(thermal["baseline_d1_branch"]["activation"]["activation_fraction_at_upper_bound"],
                   "thermal baseline activation cap"), "thermal baseline branch")
    baseline_activation_upper = base_branch["activation_upper_bound"]
    d1_branch_rows.append({"case": "baseline", **base_branch})

    for field in THERMAL_STAGE_VJP_FIELDS:
        row = thermal_vjp["rows"][field]
        gradient = finite_vector(row["values"], 12 * 39, "thermal VJP gradient " + field)
        f64_vector_words(gradient, row["raw_hex"], "thermal VJP gradient raw words " + field)

    thermal_directions = thermal["directions"]
    need(set(thermal_directions) == set(THERMAL_DIRECTION_NAMES),
         "thermal direction names")
    for direction_name in THERMAL_DIRECTION_NAMES:
        direction = thermal_directions[direction_name]
        normalization = {
            "th16_abs": "absolute K potential-temperature increment",
            "qv16_rel": "relative qv increment",
            "th16_abs_qv16_rel_joint": "joint: absolute K potential-temperature and relative qv increments",
        }[direction_name]
        need(direction["normalization"] == normalization,
             "thermal direction normalization: " + direction_name)
        seed_check = thermal_vjp_direction(
            data, thermal_vjp, direction_name, direction, base_stages, order,
            baseline_state, pii)
        stage_tangent = seed_check["stage_jvp"]
        final_state_tangent = seed_check["final_state_jvp"]
        final_pair_tangent = seed_check["final_nc_nccn_jvp"]
        stage_jvps[direction_name] = stage_tangent
        final_state_jvps[direction_name] = final_state_tangent
        final_pair_jvps[direction_name] = final_pair_tangent

        for field, expected in seed_check["source_jvp"].items():
            # Chain summaries are retained in the ledger; individual D1 stage fields
            # are checked below with source-dependent equations.
            need(math.isfinite(expected), "finite thermal JVP term: " + direction_name + "/" + field)
        source_expected = seed_check["source_jvp"]
        direct_checks = {
            MELT_STAGE + ".t": source_expected["d_temperature"],
            MELT_STAGE + ".cpm": source_expected["d_cpm"],
            NEW_STAGE + ".pre_cpm": source_expected["d_cpm"],
            NEW_STAGE + ".cpm_safe": source_expected["d_cpm"],
            MELT_STAGE + ".work2": source_expected["d_work2"],
            MELT_STAGE + ".psmlt_sum": source_expected["d_psmlt_sum"],
            MELT_STAGE + ".psmlt_raw": source_expected["d_psmlt_raw"],
            MELT_STAGE + ".psmlt_capped_g": source_expected["d_psmlt_capped_g"],
            MELT_STAGE + ".psmlt": source_expected["d_psmlt"],
            MELT_STAGE + ".t1": source_expected["d_t1"],
            MELT_STAGE + ".pgmlt_sum": source_expected["d_pgmlt_sum"],
            MELT_STAGE + ".pgmlt_raw": source_expected["d_pgmlt_raw"],
            MELT_STAGE + ".pgmlt": source_expected["d_pgmlt"],
        }
        for field, expected in direct_checks.items():
            near_chain(stage_tangent[field], expected, (expected,),
                       "thermal source-order JVP: " + direction_name + "/" + field)
        if direction_name == "qv16_rel":
            for field in (MELT_STAGE + ".work2", MELT_STAGE + ".psmlt_raw",
                          MELT_STAGE + ".psmlt_capped_g", MELT_STAGE + ".psmlt"):
                exact(stage_tangent[field], 0.0,
                      "structural QV-independent D1 tangent: " + field)
        if direction_name == "th16_abs":
            exact(stage_tangent[MELT_STAGE + ".cpm"], 0.0,
                  "structural TH-independent cpm tangent")

        fd_cases = direction["finite_differences"]
        need(set(fd_cases) == set(THERMAL_STEPS[direction_name]),
             "thermal FD step plan: " + direction_name)
        smooth_h = set(THERMAL_SMOOTH_STEPS[direction_name])
        for hkey, pair in fd_cases.items():
            h = float(hkey)
            need(float(pair["h"]) == h, "thermal FD recorded h: " + direction_name + "/" + hkey)
            endpoint_summaries = {}
            endpoint_stages = {}
            endpoint_inputs = {}
            for side, sign in (("low", -1.0), ("high", 1.0)):
                input_info = pair[side + "_input"]
                expected_th = base_th + (sign * h if direction_name != "qv16_rel" else 0.0)
                expected_qv = base_qv * (1.0 + sign * h if direction_name != "th16_abs" else 1.0)
                exact(float(input_info["th16"]), expected_th,
                      "thermal FD TH16 input: " + direction_name + "/" + hkey + "/" + side)
                exact(float(input_info["qv16"]), expected_qv,
                      "thermal FD QV16 input: " + direction_name + "/" + hkey + "/" + side)
                exact(float(input_info["physical_t16"]), expected_th * pii,
                      "thermal FD physical temperature: " + direction_name + "/" + hkey + "/" + side)
                need(str(input_info["th16_raw"]).zfill(16) == word(expected_th)
                     and str(input_info["qv16_raw"]).zfill(16) == word(expected_qv),
                     "thermal FD input words: " + direction_name + "/" + hkey + "/" + side)
                stage_values = pair[side + "_stages"]
                need(set(stage_values) == set(base_stages),
                     "thermal endpoint stage inventory: " + direction_name + "/" + hkey + "/" + side)
                thermal_stage_source_values(stage_values, expected_th, expected_qv, pii,
                                            "thermal endpoint " + direction_name + "/" + hkey + "/" + side)
                melt_expected = source_order_melt_producer(stage_values)
                for field in MELT_SOURCE_CHECK_FIELDS:
                    actual = stage_values[MELT_STAGE + "." + field]
                    expected = melt_expected[field]
                    if field in MELT_BOOL_FIELDS:
                        need(stage_bool(actual, "thermal melt mask") == bool(expected),
                             "thermal D1 source gate: " + direction_name + "/" + hkey + "/" + side + "/" + field)
                    else:
                        exact(actual, expected,
                              "thermal D1 source-order value: " + direction_name + "/" + hkey + "/" + side + "/" + field)
                summary = pair[side + "_branch"]
                signature = verify_thermal_branch(
                    summary, stage_values, expected_th, expected_qv, pii, baseline_activation_upper,
                    "thermal endpoint branch " + direction_name + "/" + hkey + "/" + side)
                need({key: signature[key] for key in (
                    "warm", "snow_active", "graupel_active", "graupel_mask",
                    "psmlt_cap_is_raw_candidate", "pgmlt_cap_is_raw_candidate")}
                     == {key: base_branch[key] for key in (
                         "warm", "snow_active", "graupel_active", "graupel_mask",
                         "psmlt_cap_is_raw_candidate", "pgmlt_cap_is_raw_candidate")},
                     "thermal D1 branch fixed: " + direction_name + "/" + hkey + "/" + side)
                if signature["activation_upper_changed"]:
                    activation_crossings.append(direction_name + "/" + hkey + "/" + side)
                d1_branch_rows.append({"case": direction_name + "/" + hkey + "/" + side,
                                      **signature})
                final_words = pair[side + "_final_raw"]
                need(len(final_words) == 468 and all(isinstance(x, str) for x in final_words),
                     "thermal final endpoint raw inventory: " + direction_name + "/" + hkey + "/" + side)
                for index, raw_word in enumerate(final_words):
                    finite_final_word(raw_word, "thermal endpoint " + direction_name
                                      + "/" + hkey + "/" + side + "/" + str(index))
                selected_pre2 = finite_vector(pair[side + "_selected_pre2"], 2,
                                               "thermal endpoint selected pre2")
                exact(selected_pre2[0], stage_values["pre2_producer.qg_input"],
                      "thermal endpoint pre2 QG link")
                exact(selected_pre2[1], stage_values["pre2_producer.brs_input"],
                      "thermal endpoint pre2 BRS link")
                endpoint_summaries[side] = signature
                endpoint_stages[side] = stage_values
                endpoint_inputs[side] = input_info
            d1_smooth_accepted = True
            final_smooth_accepted = hkey in smooth_h
            if final_smooth_accepted:
                need(not endpoint_summaries["low"]["activation_upper_changed"]
                     and not endpoint_summaries["high"]["activation_upper_changed"],
                     "accepted thermal smooth endpoints keep activation upper branch: " + direction_name + "/" + hkey)
            thermal_fd_rows.append({
                "direction": direction_name,
                "h": hkey,
                "d1_fd_accepted": d1_smooth_accepted,
                "final_fd_accepted": final_smooth_accepted,
                "low_input": endpoint_inputs["low"],
                "high_input": endpoint_inputs["high"],
                "low_stages": endpoint_stages["low"],
                "high_stages": endpoint_stages["high"],
            })

    # All three directions use the same packed input coordinates, so the mixed
    # JVP must equal the sum of the independent TH and QV JVPs.
    joint = thermal_directions["th16_abs_qv16_rel_joint"]["jvp"]
    th_jvp = thermal_directions["th16_abs"]["jvp"]
    qv_jvp = thermal_directions["qv16_rel"]["jvp"]
    joint_stages = finite_vector(joint["stage_jvp"], len(order), "thermal joint stage JVP")
    th_stages = finite_vector(th_jvp["stage_jvp"], len(order), "thermal TH stage JVP")
    qv_stages = finite_vector(qv_jvp["stage_jvp"], len(order), "thermal QV stage JVP")
    max_stage_joint_abs_residual = 0.0
    max_stage_joint_relative_residual = 0.0
    max_stage_joint_residual_field = ""
    for index, field in enumerate(order):
        residual = abs(joint_stages[index] - (th_stages[index] + qv_stages[index]))
        scale = max(abs(joint_stages[index]), abs(th_stages[index] + qv_stages[index]), 1e-300)
        relative = residual / scale
        max_stage_joint_abs_residual = max(max_stage_joint_abs_residual, residual)
        if relative > max_stage_joint_relative_residual:
            max_stage_joint_relative_residual = relative
            max_stage_joint_residual_field = field
    for field in (
        *THERMAL_STAGE_VJP_FIELDS,
        MELT_STAGE + ".psmlt", MELT_STAGE + ".pgmlt",
        MELT_STAGE + ".cpm", NEW_STAGE + ".pre_cpm",
    ):
        index = order.index(field)
        actual = joint_stages[index]
        predicted = th_stages[index] + qv_stages[index]
        residual = abs(actual - predicted)
        relative = residual / max(abs(actual), abs(predicted), math.ulp(base_stages[field]))
        need(relative <= THERMAL_FD_REL_TOL,
             "thermal joint D1-stage JVP linearity: " + field)
    joint_final = finite_vector(joint["final_state"], 468, "thermal joint final-state JVP")
    th_final = finite_vector(th_jvp["final_state"], 468, "thermal TH final-state JVP")
    qv_final = finite_vector(qv_jvp["final_state"], 468, "thermal QV final-state JVP")
    for index, (actual, th_value, qv_value) in enumerate(zip(joint_final, th_final, qv_final)):
        predicted = th_value + qv_value
        relative = abs(actual - predicted) / max(abs(actual), abs(predicted), math.ulp(0.0))
        need(relative <= THERMAL_FD_REL_TOL,
             "thermal joint final-state JVP linearity: " + str(index))

    # Source-ordered selected native values and full final states are anchored
    # in the inherited #546 TH and #550 QV saved endpoints.
    helper_path = PARENT / "native_anchors.py"
    need(sha(helper_path.read_bytes()) == THERMAL_NATIVE_ANCHORS_SHA,
         "pinned native thermal anchor helper")
    helper_spec = importlib.util.spec_from_file_location("native_thermal_anchors", helper_path)
    need(helper_spec is not None and helper_spec.loader is not None,
         "native thermal anchor helper loader")
    anchor_module = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(anchor_module)
    anchors = anchor_module.check_native_thermal_anchors(
        data, EVIDENCE, THERMAL_NATIVE_MANIFEST_SHA)

    # Central and one-sided differences use actual represented input gaps.
    central_checks = []
    one_sided_checks = []
    max_thermal_fd_relative_error = 0.0
    max_thermal_one_sided_relative_error = 0.0
    structural_zero_signals = 0
    stage_basis = {
        name: dict(zip(order, finite_vector(thermal_directions[name]["jvp"]["stage_jvp"],
                                           len(order), "thermal basis stage JVP " + name)))
        for name in THERMAL_DIRECTION_NAMES
    }
    for row in thermal_fd_rows:
        if not row["d1_fd_accepted"]:
            continue
        direction_name = row["direction"]
        h = float(row["h"])
        lo_input, hi_input = row["low_input"], row["high_input"]
        d_th = float(hi_input["th16"]) - float(lo_input["th16"])
        d_qv_relative = (float(hi_input["qv16"]) - float(lo_input["qv16"])) / base_qv
        lo_stages, hi_stages = row["low_stages"], row["high_stages"]
        for stage_field in THERMAL_D1_FD_FIELDS:
            baseline_value = base_stages[stage_field]
            observed = hi_stages[stage_field] - lo_stages[stage_field]
            predicted = (stage_basis["th16_abs"][stage_field] * d_th
                         + stage_basis["qv16_rel"][stage_field] * d_qv_relative)
            ulp = math.ulp(baseline_value)
            if direction_name == "qv16_rel" and stage_field in (
                    MELT_STAGE + ".work2", MELT_STAGE + ".psmlt_capped_g",
                    MELT_STAGE + ".psmlt"):
                exact(hi_stages[stage_field], lo_stages[stage_field],
                      "structural QV-independent D1 endpoint: " + stage_field)
                exact(predicted, 0.0, "structural QV-independent D1 prediction: " + stage_field)
                structural_zero_signals += 1
                continue
            need(abs(observed) > 32 * ulp,
                 "thermal D1 FD signal resolved above 32 ULP: " + direction_name + "/" + row["h"] + "/" + stage_field)
            error = abs(observed - predicted) / max(abs(observed), abs(predicted), ulp)
            need(error <= THERMAL_FD_REL_TOL,
                 "thermal D1 central FD: " + direction_name + "/" + row["h"] + "/" + stage_field)
            max_thermal_fd_relative_error = max(max_thermal_fd_relative_error, error)
            central_checks.append({"direction": direction_name, "h": row["h"],
                                   "stage": stage_field, "error": error,
                                   "observed": observed, "predicted": predicted,
                                   "output_ulp": abs(observed) / ulp})
            for side in ("low", "high"):
                endpoint_input = row[side + "_input"]
                endpoint_stages = row[side + "_stages"]
                one_dth = float(endpoint_input["th16"]) - base_th
                one_dqv_relative = (float(endpoint_input["qv16"]) - base_qv) / base_qv
                one_observed = endpoint_stages[stage_field] - baseline_value
                one_predicted = (stage_basis["th16_abs"][stage_field] * one_dth
                                 + stage_basis["qv16_rel"][stage_field] * one_dqv_relative)
                one_ulp = math.ulp(baseline_value)
                if direction_name == "qv16_rel" and stage_field in (
                        MELT_STAGE + ".work2", MELT_STAGE + ".psmlt_capped_g",
                        MELT_STAGE + ".psmlt"):
                    exact(endpoint_stages[stage_field], baseline_value,
                          "structural QV-independent D1 one-sided endpoint: " + stage_field)
                    continue
                one_error = abs(one_observed - one_predicted) / max(abs(one_observed), abs(one_predicted), one_ulp)
                need(one_error < 4.0 * h,
                     "thermal D1 one-sided FD: " + direction_name + "/" + row["h"] + "/" + side + "/" + stage_field)
                max_thermal_one_sided_relative_error = max(max_thermal_one_sided_relative_error, one_error)
                one_sided_checks.append({"direction": direction_name, "h": row["h"],
                                         "side": side, "stage": stage_field,
                                         "error": one_error, "observed": one_observed,
                                         "predicted": one_predicted,
                                         "output_ulp": abs(one_observed) / one_ulp})

    final_fd_path = PARENT / "final_fd.py"
    final_fd_sha = sha(final_fd_path.read_bytes())
    need(final_fd_sha == THERMAL_FINAL_FD_SHA, "pinned branch-aware final thermal FD helper")
    final_fd_spec = importlib.util.spec_from_file_location("thermal_final_fd", final_fd_path)
    need(final_fd_spec is not None and final_fd_spec.loader is not None,
         "final thermal FD helper loader")
    final_fd_module = importlib.util.module_from_spec(final_fd_spec)
    final_fd_spec.loader.exec_module(final_fd_module)
    final_fd_summary = final_fd_module.check_final_thermal_differences(data)

    return {
        "thermal_direction_names": list(THERMAL_DIRECTION_NAMES),
        "thermal_native_vjp_selected_k_index0": thermal_vjp["selected_k_index0"],
        "thermal_native_vjp_state_order": list(thermal_vjp["state_order"]),
        "thermal_native_d1_output_vjp_rows": len(thermal_vjp["rows"]),
        "thermal_native_d1_output_vjp_gradient_words": len(thermal_vjp["rows"]) * 468,
        "thermal_input_baseline": {"th16": base_th, "qv16": base_qv,
                                   "pii16": pii, "physical_t16": base_th * pii},
        "thermal_baseline_source_values": thermal_cpm_work2_values(
            base_stages, base_th, base_qv, pii, "thermal baseline summary"),
        "thermal_branch_summaries": d1_branch_rows,
        "thermal_activation_crossings": activation_crossings,
        "thermal_native_anchor_summary": anchors,
        "thermal_native_anchor_helper_sha256": THERMAL_NATIVE_ANCHORS_SHA,
        "thermal_final_fd_helper_sha256": final_fd_sha,
        "thermal_runtime_source_sha256": THERMAL_RUNTIME_SOURCE_SHA,
        "thermal_joint_stage_jvp_max_abs_residual": max_stage_joint_abs_residual,
        "thermal_joint_stage_jvp_max_relative_residual": max_stage_joint_relative_residual,
        "thermal_joint_stage_jvp_max_residual_field": max_stage_joint_residual_field,
        "thermal_smooth_fd_steps": {key: list(value) for key, value in THERMAL_SMOOTH_STEPS.items()},
        "thermal_d1_fd_pairs": len([row for row in thermal_fd_rows if row["d1_fd_accepted"]]),
        "thermal_final_fd_pairs": len([row for row in thermal_fd_rows if row["final_fd_accepted"]]),
        "thermal_fd_central_checks": central_checks,
        "thermal_fd_one_sided_checks": one_sided_checks,
        "thermal_fd_central_check_count": len(central_checks),
        "thermal_fd_one_sided_check_count": len(one_sided_checks),
        "thermal_structural_zero_qv_checks": structural_zero_signals,
        "max_thermal_fd_relative_error": max_thermal_fd_relative_error,
        "max_thermal_one_sided_relative_error": max_thermal_one_sided_relative_error,
        "thermal_source_jvp_terms": {
            name: thermal_d1_jvp_sources(base_stages,
                                         float(thermal_directions[name]["seed"]["th16"]),
                                         float(thermal_directions[name]["seed"]["qv16"]),
                                         pii, "thermal reported source terms " + name)
            for name in THERMAL_DIRECTION_NAMES
        },
        **final_fd_summary,
    }


def thermal_d1_jvp_sources(stages: dict[str, float], th_seed: float, qv_seed: float,
                            pii: float, why: str) -> dict[str, float]:
    t = stages[MELT_STAGE + ".t"]
    qv = stages[NEW_STAGE + ".qv_before"]
    cpm = stages[MELT_STAGE + ".cpm"]
    xlf = stages[MELT_STAGE + ".xlf"]
    work2 = stages[MELT_STAGE + ".work2"]
    cpm_safe = stages[NEW_STAGE + ".cpm_safe"]
    d_t = pii * th_seed
    d_qv = qv_seed
    d_cpm = (THERMAL_CPMV - THERMAL_CPMD) * d_qv if qv > THERMAL_QMIN else 0.0
    d_work2 = source_order_work2_jvp(t, work2, d_t)

    dtcld = stages[MELT_STAGE + ".dtcld"]
    n0sfac = stages[MELT_STAGE + ".n0sfac"]
    need(n0sfac == 1.0, why + " snow prefactor is on its constant lower clamp")
    need(word(stages[MELT_STAGE + ".psmlt_dt"])
         == word(stages[MELT_STAGE + ".psmlt_capped"])
         and word(stages[MELT_STAGE + ".pgmlt_dt"])
         == word(stages[MELT_STAGE + ".pgmlt_capped"]),
         why + " D1 mass caps remain on raw candidates")
    psmlt_sum = stages[MELT_STAGE + ".psmlt_sum"]
    psmlt_term2 = stages[MELT_STAGE + ".psmlt_term2"]
    d_psmlt_sum = psmlt_term2 * d_work2 / work2
    xka = stages[MELT_STAGE + ".xka_val"]
    d_xka = xka * (1.5 / t - 1.0 / (t + 120.0)) * d_t
    t0 = stages[MELT_STAGE + ".t0c"]
    psmlt_raw = stages[MELT_STAGE + ".psmlt_raw"]
    d_psmlt_raw = psmlt_raw * (d_xka / xka - d_t / (t0 - t)
                               + d_psmlt_sum / psmlt_sum)
    d_psmlt_amount = d_psmlt_raw * dtcld
    d_psmlt_rate = d_psmlt_amount / dtcld
    psmlt_amount = stages[MELT_STAGE + ".psmlt_capped_g"]
    d_t1 = (d_t + (xlf / cpm) * d_psmlt_amount
            - (xlf * psmlt_amount / (cpm * cpm)) * d_cpm)
    t1 = stages[MELT_STAGE + ".t1"]
    xka_g = stages[MELT_STAGE + ".xka_val_g"]
    d_xka_g = xka_g * (1.5 / t1 - 1.0 / (t1 + 120.0)) * d_t1
    pgmlt_sum = stages[MELT_STAGE + ".pgmlt_sum"]
    pgmlt_term2 = stages[MELT_STAGE + ".pgmlt_term2"]
    d_pgmlt_sum = pgmlt_term2 * d_work2 / work2
    pgmlt_raw = stages[MELT_STAGE + ".pgmlt_raw"]
    d_pgmlt_raw = pgmlt_raw * (d_xka_g / xka_g - d_t1 / (t0 - t1)
                               + d_pgmlt_sum / pgmlt_sum)
    need(cpm_safe == cpm and cpm > QCRMIN, why + " applied cpm clamp inactive")
    exact(xlf, THERMAL_XLF_D1, why + " D1 melt latent heat")
    return {
        "d_temperature": d_t,
        "d_qv": d_qv,
        "d_cpm": d_cpm,
        "d_work2": d_work2,
        "d_psmlt_sum": d_psmlt_sum,
        "d_psmlt_raw": d_psmlt_raw,
        "d_psmlt_capped_g": d_psmlt_amount,
        "d_psmlt": d_psmlt_rate,
        "d_t1": d_t1,
        "d_pgmlt_sum": d_pgmlt_sum,
        "d_pgmlt_raw": d_pgmlt_raw,
        "d_pgmlt": d_pgmlt_raw,
    }


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


def precg2_values(values: dict, why: str) -> dict[str, float | int | bool]:
    active = values[PRECG2_STAGE + ".active"]
    active_value = active is True or (isinstance(active, (int, float)) and active == 1.0)
    midpoint_trace = values[PRECG2_STAGE + ".midpoint_trace"]
    avtg = values[PRECG2_STAGE + ".avtg"]
    bvtg = values[PRECG2_STAGE + ".bvtg"]
    bvtg2 = values[PRECG2_STAGE + ".bvtg2"]
    g5pbgo2 = values[PRECG2_STAGE + ".g5pbgo2"]
    precg2 = values[PRECG2_STAGE + ".precg2"]
    mug = values[PRECG2_STAGE + ".mug"]
    need(active_value and values[PID_STAGE + ".active"] == active,
         why + " active ProgB gate matches parent")
    need(midpoint_trace == 0.0 and values[PID_STAGE + ".midpoint_trace"] == midpoint_trace,
         why + " midpoint trace disabled and fixed")
    need(mug == 0.0 and avtg > EPS and bvtg2 > EPS,
         why + " active precg2 internal floor branch")
    expected_avtg, expected_bvtg, interpolation_interval = source_order_progb_interpolation(
        values[ENTRY_STAGE + ".rhox"], active_value)
    exact(expected_avtg, avtg, why + " source-order ProgB avtg interpolation")
    exact(expected_bvtg, bvtg, why + " source-order ProgB bvtg interpolation")
    expected_bvtg2 = source_order_bvtg2(bvtg, mug)
    exact(expected_bvtg2, bvtg2, why + " source-order bvtg2")
    expected_g5 = source_order_g5pbgo2(bvtg2)
    g5_ulp = ulp_distance(g5pbgo2, expected_g5)
    need(g5_ulp <= 16, why + " g5pbgo2 gamma within 16 ULP")
    expected_precg2 = source_order_precg2(avtg, g5pbgo2)
    precg2_ulp = ulp_distance(precg2, expected_precg2)
    need(precg2_ulp <= 8, why + " precg2 pow/product within 8 ULP")
    exact(precg2, values[MELT_STAGE + ".precg2"], why + " parent D1 melt precg2 value handoff")
    return {
        "avtg_to_eps_margin": avtg - EPS,
        "bvtg2_to_eps_margin": bvtg2 - EPS,
        "expected_g5pbgo2": expected_g5,
        "g5pbgo2_ulp_distance": g5_ulp,
        "expected_precg2": expected_precg2,
        "precg2_ulp_distance": precg2_ulp,
        "active": active_value,
        "midpoint_trace": midpoint_trace,
        "rhox_interpolation_interval": interpolation_interval,
    }


def precg2_jvp_terms(values: dict, tangent: dict) -> tuple[float, float]:
    precg2 = values[PRECG2_STAGE + ".precg2"]
    avtg = values[PRECG2_STAGE + ".avtg"]
    g5pbgo2 = values[PRECG2_STAGE + ".g5pbgo2"]
    return (
        precg2 * (0.5 * tangent[PRECG2_STAGE + ".avtg"] / avtg),
        precg2 * (tangent[PRECG2_STAGE + ".g5pbgo2"] / g5pbgo2),
    )


def coeres_values(values: dict, why: str) -> dict[str, float | int | bool]:
    qg = values[COERES_STAGE + ".qg"]
    rslope_g = values[COERES_STAGE + ".rslope_g"]
    bvtg = values[COERES_STAGE + ".bvtg"]
    rslopegbmax = values[COERES_STAGE + ".rslopegbmax"]
    graupel_mask = values[COERES_STAGE + ".graupel_mask"]
    rslope2_g = values[COERES_STAGE + ".rslope2_g"]
    rslopeb_g = values[COERES_STAGE + ".rslopeb_g"]
    rslopemu_g = values[COERES_STAGE + ".rslopemu_g"]
    mug = values[COERES_STAGE + ".mug"]
    qcrmin = values[COERES_STAGE + ".qcrmin"]

    need(graupel_mask in (False, True, 0, 1), why + " graupel mask encoding")
    graupel_mask_value = bool(graupel_mask)
    need(graupel_mask_value == (qg <= qcrmin), why + " qg<=qcrmin slope branch")
    need(not graupel_mask_value and qg > qcrmin,
         why + " selected case remains on unmasked graupel slope branch")
    exact(qg, values[ENTRY_STAGE + ".qg"], why + " qg parent value handoff")
    exact(rslope_g, values[ENTRY_STAGE + ".rslope_g"], why + " rslope parent value handoff")
    exact(bvtg, values[PRECG2_STAGE + ".bvtg"], why + " bvtg parent value handoff")
    exact(qcrmin, QCRMIN, why + " configured graupel threshold")
    exact(mug, 0.0, why + " MUG configured zero")
    need(math.isfinite(rslopegbmax) and rslopegbmax > 0.0,
         why + " finite positive masked-branch rslopegbmax input")
    need(rslope_g > EPS, why + " safe_pow input is above EPS")

    exact(rslope2_g, rslope_g * rslope_g, why + " source-order rslope2_g square")
    expected_rslopemu = math.pow(max(rslope_g, EPS), mug)
    exact(rslopemu_g, expected_rslopemu, why + " MUG=0 rslopemu_g")
    expected_rslopeb = source_order_rslopeb_g(rslope_g, bvtg)
    rslopeb_ulp = ulp_distance(rslopeb_g, expected_rslopeb)
    need(rslopeb_ulp <= COERES_RB_ULP_LIMIT,
         why + " rslopeb_g pow within portable ULP bound")

    for field, consumer in (("qg", "qg"),
                            ("rslope_g", "rslope_g"),
                            ("qcrmin", "qcrmin"),
                            ("rslope2_g", "rslope2_g"),
                            ("rslopeb_g", "rslopeb_g"),
                            ("rslopemu_g", "rslopemu_g")):
        exact(values[COERES_STAGE + "." + field], values[MELT_STAGE + "." + consumer],
              why + " coeres input producer-to-melt handoff: " + field)

    sqrt_argument = rslope_g * rslopeb_g
    sqrt_margin = sqrt_argument - qcrmin
    need(sqrt_margin > 0.0, why + " coeres sqrt clamp inactive")
    expected_coeres = source_order_coeres_g(
        rslope2_g, rslope_g, rslopeb_g, rslopemu_g, qcrmin)
    actual_coeres = values[MELT_STAGE + ".coeres_g"]
    coeres_ulp = ulp_distance(actual_coeres, expected_coeres)
    need(coeres_ulp <= COERES_VALUE_ULP_LIMIT,
         why + " source-order coeres_g within portable ULP bound")

    return {
        "qg_branch_margin": qg - qcrmin,
        "sqrt_argument_margin": sqrt_margin,
        "expected_rslopeb_g": expected_rslopeb,
        "rslopeb_g_ulp_distance": rslopeb_ulp,
        "expected_coeres_g": expected_coeres,
        "coeres_g_ulp_distance": coeres_ulp,
        "graupel_mask": graupel_mask_value,
        "rslopemu_g": rslopemu_g,
    }


def coeres_jvp_terms(values: dict, tangent: dict) -> tuple[float, float, float, float]:
    rslope = values[COERES_STAGE + ".rslope_g"]
    rslope2 = values[COERES_STAGE + ".rslope2_g"]
    rslopeb = values[COERES_STAGE + ".rslopeb_g"]
    d_rslope = tangent[COERES_STAGE + ".rslope_g"]
    d_bvtg = tangent[COERES_STAGE + ".bvtg"]
    dr2_expected = 2.0 * rslope * d_rslope
    drb_expected = rslopeb * (values[COERES_STAGE + ".bvtg"] * d_rslope / rslope
                              + math.log(rslope) * d_bvtg)
    coeres = values[MELT_STAGE + ".coeres_g"]
    dcoeres_terms = (
        coeres * dr2_expected / rslope2,
        0.5 * coeres * d_rslope / rslope,
        0.5 * coeres * drb_expected / rslopeb,
    )
    return dr2_expected, drb_expected, 0.0, math.fsum(dcoeres_terms)


def check_coeres_jvp_chain(values: dict, tangent: dict, why: str) -> tuple[float, float, float, float]:
    dr2_expected, drb_expected, drmu_expected, dcoeres_expected = coeres_jvp_terms(values, tangent)
    near_chain(tangent[COERES_STAGE + ".rslope2_g"], dr2_expected,
               (dr2_expected,), why + " square JVP")
    near_chain(tangent[COERES_STAGE + ".rslopeb_g"], drb_expected,
               (drb_expected,), why + " power JVP")
    exact(tangent[COERES_STAGE + ".rslopemu_g"], drmu_expected,
          why + " MUG=0 rslopemu JVP")
    near_chain(tangent[MELT_STAGE + ".coeres_g"], dcoeres_expected,
               (dcoeres_expected,), why + " coeres slope-input JVP chain")
    term2_value = values[MELT_STAGE + ".pgmlt_term2"]
    dterm2_parts = (
        term2_value * tangent[MELT_STAGE + ".precg2"] / values[MELT_STAGE + ".precg2"],
        term2_value * tangent[MELT_STAGE + ".n0go"] / values[MELT_STAGE + ".n0go"],
        term2_value * tangent[MELT_STAGE + ".work2"] / values[MELT_STAGE + ".work2"],
        term2_value * dcoeres_expected / values[MELT_STAGE + ".coeres_g"],
    )
    near_chain(tangent[MELT_STAGE + ".pgmlt_term2"], math.fsum(dterm2_parts), dterm2_parts,
               why + " term2 JVP via independently reconstructed coeres")
    return dr2_expected, drb_expected, drmu_expected, dcoeres_expected


def replay(*, output_override: tuple[bytes, str] | None = None,
           activation_override: tuple[bytes, str] | None = None) -> dict:
    fixed_manifest()
    parent_summary = parent_replay()
    original = (PARENT / "raw/cpp_result.json").read_bytes()
    boundary_original = ACTIVATION_BOUNDARY_PATH.read_bytes()
    provenance(original, boundary_original)
    raw = original if output_override is None else output_override[0]
    if output_override is not None:
        need(sha(raw) == output_override[1], "override SHA")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc_process_graph_cpp_ad.v1", "C++ result schema")
    prior = json.loads((PARENT / "raw/cpp_result.json").read_text())
    boundary_raw = (boundary_original if activation_override is None else activation_override[0])
    if activation_override is not None:
        need(sha(boundary_raw) == activation_override[1], "activation override SHA")
    boundary = json.loads(boundary_raw, parse_constant=reject_json_constant)
    activation_summary = verify_activation_boundary(boundary, data)
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
                | {MELT_STAGE + "." + field for field in MELT_FIELDS}
                | {PRECG2_STAGE + "." + field for field in PRECG2_FIELDS}
                | {COERES_STAGE + "." + field for field in COERES_FIELDS})
    need(set(base["stage_scalars"]) == set(old_base["stage_scalars"]) | new_keys,
         "new D1 coeres stage inventory")
    for key, value in old_base["stage_scalars"].items():
        exact(base["stage_scalars"][key], value, "parent baseline stage: " + key)
        need(base["stage_types"][key] == old_base["stage_types"][key], "parent dtype: " + key)
    order = data["stage_numeric_order"]
    need(order == sorted(k for k, typ in base["stage_types"].items() if typ == "f64")
         and len(order) == 322 and len(base["stage_scalars"]) == 336,
         "D1 coeres producer stage order")
    need(base["stage_types"][PID_STAGE + ".active"] == "bool",
         "D1 entry PID active dtype")
    for field in set(PID_FIELDS) - {"active"}:
        need(base["stage_types"][PID_STAGE + "." + field] == "f64",
             "D1 entry PID field dtype: " + field)
    for field in MELT_FIELDS:
        expected_type = "bool" if field in MELT_BOOL_FIELDS else "f64"
        need(base["stage_types"][MELT_STAGE + "." + field] == expected_type,
             "D1 melt producer field dtype: " + field)
    need(base["stage_types"][PRECG2_STAGE + ".active"] == "bool",
         "D1 precg2 active dtype")
    for field in set(PRECG2_FIELDS) - {"active"}:
        need(base["stage_types"][PRECG2_STAGE + "." + field] == "f64",
             "D1 precg2 field dtype: " + field)
    need(base["stage_types"][COERES_STAGE + ".graupel_mask"] == "bool",
         "D1 coeres graupel mask dtype")
    for field in set(COERES_FIELDS) - {"graupel_mask"}:
        need(base["stage_types"][COERES_STAGE + "." + field] == "f64",
             "D1 coeres field dtype: " + field)
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
        jvp[name] = dict(zip(order, finite_vector(direction["stage_jvp"], 322, "D1 JVP " + name)))
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
    precg2_native_anchor_words = 0
    coeres_native_anchor_words = 0
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
        native_precg2_names = {
            "avtg": ("d1_upstream_producer", "avtg"),
            "bvtg": ("d1_upstream_producer", "bvtg"),
            "precg2": ("d1_melt_producer", "precg2"),
        }
        for field, (native_stage, native_field) in native_precg2_names.items():
            key = PRECG2_STAGE + "." + field
            native_key = native_stage + "." + native_field
            need(rows[native_key]["dtype"] == "f64"
                 and word(values[key]) == rows[native_key]["raw_hex"].zfill(16),
                 "native D1 precg2 anchor word: " + label + "/" + key)
            precg2_native_anchor_words += 1
        native_coeres_names = {
            (PRECG2_STAGE, "bvtg"): ("d1_upstream_producer", "bvtg"),
            (COERES_STAGE, "qg"): ("d1_melt_producer", "qg"),
            (COERES_STAGE, "rslope_g"): ("d1_melt_producer", "rslope_g"),
            (COERES_STAGE, "rslope2_g"): ("d1_melt_producer", "rslope2_g"),
            (COERES_STAGE, "rslopeb_g"): ("d1_melt_producer", "rslopeb_g"),
            (COERES_STAGE, "rslopemu_g"): ("d1_melt_producer", "rslopemu_g"),
            (COERES_STAGE, "qcrmin"): ("d1_melt_producer", "qcrmin"),
            (MELT_STAGE, "coeres_g"): ("d1_melt_producer", "coeres_g"),
        }
        for (stage, field), (native_stage, native_field) in native_coeres_names.items():
            key = stage + "." + field
            native_key = native_stage + "." + native_field
            need(rows[native_key]["dtype"] == "f64"
                 and word(values[key]) == rows[native_key]["raw_hex"].zfill(16),
                 "native D1 coeres input word: " + label + "/" + key)
            coeres_native_anchor_words += 1
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
    minimum_precg2_avtg_floor_margin = math.inf
    minimum_precg2_bvtg2_floor_margin = math.inf
    maximum_precg2_g5_ulp_distance = 0
    maximum_precg2_value_ulp_distance = 0
    precg2_value_rows = []
    minimum_coeres_qg_margin = math.inf
    minimum_coeres_sqrt_margin = math.inf
    maximum_coeres_rb_ulp_distance = 0
    maximum_coeres_value_ulp_distance = 0
    coeres_value_rows = []
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
        coeres_diag = coeres_values(values, label)
        minimum_coeres_qg_margin = min(
            minimum_coeres_qg_margin, float(coeres_diag["qg_branch_margin"]))
        minimum_coeres_sqrt_margin = min(
            minimum_coeres_sqrt_margin, float(coeres_diag["sqrt_argument_margin"]))
        maximum_coeres_rb_ulp_distance = max(
            maximum_coeres_rb_ulp_distance, int(coeres_diag["rslopeb_g_ulp_distance"]))
        maximum_coeres_value_ulp_distance = max(
            maximum_coeres_value_ulp_distance, int(coeres_diag["coeres_g_ulp_distance"]))
        coeres_value_rows.append({"case": label, **coeres_diag})
        precg_diag = precg2_values(values, label)
        minimum_precg2_avtg_floor_margin = min(
            minimum_precg2_avtg_floor_margin, float(precg_diag["avtg_to_eps_margin"]))
        minimum_precg2_bvtg2_floor_margin = min(
            minimum_precg2_bvtg2_floor_margin, float(precg_diag["bvtg2_to_eps_margin"]))
        maximum_precg2_g5_ulp_distance = max(
            maximum_precg2_g5_ulp_distance, int(precg_diag["g5pbgo2_ulp_distance"]))
        maximum_precg2_value_ulp_distance = max(
            maximum_precg2_value_ulp_distance, int(precg_diag["precg2_ulp_distance"]))
        precg2_value_rows.append({"case": label, **precg_diag})
        for field in ("mug", "midpoint_trace"):
            exact(values[PRECG2_STAGE + "." + field],
                  base["stage_scalars"][PRECG2_STAGE + "." + field],
                  "fixed D1 precg2 input across cases: " + label + "/" + field)
        for field in ("mug", "qcrmin"):
            exact(values[COERES_STAGE + "." + field],
                  base["stage_scalars"][COERES_STAGE + "." + field],
                  "fixed D1 coeres parameter across cases: " + label + "/" + field)
        need(values[COERES_STAGE + ".graupel_mask"] in (False, 0),
             "fixed selected D1 coeres branch across cases: " + label)
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
        d_bvtg2 = tangent[PRECG2_STAGE + ".bvtg2"]
        d_bvtg2_terms = (0.5 * tangent[PRECG2_STAGE + ".bvtg"],
                         tangent[PRECG2_STAGE + ".mug"])
        near_roundoff(d_bvtg2, math.fsum(d_bvtg2_terms), d_bvtg2_terms,
                      "D1 precg2 bvtg2 tangent chain: " + name)
        d_precg2 = tangent[PRECG2_STAGE + ".precg2"]
        d_precg2_terms = precg2_jvp_terms(base["stage_scalars"], tangent)
        near_roundoff(d_precg2, math.fsum(d_precg2_terms), d_precg2_terms,
                      "D1 precg2 JVP chain: " + name)
        exact(d_precg2, tangent[MELT_STAGE + ".precg2"],
              "D1 precg2 producer-to-melt tangent handoff: " + name)
        exact(tangent[PRECG2_STAGE + ".mug"], 0.0,
              "fixed D1 precg2 mug tangent: " + name)
        exact(tangent[PRECG2_STAGE + ".midpoint_trace"], 0.0,
              "fixed D1 precg2 midpoint tangent: " + name)
        terms[name].update({
            "dbvtg2_from_bvtg": d_bvtg2_terms[0],
            "dbvtg2_from_mug": d_bvtg2_terms[1],
            "dbvtg2": d_bvtg2,
            "dprecg2_from_avtg": d_precg2_terms[0],
            "dprecg2_from_g5pbgo2": d_precg2_terms[1],
            "dprecg2": d_precg2,
        })
        for stage_field, melt_field in (("qg", "qg"),
                                        ("rslope_g", "rslope_g"),
                                        ("qcrmin", "qcrmin"),
                                        ("rslope2_g", "rslope2_g"),
                                        ("rslopeb_g", "rslopeb_g"),
                                        ("rslopemu_g", "rslopemu_g")):
            exact(tangent[COERES_STAGE + "." + stage_field],
                  tangent[MELT_STAGE + "." + melt_field],
                  "D1 coeres input tangent handoff: " + name + "/" + stage_field)
        for field in ("mug", "qcrmin"):
            exact(tangent[COERES_STAGE + "." + field], 0.0,
                  "fixed D1 coeres parameter tangent: " + name + "/" + field)
        exact(tangent[COERES_STAGE + ".rslope_g"], tangent[ENTRY_STAGE + ".rslope_g"],
              "D1 coeres rslope_g entry tangent handoff: " + name)
        exact(tangent[COERES_STAGE + ".bvtg"], tangent[PRECG2_STAGE + ".bvtg"],
              "D1 coeres bvtg entry tangent handoff: " + name)
        dr2_expected, drb_expected, drmu_expected, dcoeres_expected = check_coeres_jvp_chain(
            base["stage_scalars"], tangent, "D1 coeres " + name)
        terms[name].update({
            "drslope2_g": dr2_expected,
            "drslopeb_g": drb_expected,
            "drslopemu_g": drmu_expected,
            "dcoeres_from_entry_slopes": dcoeres_expected,
            "dpgmlt_term2_from_entry_coeres": (
                base["stage_scalars"][MELT_STAGE + ".pgmlt_term2"] * dcoeres_expected
                / base["stage_scalars"][MELT_STAGE + ".coeres_g"]),
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
    max_precg2_fd_relative_error = max_precg2_one_sided_relative_error = 0.0
    max_precg2_fd_residual_ulp = max_precg2_one_sided_residual_ulp = 0.0
    max_coeres_fd_relative_error = max_coeres_one_sided_relative_error = 0.0
    max_coeres_slope_fd_relative_error = 0.0
    max_parent_coeres_fd_recheck_relative_error = 0.0
    fd_resolved_signals = fd_unresolved_zero_signals = 0
    entry_fd_resolved_signals = entry_fd_rounding_floor_cases = 0
    entry_one_sided_rounding_floor_cases = 0
    pid_fd_resolved_signals = pid_fd_rounding_floor_cases = 0
    pid_one_sided_rounding_floor_cases = 0
    precg2_fd_resolved_signals = precg2_fd_rounding_floor_cases = 0
    precg2_one_sided_rounding_floor_cases = 0
    coeres_fd_resolved_signals = 0
    coeres_new_slope_fd_signal_count = 0
    coeres_parent_fd_recheck_count = 0
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
            for field in (*SIGNALS, *ENTRY_SIGNALS, *PID_SIGNALS, *PRECG2_SIGNALS, *COERES_SIGNALS):
                observed = pair["high_stages"][field] - pair["low_stages"][field]
                predicted = jvp["qg17_relative"][field] * dq + jvp["brs17_relative"][field] * db
                baseline = base["stage_scalars"][field]
                threshold = 32 * math.ulp(baseline)
                is_entry_signal = field in ENTRY_SIGNALS
                is_pid_signal = field in PID_SIGNALS
                is_precg2_signal = field in PRECG2_SIGNALS
                is_coeres_signal = field in COERES_SIGNALS
                is_new_signal = is_entry_signal or is_pid_signal or is_precg2_signal or is_coeres_signal
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
                    elif is_precg2_signal:
                        precg2_fd_resolved_signals += 1
                    if is_coeres_signal:
                        need(error < 1e-6,
                             "D1 coeres FD signal derivative: " + name + "/" + h + "/" + field)
                    else:
                        bound = max(1e-6 * scale, 4 * math.ulp(baseline))
                        need(residual <= bound,
                             "D1 producer FD signal derivative: " + name + "/" + h + "/" + field)
                    if residual > 1e-6 * scale and not is_coeres_signal:
                        if is_entry_signal:
                            entry_fd_rounding_floor_cases += 1
                        elif is_pid_signal:
                            pid_fd_rounding_floor_cases += 1
                        elif is_precg2_signal:
                            precg2_fd_rounding_floor_cases += 1
                    if is_pid_signal:
                        pid_fd_resolved_signals += 1
                        max_pid_fd_relative_error = max(max_pid_fd_relative_error, error)
                    elif is_precg2_signal:
                        max_precg2_fd_relative_error = max(max_precg2_fd_relative_error, error)
                        max_precg2_fd_residual_ulp = max(
                            max_precg2_fd_residual_ulp, residual / math.ulp(baseline))
                    elif is_coeres_signal:
                        coeres_fd_resolved_signals += 1
                        max_coeres_fd_relative_error = max(max_coeres_fd_relative_error, error)
                        if field == MELT_STAGE + ".coeres_g":
                            coeres_parent_fd_recheck_count += 1
                            max_parent_coeres_fd_recheck_relative_error = max(
                                max_parent_coeres_fd_recheck_relative_error, error)
                        else:
                            coeres_new_slope_fd_signal_count += 1
                            max_coeres_slope_fd_relative_error = max(
                                max_coeres_slope_fd_relative_error, error)
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
                        if is_coeres_signal:
                            need(one_error < 4 * float(h),
                                 "D1 coeres one-sided FD: " + name + "/" + h + "/" + field)
                        else:
                            one_bound = max(4 * float(h) * one_scale, 4 * math.ulp(baseline))
                            need(one_residual <= one_bound,
                                 "D1 producer one-sided FD: " + name + "/" + h + "/" + field)
                        if one_residual > 4 * float(h) * one_scale:
                            if is_entry_signal:
                                entry_one_sided_rounding_floor_cases += 1
                            elif is_pid_signal:
                                pid_one_sided_rounding_floor_cases += 1
                            elif is_precg2_signal:
                                precg2_one_sided_rounding_floor_cases += 1
                        if is_pid_signal:
                            max_pid_one_sided_relative_error = max(
                                max_pid_one_sided_relative_error, one_error)
                        elif is_precg2_signal:
                            max_precg2_one_sided_relative_error = max(
                                max_precg2_one_sided_relative_error, one_error)
                            max_precg2_one_sided_residual_ulp = max(
                                max_precg2_one_sided_residual_ulp,
                                one_residual / math.ulp(baseline))
                        elif is_coeres_signal:
                            max_coeres_one_sided_relative_error = max(
                                max_coeres_one_sided_relative_error, one_error)
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
    thermal_summary = verify_thermal_payload(data, prior, order)
    return {
        "schema": "kdm6.native_activation_upper_boundary_cpp_ad_replay.v1",
        "selected_cases": len(all_cases),
        "parent_stage_fields": len(NEW_FIELDS),
        "parent_gfac_stage_fields": len(GFAC_FIELDS),
        "parent_entry_slope_stage_fields": len(ENTRY_FIELDS),
        "new_entry_pid_stage_fields": len(PID_FIELDS),
        "new_entry_precg2_stage_fields": len(PRECG2_FIELDS),
        "new_entry_coeres_stage_fields": len(COERES_FIELDS),
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
        "native_d1_precg2_anchor_words_raw_equal": precg2_native_anchor_words,
        "native_d1_coeres_anchor_words_raw_equal": coeres_native_anchor_words,
        "coeres_native_anchor_scope": (
            "#553 baseline and joint ±1e-3 words for bvtg plus D1 consumer qg, "
            "rslope_g, rslope2_g, rslopeb_g, rslopemu_g, qcrmin, and coeres_g"
        ),
        "precg2_native_anchor_scope": (
            "#553 PRE2 anchors avtg, bvtg, precg2 at baseline and joint ±1e-3; "
            "bvtg2 and g5pbgo2 have no independent native word tap"
        ),
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
            "compiled_parent_melt_source_sha256": sha(MELT_SOURCE_PACKET.read_bytes()),
        },
        "native_amount_and_factor_handoffs_raw_equal": producer_words,
        "numeric_stage_tangents_per_direction": len(order),
        "entry_pid_source_order_cases": len(all_cases),
        "entry_cmg_source_order_cases": len(all_cases),
        "entry_pidn0g_parent_value_handoff_cases": len(all_cases),
        "entry_pidn0g_parent_jvp_handoff_directions": len(DIRECTIONS),
        "precg2_source_order_cases": len(all_cases),
        "precg2_interpolation_source_order_cases": len(all_cases),
        "precg2_source_expressions": {
            "avtg_bvtg": (
                "searchsorted-right density-table interval; aTbl_left + "
                "((rhox-Tbl_left)*(aTbl_right-aTbl_left))*(1/(Tbl_right-Tbl_left)); "
                "same operation order for bvtg"
            ),
            "bvtg2": "(2.5 + bvtg * 0.5) + mug",
            "g5pbgo2": "exp(lgamma(max(bvtg2, 1e-15)))",
            "precg2": "((4.0 * 0.31) * pow(max(avtg, 1e-15), 0.5)) * g5pbgo2",
        },
        "precg2_source_order_g5_max_ulp_distance": maximum_precg2_g5_ulp_distance,
        "precg2_source_order_value_max_ulp_distance": maximum_precg2_value_ulp_distance,
        "precg2_floor_margins": {
            "minimum_avtg_minus_eps": minimum_precg2_avtg_floor_margin,
            "minimum_bvtg2_minus_eps": minimum_precg2_bvtg2_floor_margin,
        },
        "precg2_source_order_checks": precg2_value_rows,
        "precg2_parent_value_handoff_cases": len(all_cases),
        "precg2_parent_jvp_handoff_directions": len(DIRECTIONS),
        "precg2_fd_resolved_signal_count": precg2_fd_resolved_signals,
        "precg2_fd_rounding_floor_cases": precg2_fd_rounding_floor_cases,
        "precg2_one_sided_rounding_floor_cases": precg2_one_sided_rounding_floor_cases,
        "max_precg2_fd_residual_ulp": max_precg2_fd_residual_ulp,
        "max_precg2_one_sided_residual_ulp": max_precg2_one_sided_residual_ulp,
        "max_precg2_fd_relative_error": max_precg2_fd_relative_error,
        "max_precg2_one_sided_relative_error": max_precg2_one_sided_relative_error,
        "coeres_source_order_cases": len(all_cases),
        "coeres_slope_parameter_words": {
            "mug": base["stage_scalars"][COERES_STAGE + ".mug"],
            "qcrmin": base["stage_scalars"][COERES_STAGE + ".qcrmin"],
            "rslopegbmax": base["stage_scalars"][COERES_STAGE + ".rslopegbmax"],
        },
        "coeres_source_expressions": {
            "graupel_mask": "qg <= qcrmin",
            "rslope2_g": "rslope_g * rslope_g (selected unmasked branch)",
            "rslopeb_g": "pow(max(rslope_g, 1e-15), bvtg) (selected unmasked branch)",
            "rslopemu_g": "pow(max(rslope_g, 1e-15), mug); mug=0 gives 1",
            "coeres_g": "(rslope2_g * sqrt(max(rslope_g * rslopeb_g, qcrmin))) * rslopemu_g",
        },
        "coeres_slope_source_order_checks": coeres_value_rows,
        "coeres_minimum_branch_margins": {
            "qg_minus_qcrmin": minimum_coeres_qg_margin,
            "rslope_g_times_rslopeb_g_minus_qcrmin": minimum_coeres_sqrt_margin,
        },
        "coeres_rslopeb_g_max_ulp_distance": maximum_coeres_rb_ulp_distance,
        "coeres_value_max_ulp_distance": maximum_coeres_value_ulp_distance,
        "coeres_input_handoff_cases": len(all_cases),
        "coeres_input_tangent_handoff_directions": len(DIRECTIONS),
        "coeres_term2_tangent_chain_directions": len(DIRECTIONS),
        "coeres_fd_resolved_signal_count": coeres_fd_resolved_signals,
        "coeres_new_slope_fd_signal_count": coeres_new_slope_fd_signal_count,
        "coeres_parent_fd_recheck_count": coeres_parent_fd_recheck_count,
        "max_coeres_fd_relative_error": max_coeres_fd_relative_error,
        "max_coeres_slope_fd_relative_error": max_coeres_slope_fd_relative_error,
        "max_parent_coeres_fd_recheck_relative_error": max_parent_coeres_fd_recheck_relative_error,
        "max_coeres_one_sided_relative_error": max_coeres_one_sided_relative_error,
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
        **thermal_summary,
        **activation_summary,
    }


def main() -> None:
    print("verified native activation upper-bound bracket replay: "
          + json.dumps(replay(), sort_keys=True))


if __name__ == "__main__":
    main()
