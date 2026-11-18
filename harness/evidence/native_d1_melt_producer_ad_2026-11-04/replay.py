#!/usr/bin/env python3
"""Pinned active native D1 snow/graupel producer replay and local AD."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
import sys

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from oracle.kdm6.thermo import compute_cpm, default_thermo_params  # noqa: E402


PARENT = REPO / "harness/evidence/native_qi_applied_d1_active_2026-11-04"
PD1_QI = REPO / "harness/evidence/native_qnice_d1_qi_2026-11-03"
PD1_AD = REPO / "harness/evidence/native_qnice_d1_ad_2026-11-03"
P39 = REPO / "harness/evidence/native_qnice_39_applied_2026-11-03"
PARENT_SOURCE_SHA = "e6d25eb51934f5448ad296bc9839a5dfea500deb52d5ae1593689f2806715775"
PD1_AD_RECEIPT_SHA = "54fcb88c3482070bde43bb6220b5a009f27a3a5dcc749fa90824f8eae27bc13c"
CAPTURE = "raw/native_qnice_applied_39515_runtime2.csv"
ORDER_SHA = "63e01a3a6e6833afce60ca33b0b3391bb1db6aade31f0d2f50bee3603377655c"
ORACLE_THERMO_SHA = "5278c14c6d87178af5ee963eef59d3297b923fa374412fd854c01e43ffb1b5cd"
PINS = {
    "raw/build_receipt.json": "f7d165f8daeb5c38517c951ee575f0426caf3c3d9cd5b966668948afbe027e0d",
    CAPTURE: "f38375e459564980bcce0ea217d03a9cd25be4e5f187d6bab7198a2ba8900f71",
    "raw/off_live_session.json": "cedea5d07ad27a04f8c42fbf61fb26e86feb95c80bf76fcd36fea5f3c7a18c7f",
    "raw/off_run_result.json": "f67c15d5430137f58165a9cd91765d6918141bc94128cb0222a3bb04d9f6b5f7",
    "raw/on_live_session.json": "f41a985910411e82a4d83654a702eda5a82463019b79bd90995a5e4642ed2d51",
    "raw/on_run_result.json": "1776c7a07e03f756d2df77c89e18a2c6f46a105a2a7ac05c207cafd792984174",
    "executed_cpp/melt_freeze.cpp": "737198615eb14990e0d322af6ba5b5983d4265909dffa3a1a3e8d5687f83f137",
    "producer/d1_producer_capture_block.txt": "01e57b2749ccab9c7c0e0e196ea8f3e976d6a693a897a39f523a3aac9e55041a",
    "producer/run.py.txt": "99c2772205023cbbdea7e02c103409de5f510c1b42952ae57e1f389f36048f0b",
    "results.json": "3c87f60154c0c71fbbe70c490d408e2945ad80731a271f6a7b22f457686f7ada",
}
K = 39
TARGET = K - 16
STAGE = "d1_melt_producer"
BOOL_FIELDS = {"warm", "snow_active", "graupel_active"}
CAPTURE_FIELDS = (
    "qs",
    "qg",
    "qi",
    "ni",
    "t",
    "p",
    "den",
    "mass_den",
    "rhox",
    "cpm",
    "n0so",
    "n0go",
    "n0sfac",
    "work2",
    "precg2",
    "rslope_s",
    "rslope2_s",
    "rslopeb_s",
    "rslopemu_s",
    "rslope_g",
    "rslope2_g",
    "rslopeb_g",
    "rslopemu_g",
    "precs1",
    "precs2",
    "precg1",
    "xlf",
    "t0c",
    "qcrmin",
    "dtcld",
    "warm",
    "snow_active",
    "graupel_active",
    "den_safe",
    "xka_val",
    "coeres_s",
    "psmlt_term1",
    "psmlt_term2",
    "psmlt_sum",
    "psmlt_raw",
    "psmlt_dt",
    "psmlt_capped",
    "psmlt_capped_g",
    "psmlt",
    "t1",
    "xka_val_g",
    "coeres_g",
    "pgmlt_term1",
    "pgmlt_term2",
    "pgmlt_sum",
    "pgmlt_raw",
    "pgmlt_dt",
    "pgmlt_capped",
    "pgmlt_capped_g",
    "pgmlt",
)
DERIVED = (
    "den_safe",
    "xka_val",
    "coeres_s",
    "psmlt_term1",
    "psmlt_term2",
    "psmlt_sum",
    "psmlt_raw",
    "psmlt_dt",
    "psmlt_capped",
    "psmlt_capped_g",
    "psmlt",
    "t1",
    "xka_val_g",
    "coeres_g",
    "pgmlt_term1",
    "pgmlt_term2",
    "pgmlt_sum",
    "pgmlt_raw",
    "pgmlt_dt",
    "pgmlt_capped",
    "pgmlt_capped_g",
    "pgmlt",
)
AD_OUTPUTS = (
    "psmlt_raw",
    "psmlt_dt",
    "psmlt_capped_g",
    "t1",
    "pgmlt_raw",
    "pgmlt_dt",
    "pgmlt_capped_g",
    "D1_T_out",
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == PINS[name], "packet SHA-256: " + name)
    return raw


def module(path: Path, expected: str, name: str):
    need(sha(path.read_bytes()) == expected, "parent replay source: " + name)
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, "parent import: " + name)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def f64(raw_hex: str) -> float:
    value = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(value), "nonfinite captured f64")
    return value


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def load_capture(raw: bytes, parent, p39, old_fields: dict) -> dict:
    need(len(raw) <= 2 << 20 and raw.endswith(b"\n"), "producer capture byte bound")
    lines = raw.decode("ascii").splitlines()
    need(
        len(lines) == 6634
        and lines[0] == p39.NATIVE_HEADER
        and lines[1] == p39.NATIVE_META[0]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=27945; K=39; max_rows=7000; max_bytes=2097152"
        and lines[-1] == "# native_rows=6630,status=complete",
        "producer capture header/footer",
    )
    reader = csv.DictReader(io.StringIO("\n".join([lines[0], *lines[3:-1]])))
    need(
        reader.fieldnames == p39.NATIVE_HEADER.split(","),
        "producer capture CSV columns",
    )
    source_names = [
        m.decode()
        for m in __import__("re").findall(
            rb'record\("([^"]+)"', pinned("producer/d1_producer_capture_block.txt")
        )
    ]
    need(
        tuple(source_names) == CAPTURE_FIELDS and len(CAPTURE_FIELDS) == 55,
        "producer source/field inventory",
    )
    expected = set(old_fields) | {
        (STAGE, name, k) for name in CAPTURE_FIELDS for k in range(K)
    }
    ordered_stages = list(p39.STAGES)
    ordered_stages.insert(ordered_stages.index("c3_pre_mf_d1"), STAGE)
    fields = {}
    stages = []
    order = []
    for row in reader:
        need(
            set(row) == set(reader.fieldnames) and None not in row.values(),
            "producer row shape",
        )
        need(
            (
                row["one_step_call"],
                row["runtime_call"],
                row["b_zero"],
                row["B"],
                row["K"],
            )
            == ("2", "2", "27945", "32248", "39"),
            "producer call/tile identity",
        )
        try:
            k = int(row["k_zero"])
            bits = int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("producer level/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < K
            and row["k_zero"] == str(k)
            and key in expected
            and key not in fields,
            "producer level/field uniqueness",
        )
        need(
            row["substep"] == ("1" if row["stage"] == parent.SED else "0"),
            "producer substep",
        )
        dtype = (
            "bool"
            if (row["stage"], row["field"]) in p39.BOOL_FIELDS
            or (row["stage"] == STAGE and row["field"] in BOOL_FIELDS)
            else "f64"
        )
        need(
            row["dtype"] == dtype
            and row["raw_hex"] == format(bits, "x")
            and bits < (2 if dtype == "bool" else 1 << 64),
            "producer dtype/raw word",
        )
        if dtype == "f64":
            f64(row["raw_hex"])
        fields[key] = row
        if not stages or stages[-1] != row["stage"]:
            stages.append(row["stage"])
        order.append(
            "|".join(
                row[c]
                for c in (
                    "one_step_call",
                    "runtime_call",
                    "substep",
                    "b_zero",
                    "k_zero",
                    "stage",
                    "field",
                    "dtype",
                )
            )
        )
    need(
        len(fields) == 6630 and set(fields) == expected and stages == ordered_stages,
        "producer complete stage/level inventory",
    )
    need(sha(("\n".join(order) + "\n").encode()) == ORDER_SHA, "producer row order")
    for key, prior in old_fields.items():
        need(
            (fields[key]["dtype"], fields[key]["raw_hex"])
            == (prior["dtype"], prior["raw_hex"]),
            "parent 4485 raw words",
        )
    return fields


def get(fields: dict, stage: str, name: str, k: int) -> float:
    return f64(fields[(stage, name, k)]["raw_hex"])


def check(fields: dict, stage: str, name: str, k: int, value: float, why: str) -> None:
    need(fields[(stage, name, k)]["raw_hex"] == word(value), why)


def provenance(parent, p39) -> dict:
    receipt = json.loads(pinned("raw/build_receipt.json"))
    need(
        receipt["schema"] == "kdm6.native_d1_melt_producer_cpp_build.v1"
        and receipt["candidate"]
        == {
            "native_ij_1based": [203, 149],
            "native_level_1based": 16,
            "B": 32248,
            "b_zero": 27945,
            "runtime_call": 2,
            "one_step_call": 2,
        },
        "producer build/call schema",
    )
    parent_receipt_raw = parent.pinned("raw/build_receipt.json")
    parent_receipt = json.loads(parent_receipt_raw)
    need(
        sha(parent_receipt_raw) == receipt["parent_build_receipt_sha256"],
        "producer parent build receipt",
    )
    need(
        receipt["only_source_change_vs_parent"] == ["src/melt_freeze.cpp"],
        "producer source change scope",
    )
    old = (PD1_QI / "executed_cpp/melt_freeze.cpp").read_bytes()
    need(
        sha(old) == "049e3327a277f0342d80767ea5bb48b0f56fa7e1fbdd412b4f508db976d9d4da",
        "parent melt producer source",
    )
    new = pinned("executed_cpp/melt_freeze.cpp")
    block = pinned("producer/d1_producer_capture_block.txt")
    include = b'#include "kdm6/coordinator.h"  // selected-column, value-only native D1 capture\n'
    need(
        new.count(include) == 1
        and new.count(block) == 1
        and new.replace(include, b"", 1).replace(block, b"", 1) == old,
        "D1 producer capture-only overlay",
    )
    need(
        sha(new) == receipt["source_sha256"]["melt_freeze.cpp"], "executed melt source"
    )
    for name in ("sedimentation_conservative.cpp", "coordinator.cpp", "runtime.cpp"):
        need(
            receipt["source_sha256"][name] == parent_receipt["source_sha256"][name],
            "unchanged producer source: " + name,
        )
    need(
        receipt["parent_dso_sha256"] == parent_receipt["new_dso_sha256"]
        and receipt["new_executable_sha256"] == parent_receipt["new_executable_sha256"],
        "producer parent DSO/executable",
    )
    old_d1_receipt_raw = (PD1_AD / "raw/build_receipt.json").read_bytes()
    need(sha(old_d1_receipt_raw) == PD1_AD_RECEIPT_SHA, "parent D1 header receipt")
    old_receipt = json.loads(old_d1_receipt_raw)
    for name in ("constants.h", "melt_freeze.h", "ops.h"):
        need(
            receipt["source_headers_sha256"][name]
            == old_receipt["source_headers_sha256"][name + ".txt"],
            "producer header: " + name,
        )
    old_co = (P39 / "executed_cpp/coordinator.h").read_bytes()
    need(
        sha(old_co)
        == p39.PINS["executed_cpp/coordinator.h"]
        == receipt["source_headers_sha256"]["coordinator.h"],
        "capture API header",
    )
    need("-ffp-contract=off" in receipt["cxx_flags"], "producer C++ FP contraction")
    pinned("producer/run.py.txt")
    need(
        receipt["producer_runner_sha256"] == PINS["producer/run.py.txt"]
        and receipt["capture_block_sha256"]
        == PINS["producer/d1_producer_capture_block.txt"],
        "producer runner/capture pins",
    )
    for mode in ("off", "on"):
        run = json.loads(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = json.loads(session_raw)
        need(
            run["schema"] == "kdm6.native_d1_producer_run.v1" and run["mode"] == mode,
            "producer run schema/mode",
        )
        need(run["session_record_sha256"] == sha(session_raw), "producer run/session")
        need(
            run["source_sha256"] == receipt["source_sha256"]
            and all(
                run["object_sha256"][n] == receipt["object_sha256"][n]
                for n in run["object_sha256"]
            ),
            "producer source/object pins",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == receipt["new_executable_sha256"]
            and run["dso_sha256"]
            == session["library_candidate_sha256"]
            == receipt["new_dso_sha256"],
            "producer executable/DSO pins",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True
            and session["dt_seconds"] == 20
            and session["steps"] == 1,
            "completed one-step producer run",
        )
        need(
            any(
                "/native_d1_producer_20261104/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in s
                for s in session["loaded_library_lines"]
            ),
            "loaded producer DSO",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"
            and run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "same input and off/on/prior endpoint",
        )
        if mode == "off":
            need(run["captures"] == {}, "producer off capture")
        else:
            need(
                run["captures"]
                == {"native_qnice_applied_39515_runtime2.csv": PINS[CAPTURE]},
                "producer on capture hash",
            )
    return {
        "executable_sha256": receipt["new_executable_sha256"],
        "dso_sha256": receipt["new_dso_sha256"],
        "endpoint_sha256": "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "capture_sha256": PINS[CAPTURE],
    }


def xka_scalar(t: float, den: float) -> float:
    safe = max(t, 1.0)
    viscos = 1.496e-6 * (safe * math.sqrt(safe)) / (safe + 120.0) / den
    return 1.414e3 * viscos * den


def scalar_producer(
    fields: dict, k: int, *, qv: float | None = None, temperature: float | None = None
) -> dict:
    def x(name: str) -> float:
        return get(fields, STAGE, name, k)

    t = x("t") if temperature is None else temperature
    qmin, xlf, t0, dt = (x(name) for name in ("qcrmin", "xlf", "t0c", "dtcld"))
    cpm = (
        x("cpm")
        if qv is None
        else 1004.5 * (1.0 - max(qv, 1e-15)) + max(qv, 1e-15) * 1846.4
    )
    warm = t > t0
    snow_active = warm and x("qs") > 0.0
    graupel_active = warm and x("qg") > 0.0
    den_safe = max(x("mass_den"), qmin)
    xka0 = xka_scalar(t, x("den"))
    coeres_s = (
        x("rslope2_s") * math.sqrt(max(x("rslope_s") * x("rslopeb_s"), qmin))
    ) * x("rslopemu_s")
    ps1 = ((x("precs1") * x("n0so")) * x("rslope2_s")) * x("rslopemu_s")
    ps2 = ((x("precs2") * x("n0so")) * x("work2")) * coeres_s
    ps_sum = ps1 + ps2
    ps_raw = (
        ((((xka0 / xlf) * (t0 - t)) * x("n0sfac")) * math.pi / 2.0) * ps_sum
    ) / den_safe
    ps_dt = ps_raw * dt
    ps_cap = min(max(ps_dt, -x("qs")), 0.0)
    ps = ps_cap if snow_active else 0.0
    t1 = t + (xlf / cpm) * ps
    xkag = xka_scalar(t1, x("den"))
    coeres_g = (
        x("rslope2_g") * math.sqrt(max(x("rslope_g") * x("rslopeb_g"), qmin))
    ) * x("rslopemu_g")
    pg1 = ((x("precg1") * x("n0go")) * x("rslope2_g")) * x("rslopemu_g")
    pg2 = ((x("precg2") * x("n0go")) * x("work2")) * coeres_g
    pg_sum = pg1 + pg2
    pg_raw = ((((xkag / xlf) * (t0 - t1)) * math.pi / 2.0) * pg_sum) / den_safe
    pg_dt = pg_raw * dt
    pg_cap = min(max(pg_dt, -x("qg")), 0.0)
    pg = pg_cap if graupel_active else 0.0
    melt_q = x("qi") if warm and x("qi") > 0.0 else 0.0
    coef = xlf / max(cpm, qmin)
    tout = ((t + coef * ps) + coef * pg) - coef * melt_q
    return {
        "warm": warm,
        "snow_active": snow_active,
        "graupel_active": graupel_active,
        "den_safe": den_safe,
        "xka_val": xka0,
        "coeres_s": coeres_s,
        "psmlt_term1": ps1,
        "psmlt_term2": ps2,
        "psmlt_sum": ps_sum,
        "psmlt_raw": ps_raw,
        "psmlt_dt": ps_dt,
        "psmlt_capped": ps_cap,
        "psmlt_capped_g": ps,
        "psmlt": ps / dt,
        "t1": t1,
        "xka_val_g": xkag,
        "coeres_g": coeres_g,
        "pgmlt_term1": pg1,
        "pgmlt_term2": pg2,
        "pgmlt_sum": pg_sum,
        "pgmlt_raw": pg_raw,
        "pgmlt_dt": pg_dt,
        "pgmlt_capped": pg_cap,
        "pgmlt_capped_g": pg,
        "pgmlt": pg / dt,
        "D1_T_out": tout,
        "cpm_from_qv": cpm,
    }


def baseline_producer(fields: dict) -> dict:
    nonzero_snow = []
    nonzero_graupel = []
    for k in range(K):
        calc = scalar_producer(fields, k)
        for name in BOOL_FIELDS:
            need(
                int(fields[(STAGE, name, k)]["raw_hex"], 16) == int(calc[name]),
                "D1 producer gate: " + name,
            )
        for name in DERIVED:
            check(
                fields, STAGE, name, k, calc[name], "D1 producer source-order: " + name
            )
        for left, right in (
            ("qi", "qi_before"),
            ("ni", "ni_before"),
            ("t", "t_before"),
            ("cpm", "pre_cpm"),
        ):
            need(
                fields[(STAGE, left, k)]["raw_hex"]
                == fields[("c3_pre_mf_d1", right, k)]["raw_hex"],
                "D1 producer/consumer raw handoff: " + left,
            )
        for left, right in (
            ("psmlt_capped_g", "psmlt_capped"),
            ("pgmlt_capped_g", "pgmlt_capped"),
        ):
            need(
                fields[(STAGE, left, k)]["raw_hex"]
                == fields[("c3_pre_mf_d1", right, k)]["raw_hex"],
                "D1 applied amount handoff: " + left,
            )
        check(
            fields,
            "c3_pre_mf_d1",
            "t_after_d1",
            k,
            calc["D1_T_out"],
            "D1 sequential producer-to-temperature store",
        )
        if calc["psmlt_capped_g"] != 0:
            nonzero_snow.append(K - k)
        if calc["pgmlt_capped_g"] != 0:
            nonzero_graupel.append(K - k)
    target = scalar_producer(fields, TARGET)

    def x(name: str) -> float:
        return get(fields, STAGE, name, TARGET)

    need(
        target["warm"]
        and target["snow_active"]
        and target["graupel_active"]
        and -x("qs") < target["psmlt_dt"] < 0.0
        and -x("qg") < target["pgmlt_dt"] < 0.0
        and target["t1"] > x("t0c"),
        "native16 strict active raw-rate cap branches",
    )
    parallel_pg_raw = (
        (
            ((xka_scalar(x("t"), x("den")) / x("xlf")) * (x("t0c") - x("t")))
            * math.pi
            / 2.0
        )
        * target["pgmlt_sum"]
    ) / target["den_safe"]
    need(
        word(parallel_pg_raw) != fields[(STAGE, "pgmlt_raw", TARGET)]["raw_hex"],
        "sequential snow-heated graupel producer differs from entry-T counterfactual",
    )
    return {
        "raw_bit_replayed_levels": K,
        "source_order_derived_fields": list(DERIVED),
        "nonzero_snow_melt_native_levels": sorted(nonzero_snow),
        "nonzero_graupel_melt_native_levels": sorted(nonzero_graupel),
        "native16": {
            name: x(name)
            for name in (
                "qs",
                "qg",
                "qi",
                "t",
                "cpm",
                "psmlt_raw",
                "psmlt_dt",
                "psmlt_capped_g",
                "t1",
                "pgmlt_raw",
                "pgmlt_dt",
                "pgmlt_capped_g",
            )
        },
        "native16_snow_available_margin": target["psmlt_dt"] + x("qs"),
        "native16_graupel_available_margin": target["pgmlt_dt"] + x("qg"),
        "native16_parallel_entry_T_pgmlt_raw": parallel_pg_raw,
        "native16_sequential_minus_parallel_pgmlt_raw": target["pgmlt_raw"]
        - parallel_pg_raw,
    }


def torch_xka(t: torch.Tensor, den: torch.Tensor) -> torch.Tensor:
    safe = torch.clamp(t, min=1.0)
    viscos = 1.496e-6 * (safe * torch.sqrt(safe)) / (safe + 120.0) / den
    return 1.414e3 * viscos * den


def torch_producer(base: dict, qv: torch.Tensor, t: torch.Tensor) -> tuple:
    """Differentiable, source-ordered f64 mass producer on the selected cell."""
    x = base.__getitem__
    qmin = x("qcrmin")
    xlf = x("xlf")
    t0 = x("t0c")
    dt = x("dtcld")
    cpm = compute_cpm(qv, params=default_thermo_params())
    zero = torch.zeros_like(x("qs"))
    warm = t > t0
    snow_active = warm & (x("qs") > 0.0)
    graupel_active = warm & (x("qg") > 0.0)
    den_safe = torch.clamp(x("mass_den"), min=qmin)
    xka0 = torch_xka(t, x("den"))
    coeres_s = (
        x("rslope2_s")
        * torch.sqrt(torch.clamp(x("rslope_s") * x("rslopeb_s"), min=qmin))
    ) * x("rslopemu_s")
    ps1 = (x("precs1") * x("n0so") * x("rslope2_s")) * x("rslopemu_s")
    ps2 = (x("precs2") * x("n0so") * x("work2")) * coeres_s
    ps_sum = ps1 + ps2
    ps_raw = (xka0 / xlf * (t0 - t) * x("n0sfac") * math.pi / 2.0) * ps_sum / den_safe
    ps_dt = ps_raw * dt
    ps_cap = torch.minimum(torch.maximum(ps_dt, -x("qs")), zero)
    ps = torch.where(snow_active, ps_cap, zero)
    t1 = t + (xlf / cpm) * ps
    xkag = torch_xka(t1, x("den"))
    coeres_g = (
        x("rslope2_g")
        * torch.sqrt(torch.clamp(x("rslope_g") * x("rslopeb_g"), min=qmin))
    ) * x("rslopemu_g")
    pg1 = (x("precg1") * x("n0go") * x("rslope2_g")) * x("rslopemu_g")
    pg2 = (x("precg2") * x("n0go") * x("work2")) * coeres_g
    pg_sum = pg1 + pg2
    pg_raw = (xkag / xlf * (t0 - t1) * math.pi / 2.0) * pg_sum / den_safe
    pg_dt = pg_raw * dt
    pg_cap = torch.minimum(torch.maximum(pg_dt, -x("qg")), zero)
    pg = torch.where(graupel_active, pg_cap, zero)
    melt = torch.where(warm & (x("qi") > 0.0), x("qi"), zero)
    coef = xlf / torch.clamp(cpm, min=qmin)
    t_out = ((t + coef * ps) + coef * pg) - coef * melt
    result = torch.stack((ps_raw, ps_dt, ps, t1, pg_raw, pg_dt, pg, t_out))
    diagnostic = {
        "warm": warm,
        "snow_active": snow_active,
        "graupel_active": graupel_active,
        "ps_dt": ps_dt,
        "pg_dt": pg_dt,
        "qs": x("qs"),
        "qg": x("qg"),
        "cpm": cpm,
        "den_safe": den_safe,
        "t1": t1,
        "melt": melt,
    }
    return result, diagnostic


def analytic_tangent(fields: dict, direction: str) -> list[float]:
    def x(name: str) -> float:
        return get(fields, STAGE, name, TARGET)

    cpm = x("cpm")
    qv = get(fields, "c3_pre_mf_d1", "qv_before", TARGET)
    ps = x("psmlt_capped_g")
    pg = x("pgmlt_capped_g")
    melt = get(fields, "c3_pre_mf_d1", "pimlt_qi", TARGET)
    t = x("t")
    t1 = x("t1")
    dt = x("dtcld")
    t0 = x("t0c")
    xlf = x("xlf")
    coef = xlf / cpm

    def logfactor(temp: float) -> float:
        return 1.5 / temp - 1.0 / (temp + 120.0) - 1.0 / (t0 - temp)

    if direction == "relative_qv16":
        dcpm = (1846.4 - 1004.5) * qv
        dpsraw = dpsdt = dps = 0.0
        dt1 = -(xlf * ps / (cpm * cpm)) * dcpm
        dpgraw = x("pgmlt_raw") * logfactor(t1) * dt1
        dpgdt = dpgraw * dt
        dpg = dpgdt
        dout = -(xlf * dcpm / (cpm * cpm)) * (ps + pg - melt) + coef * dpg
    elif direction == "absolute_t16":
        dpsraw = x("psmlt_raw") * logfactor(t)
        dpsdt = dpsraw * dt
        dps = dpsdt
        dt1 = 1.0 + coef * dps
        dpgraw = x("pgmlt_raw") * logfactor(t1) * dt1
        dpgdt = dpgraw * dt
        dpg = dpgdt
        dout = 1.0 + coef * (dps + dpg)
    else:
        raise ValueError("unknown D1 tangent direction")
    return [dpsraw, dpsdt, dps, dt1, dpgraw, dpgdt, dpg, dout]


def active_signature(
    diag: dict, qv: torch.Tensor, t: torch.Tensor, base: dict
) -> tuple:
    return (
        bool(qv > 1e-15),
        bool(t > base["t0c"]),
        bool(diag["snow_active"]),
        bool(diag["graupel_active"]),
        bool(diag["ps_dt"] > -diag["qs"]),
        bool(diag["ps_dt"] < 0),
        bool(diag["pg_dt"] > -diag["qg"]),
        bool(diag["pg_dt"] < 0),
        bool(diag["cpm"] > base["qcrmin"]),
        bool(diag["t1"] > base["t0c"]),
        bool(diag["melt"] > 0),
    )


def derivative_replay(fields: dict) -> dict:
    need(
        sha((REPO / "oracle/kdm6/thermo.py").read_bytes()) == ORACLE_THERMO_SHA,
        "pinned f64 QV→cpm oracle source",
    )
    names = (
        "qs",
        "qg",
        "qi",
        "ni",
        "t",
        "p",
        "den",
        "mass_den",
        "rhox",
        "cpm",
        "n0so",
        "n0go",
        "n0sfac",
        "work2",
        "precg2",
        "rslope_s",
        "rslope2_s",
        "rslopeb_s",
        "rslopemu_s",
        "rslope_g",
        "rslope2_g",
        "rslopeb_g",
        "rslopemu_g",
        "precs1",
        "precs2",
        "precg1",
        "xlf",
        "t0c",
        "qcrmin",
        "dtcld",
    )
    base = {
        name: torch.tensor(get(fields, STAGE, name, TARGET), dtype=torch.float64)
        for name in names
    }
    qv0 = torch.tensor(
        get(fields, "c3_pre_mf_d1", "qv_before", TARGET), dtype=torch.float64
    )
    t0 = base["t"]
    baseline, diag = torch_producer(base, qv0, t0)
    matching = (
        "psmlt_raw",
        "psmlt_dt",
        "psmlt_capped_g",
        "t1",
        "pgmlt_raw",
        "pgmlt_dt",
        "pgmlt_capped_g",
    )
    for i, name in enumerate(matching):
        check(
            fields,
            STAGE,
            name,
            TARGET,
            baseline[i].item(),
            "differentiable D1 baseline: " + name,
        )
    check(
        fields,
        "c3_pre_mf_d1",
        "t_after_d1",
        TARGET,
        baseline[-1].item(),
        "differentiable D1 temperature baseline",
    )
    need(
        word(compute_cpm(qv0, params=default_thermo_params()).item())
        == fields[(STAGE, "cpm", TARGET)]["raw_hex"],
        "D1 heat-capacity producer baseline",
    )
    signature = active_signature(diag, qv0, t0, base)
    need(all(signature), "strict native16 snow/graupel/ice producer branch")

    def fn(qv: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        return torch_producer(base, qv, t)[0]

    weights = torch.tensor(
        (2.0, -3.0, 5.0, 7.0, 11.0, -13.0, 17.0, 19.0), dtype=torch.float64
    )
    _, pullback = torch.func.vjp(fn, qv0, t0)
    vq, vt = pullback(weights)
    zero = torch.zeros_like(qv0)
    directions = {}
    for name, tangent in (
        ("relative_qv16", (qv0, zero)),
        ("absolute_t16", (zero, torch.ones_like(t0))),
    ):
        _, jvp = torch.func.jvp(fn, (qv0, t0), tangent)
        expected = torch.tensor(analytic_tangent(fields, name), dtype=torch.float64)
        need(
            torch.allclose(jvp, expected, rtol=2e-11, atol=2e-18),
            "independent D1 producer JVP: " + name,
        )
        vjp_dot = (vq * tangent[0] + vt * tangent[1]).item()
        jvp_dot = torch.dot(weights, jvp).item()
        need(
            abs(vjp_dot - jvp_dot) <= 2e-11 * max(1e-12, abs(jvp_dot)),
            "D1 producer weighted VJP transpose: " + name,
        )
        steps = {}
        for h in (0.1, 0.01, 0.001):
            if name == "relative_qv16":
                plus = (qv0 * (1.0 + h), t0)
                minus = (qv0 * (1.0 - h), t0)
                gap = (plus[0].item() - minus[0].item()) / qv0.item()
                plus_scalar = scalar_producer(fields, TARGET, qv=plus[0].item())
                minus_scalar = scalar_producer(fields, TARGET, qv=minus[0].item())
            else:
                plus = (qv0, t0 + h)
                minus = (qv0, t0 - h)
                gap = plus[1].item() - minus[1].item()
                plus_scalar = scalar_producer(
                    fields, TARGET, temperature=plus[1].item()
                )
                minus_scalar = scalar_producer(
                    fields, TARGET, temperature=minus[1].item()
                )
            high, hi_diag = torch_producer(base, *plus)
            low, lo_diag = torch_producer(base, *minus)
            need(
                active_signature(hi_diag, *plus, base) == signature
                and active_signature(lo_diag, *minus, base) == signature,
                "branch-preserving D1 producer endpoints: " + name,
            )
            for i, field in enumerate((*matching, "D1_T_out")):
                need(
                    word(high[i].item()) == word(plus_scalar[field])
                    and word(low[i].item()) == word(minus_scalar[field]),
                    "independent scalar D1 producer endpoint: " + field,
                )
            difference = high - low
            fd = difference / gap
            residual = fd - jvp
            rel_errors = []
            for i in range(len(fd)):
                tangent_value = abs(jvp[i].item())
                if tangent_value > 1e-20:
                    relative = abs(residual[i].item()) / tangent_value
                    need(relative <= 1e-6, "represented D1 producer FD/JVP: " + name)
                    rel_errors.append(relative)
                else:
                    roundoff = 8.0 * math.ulp(baseline[i].item()) / gap + 1e-24
                    need(
                        abs(fd[i].item()) <= roundoff,
                        "zero-signal D1 producer FD: " + name,
                    )
            steps[str(h)] = {
                "represented_input_gap": gap,
                "output_difference": difference.tolist(),
                "output_ulp": [math.ulp(x) for x in baseline.tolist()],
                "fd": fd.tolist(),
                "fd_minus_jvp": residual.tolist(),
                "temperature_signal_ulps": abs(difference[-1].item())
                / math.ulp(baseline[-1].item()),
                "max_nonzero_relative_fd_jvp_error": max(rel_errors, default=0.0),
            }
        directions[name] = {
            "jvp": jvp.tolist(),
            "independent_analytic": expected.tolist(),
            "weighted_vjp_contraction": vjp_dot,
            "weighted_jvp_contraction": jvp_dot,
            "finite_differences": steps,
        }
    return {
        "native_level_1based": 16,
        "output_order": list(AD_OUTPUTS),
        "baseline_outputs": baseline.tolist(),
        "baseline_branch_signature": signature,
        "directions": directions,
        "fixed_inputs": "density, pressure, QI/NI, snow/graupel intercepts/slopes, work2, precg2, rhox, other process rates, geometry and substep schedule",
    }


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    parent = module(PARENT / "replay.py", PARENT_SOURCE_SHA, "native_qi_applied_parent")
    parent_result = parent.replay()
    p39 = parent.module(P39 / "replay.py", parent.P39_SOURCE_SHA, "native39_parent")
    d1_qi = parent.module(
        PD1_QI / "replay.py", parent.PD1_QI_SOURCE_SHA, "d1_qi_parent"
    )
    d1_ad = parent.module(
        PD1_AD / "replay.py", parent.PD1_AD_SOURCE_SHA, "d1_ad_parent"
    )
    old = parent.load_capture(parent.pinned(parent.CAPTURE), p39, d1_qi, d1_ad)
    source_run = provenance(parent, p39)
    raw = pinned(CAPTURE) if capture_override is None else capture_override
    if capture_override is not None:
        need(capture_sha is not None and sha(raw) == capture_sha, "override SHA-256")
    fields = load_capture(raw, parent, p39, old)
    sed = parent.sed_replay(fields)
    d1_state = parent.d1_replay(fields)
    need(
        sed == parent_result["sedimentation"] and d1_state == parent_result["d1"],
        "unchanged applied-QI/D1 parent numerical result",
    )
    baseline = baseline_producer(fields)
    derivative = derivative_replay(fields)
    result = {
        "schema": "kdm6.native_active_d1_melt_producer_ad.v1",
        "call": {
            "native_ij_1based": [203, 149],
            "runtime_call": 2,
            "one_step_call": 2,
            "b_zero": 27945,
            "B": 32248,
            "K": 39,
            "native_level_1based": 16,
        },
        "capture_rows": len(fields),
        "parent_rows_raw_bit_equal": len(old),
        "source_and_run": source_run,
        "baseline_producer": baseline,
        "parent_sedimentation_and_D1_state_raw_bit_replayed": True,
        "conditional_derivatives": derivative,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }
    if capture_override is None:
        saved = json.loads(pinned("results.json"))
        for key in (
            "schema",
            "call",
            "capture_rows",
            "parent_rows_raw_bit_equal",
            "source_and_run",
            "baseline_producer",
            "parent_sedimentation_and_D1_state_raw_bit_replayed",
            "scientific_status",
            "physical_unit_status",
        ):
            need(saved[key] == result[key], "stable D1 producer result: " + key)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("NATIVE_D1_MELT_PRODUCER_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {
                    "schema": result["schema"],
                    "source_order_levels": result["baseline_producer"][
                        "raw_bit_replayed_levels"
                    ],
                    "scientific_status": result["scientific_status"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
