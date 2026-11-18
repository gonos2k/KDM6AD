#!/usr/bin/env python3
"""Pinned same-call D1-to-postmelt ProgB replay and conditional local AD."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PARENT = REPO / "harness/evidence/native_d1_melt_state_ad_2026-11-04"
PARENT_SOURCE_SHA = "bc3836e1bab4f5a44c0024127dd1d565d12acd88be27945556079dde54f5ae92"
CAPTURE = "raw/native_qnice_applied_67313_runtime2.csv"
MANIFEST_SHA = "55b9f2edb21816dae4f67414b94e5731c919c5999ad16a0987c82f2e7eb786cc"
ORDER_SHA = "151223a88fafecf132cf23900c511b19378fb46cc6c762b465c58797d18d9a4e"
K = 39
TARGET = 23  # top-first zero-based position of native level 16
STAGE = "d1_postmelt_progb"
MERGE = "d1_postmelt_progb_merge"
FIELDS = (
    "qg",
    "bg",
    "active",
    "trace",
    "produced",
    "bg_den",
    "zero_den",
    "density_divisor",
    "rhox_op",
    "rhox_c",
    "bg_new_op",
    "rhox",
    "bg_new",
    "qcrmin",
    "brs_min",
    "rho_min",
    "rho_max",
    "idx_left",
    "idx_right",
    "avtg",
    "bvtg",
    "op_f32",
    "midpoint_trace",
)
BOOL_FIELDS = {"active", "trace", "produced", "zero_den", "op_f32", "midpoint_trace"}
MERGE_FIELDS = ("rhox", "bg")
AD_OUTPUTS = ("qg_d1", "brs_d1", "ratio_raw", "rhox", "brs_reclamped", "avtg", "bvtg")
TABLE = (100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0)
AVTG = (
    54.9153,
    74.2262,
    88.8313,
    101.0411,
    111.7359,
    121.3625,
    130.1841,
    138.3714,
    146.0422,
)
BVTG = (0.5446, 0.5375, 0.5339, 0.5316, 0.5299, 0.5286, 0.5275, 0.5266, 0.5258)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def f64(raw_hex: str) -> float:
    result = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(result), "nonfinite native ProgB field")
    return result


def manifest() -> dict:
    raw = (HERE / "source_manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "ProgB manifest SHA-256")
    return json.loads(raw)


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == manifest()[name], "ProgB packet SHA-256: " + name)
    return raw


def parent_module():
    path = PARENT / "replay.py"
    need(sha(path.read_bytes()) == PARENT_SOURCE_SHA, "parent D1 state replay source")
    spec = importlib.util.spec_from_file_location("native_d1_state_parent", path)
    need(spec is not None and spec.loader is not None, "parent D1 state import")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rows(raw: bytes) -> tuple[list[str], list[dict]]:
    lines = raw.decode("ascii").splitlines()
    reader = csv.DictReader(
        io.StringIO(
            "\n".join([lines[0], *(x for x in lines[1:] if not x.startswith("#"))])
        )
    )
    need(
        reader.fieldnames is not None and len(reader.fieldnames) == 11,
        "native ProgB CSV header",
    )
    return lines, list(reader)


def load_capture(raw: bytes, parent) -> dict:
    need(len(raw) < 4 << 20 and raw.endswith(b"\n"), "ProgB capture byte bound")
    lines, data = rows(raw)
    old_lines, old_data = rows(parent.pinned(parent.CAPTURE))
    need(
        len(lines) == 8896
        and len(data) == 8892
        and lines[0] == old_lines[0]
        and lines[1] == old_lines[1]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=27945; K=39; max_rows=9000; max_bytes=4194304"
        and lines[-1] == "# native_rows=8892,status=complete",
        "ProgB capture header/footer/inventory",
    )
    old_keys = {(r["stage"], r["field"], int(r["k_zero"])) for r in old_data}
    expected = old_keys | {
        (stage, name, k)
        for stage, names in ((STAGE, FIELDS), (MERGE, MERGE_FIELDS))
        for name in names
        for k in range(K)
    }
    need(len(expected) == 8892, "ProgB expected key count")
    old_subsequence = []
    fields = {}
    order = []
    for row in data:
        need(set(row) == set(data[0]) and None not in row.values(), "ProgB row shape")
        try:
            k, bits = int(row["k_zero"]), int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("ProgB k/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < K
            and row["k_zero"] == str(k)
            and key in expected
            and key not in fields,
            "ProgB row uniqueness",
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
            "ProgB call identity",
        )
        need(
            row["substep"]
            == ("1" if row["stage"] == "ice_sedimentation_conservative_n1" else "0"),
            "ProgB substep",
        )
        need(
            row["raw_hex"] == format(bits, "x") and bits >= 0,
            "ProgB canonical raw word",
        )
        if key in old_keys:
            old_subsequence.append(row)
        else:
            dtype = (
                "bool"
                if row["stage"] == STAGE and row["field"] in BOOL_FIELDS
                else "f64"
            )
            need(
                row["dtype"] == dtype and bits < (2 if dtype == "bool" else 1 << 64),
                "new ProgB dtype/raw word",
            )
            if dtype == "f64":
                f64(row["raw_hex"])
        fields[key] = row
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
        len(fields) == len(expected) and set(fields) == expected,
        "complete ProgB row inventory",
    )
    need(
        old_subsequence == old_data, "parent 7917 rows preserved in order and raw bits"
    )
    need(sha(("\n".join(order) + "\n").encode()) == ORDER_SHA, "ProgB row order")
    return fields


def value(fields: dict, stage: str, name: str, k: int) -> float:
    row = fields[(stage, name, k)]
    return (
        float(int(row["raw_hex"], 16))
        if row["dtype"] == "bool"
        else f64(row["raw_hex"])
    )


def check(
    fields: dict, stage: str, name: str, k: int, got: float | bool, why: str
) -> None:
    row = fields[(stage, name, k)]
    expected = format(int(got), "x") if row["dtype"] == "bool" else word(float(got))
    need(row["raw_hex"] == expected, why)


def source_and_run(parent) -> dict:
    receipt = json.loads(pinned("raw/build_receipt.json"))
    parent_raw = parent.pinned("raw/build_receipt.json")
    old = json.loads(parent_raw)
    need(
        receipt["schema"] == "kdm6.native_d1_postmelt_progb_cpp_build.v1"
        and receipt["parent_build_receipt_sha256"] == sha(parent_raw)
        and receipt["parent_dso_sha256"] == old["new_dso_sha256"]
        and receipt["candidate"] == old["candidate"]
        and receipt["only_source_change_vs_parent"]
        == ["src/coordinator.cpp", "src/progb.cpp"],
        "ProgB build/parent contract",
    )
    coord = pinned("executed_cpp/coordinator.cpp")
    progb = pinned("executed_cpp/progb.cpp")
    for name in (
        "coordinator_decl.txt",
        "coordinator_on.txt",
        "coordinator_off.txt",
        "coordinator_merge.txt",
    ):
        block = pinned("producer/" + name)
        need(coord.count(block) == 1, "unique coordinator capture block: " + name)
        coord = coord.replace(block, b"", 1)
    need(
        coord == parent.pinned("executed_cpp/coordinator.cpp"),
        "capture-only postmelt coordinator overlay",
    )
    for name in ("progb_include.txt", "progb_flag.txt", "progb_fields.txt"):
        block = pinned("producer/" + name)
        need(progb.count(block) == 1, "unique ProgB capture block: " + name)
        progb = progb.replace(block, b"", 1)
    need(
        progb == pinned("executed_cpp/parent_progb.cpp"),
        "capture-only ProgB source overlay",
    )
    need(
        receipt["source_sha256"]["coordinator.cpp"]
        == sha(pinned("executed_cpp/coordinator.cpp"))
        and receipt["source_sha256"]["progb.cpp"]
        == sha(pinned("executed_cpp/progb.cpp")),
        "executed ProgB source hashes",
    )
    need(
        receipt["source_headers_sha256"]["progb.h"]
        == sha(pinned("executed_cpp/progb.h"))
        and all(
            receipt["source_sha256"][n] == old["source_sha256"][n]
            for n in old["source_sha256"]
            if n != "coordinator.cpp"
        )
        and all(
            receipt["source_headers_sha256"][n] == old["source_headers_sha256"][n]
            for n in old["source_headers_sha256"]
        )
        and "-ffp-contract=off" in receipt["cxx_flags"],
        "ProgB source/header/FP contract",
    )
    for name, expected in receipt["capture_blocks_sha256"].items():
        need(
            sha(pinned("producer/" + name)) == expected, "build capture block: " + name
        )
    need(
        receipt["runner_sha256"] == sha(pinned("producer/run.py.txt")),
        "ProgB runner source",
    )
    endpoints = set()
    for mode in ("off", "on"):
        run = json.loads(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = json.loads(session_raw)
        need(
            run["schema"] == "kdm6.native_d1_progb_run.v1" and run["mode"] == mode,
            "ProgB run schema/mode",
        )
        need(run["session_record_sha256"] == sha(session_raw), "ProgB run/session")
        need(
            run["source_sha256"]
            == {n: receipt["source_sha256"][n] for n in run["source_sha256"]}
            and set(run["object_sha256"])
            == {
                "coordinator.cpp.o",
                "melt_freeze.cpp.o",
                "runtime.cpp.o",
                "sedimentation_conservative.cpp.o",
            }
            and all(
                run["object_sha256"][n] == receipt["object_sha256"][n]
                for n in run["object_sha256"]
            ),
            "ProgB run source/object pins",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == receipt["new_executable_sha256"]
            and run["dso_sha256"]
            == session["library_candidate_sha256"]
            == receipt["new_dso_sha256"],
            "ProgB executable/DSO",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True
            and session["steps"] == 1
            and session["dt_seconds"] == 20,
            "completed ProgB host call",
        )
        need(
            any(
                "/native_d1_progb_20261104/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in s
                for s in session["loaded_library_lines"]
            ),
            "loaded isolated ProgB DSO",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"
            and run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "ProgB same input and prior endpoint",
        )
        need(
            run["captures"]
            == (
                {}
                if mode == "off"
                else {"native_qnice_applied_67313_runtime2.csv": manifest()[CAPTURE]}
            ),
            "ProgB off/on capture inventory",
        )
        endpoints.add(run["endpoint_sha256"])
    need(len(endpoints) == 1, "ProgB capture noninterference")
    return {
        "host_executable_sha256": receipt["new_executable_sha256"],
        "isolated_dso_sha256": receipt["new_dso_sha256"],
        "off_on_endpoint_sha256": endpoints.pop(),
        "capture_sha256": manifest()[CAPTURE],
    }


def scalar_progb(
    qg: float,
    bg: float,
    *,
    qcrmin: float = 1e-9,
    brs_min: float = 1e-15,
    rho_min: float = 100.0,
    rho_max: float = 900.0,
    midpoint_trace: bool = False,
) -> dict:
    active = qg > qcrmin or bg > brs_min
    trace = midpoint_trace and not active and qg > 0.0
    produced = active or trace
    bg_den = max(bg, brs_min)
    zero_den = bg_den == 0.0
    density_divisor = 1.0 if zero_den or (midpoint_trace and not active) else bg_den
    rhox_op = qg / density_divisor
    rhox_c = min(max(rhox_op, rho_min), rho_max)
    bg_new_op = qg / rhox_c
    rhox = rhox_c if active else 400.0 if trace else 0.0 if midpoint_trace else 400.0
    bg_new = (
        bg_new_op if active else qg / 400.0 if trace else 0.0 if midpoint_trace else bg
    )
    right = min(max(bisect.bisect_right(TABLE, rhox), 1), 8)
    left = right - 1

    def table_result(values: tuple[float, ...]) -> float:
        tmp2 = 1.0 / (TABLE[right] - TABLE[left])
        d1 = rhox - TABLE[left]
        raw = values[left] + (d1 * (values[right] - values[left])) * tmp2
        if rhox == TABLE[-1]:
            raw = values[-1]
        return raw if produced else 0.0

    return {
        "qg": qg,
        "bg": bg,
        "active": active,
        "trace": trace,
        "produced": produced,
        "bg_den": bg_den,
        "zero_den": zero_den,
        "density_divisor": density_divisor,
        "rhox_op": rhox_op,
        "rhox_c": rhox_c,
        "bg_new_op": bg_new_op,
        "rhox": rhox,
        "bg_new": bg_new,
        "qcrmin": qcrmin,
        "brs_min": brs_min,
        "rho_min": rho_min,
        "rho_max": rho_max,
        "idx_left": float(left),
        "idx_right": float(right),
        "avtg": table_result(AVTG),
        "bvtg": table_result(BVTG),
        "op_f32": False,
        "midpoint_trace": midpoint_trace,
    }


def baseline(fields: dict, parent) -> dict:
    counts = {"inactive": 0, "lower": 0, "interior": 0, "upper": 0}
    for k in range(K):
        qg, bg = value(fields, STAGE, "qg", k), value(fields, STAGE, "bg", k)
        check(
            fields,
            STAGE,
            "qg",
            k,
            value(fields, parent.CONSUMER, "qg_after", k),
            "post-D1 QG producer handoff",
        )
        check(
            fields,
            STAGE,
            "bg",
            k,
            value(fields, parent.CONSUMER, "brs_after", k),
            "post-D1 BRS producer handoff",
        )
        expected = scalar_progb(qg, bg)
        for name in FIELDS:
            check(
                fields,
                STAGE,
                name,
                k,
                expected[name],
                "source-order postmelt ProgB: " + name,
            )
        check(fields, MERGE, "bg", k, expected["bg_new"], "merged ProgB BRS")
        check(
            fields, parent.RESLOPE, "brs_before", k, bg, "ProgB input/reslope handoff"
        )
        check(
            fields,
            parent.RESLOPE,
            "brs_after",
            k,
            value(fields, MERGE, "bg", k),
            "ProgB return/BRS store",
        )
        if expected["active"]:
            check(fields, MERGE, "rhox", k, expected["rhox"], "active ProgB rhox merge")
            category = (
                "lower"
                if expected["rhox_op"] < 100
                else "upper"
                if expected["rhox_op"] > 900
                else "interior"
            )
        else:
            category = "inactive"  # persistent PR may retain earlier rhox
        counts[category] += 1
    target = {n: value(fields, STAGE, n, TARGET) for n in FIELDS}
    need(
        target["active"] == 1
        and target["rhox_op"] < 900
        and target["rhox_op"] > 800
        and target["idx_left"] == 7
        and target["idx_right"] == 8,
        "native16 interior upper-table segment",
    )
    return {
        "levels_raw_bit_replayed": K,
        "branch_counts": counts,
        "native16": target,
        "native16_merged_rhox": value(fields, MERGE, "rhox", TARGET),
        "native16_merged_brs": value(fields, MERGE, "bg", TARGET),
        "native16_upper_margin": 900.0 - target["rhox_op"],
    }


def torch_progb(qg: torch.Tensor, bg: torch.Tensor) -> tuple[torch.Tensor, tuple]:
    active = (qg > 1e-9) | (bg > 1e-15)
    bg_den = torch.clamp(bg, min=1e-15)
    raw = qg / bg_den
    clamped = torch.clamp(raw, min=100.0, max=900.0)
    rho = torch.where(active, clamped, torch.full_like(qg, 400.0))
    bg_new = torch.where(active, qg / clamped, bg)
    tbl = torch.tensor(TABLE, dtype=qg.dtype)
    av = torch.tensor(AVTG, dtype=qg.dtype)
    bv = torch.tensor(BVTG, dtype=qg.dtype)
    right = torch.clamp(
        torch.searchsorted(tbl, rho.contiguous(), right=True), min=1, max=8
    )
    left = right - 1
    tmp2 = 1.0 / (tbl[right] - tbl[left])
    d1 = rho - tbl[left]
    avraw = av[left] + (d1 * (av[right] - av[left])) * tmp2
    bvraw = bv[left] + (d1 * (bv[right] - bv[left])) * tmp2
    avraw = torch.where(rho == 900.0, av[-1], avraw)
    bvraw = torch.where(rho == 900.0, bv[-1], bvraw)
    avout = torch.where(active, avraw, torch.zeros_like(qg))
    bvout = torch.where(active, bvraw, torch.zeros_like(qg))
    output = torch.stack((qg, bg, raw, rho, bg_new, avout, bvout))
    signature = (
        bool(active),
        bool(bg > 1e-15),
        bool(raw > 100.0),
        bool(raw < 900.0),
        int(left),
        int(right),
    )
    return output, signature


def make_d1_base(fields: dict, parent) -> dict:
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
        n: torch.tensor(value(fields, parent.PRODUCER, n, TARGET), dtype=torch.float64)
        for n in names
    }
    for n in (
        "qr_before",
        "nr_before",
        "brs_before",
        "pfrzdtr",
        "nfrzdtr",
        "delta_brs_freeze",
    ):
        base[n] = torch.tensor(
            value(fields, parent.CONSUMER, n, TARGET), dtype=torch.float64
        )
    return base


def analytic(fields: dict, parent, producer, direction: str) -> list[float]:
    tangent = parent.analytic(fields, producer, direction)
    dqg, dbg = tangent[7], tangent[14]
    qg, bg = value(fields, STAGE, "qg", TARGET), value(fields, STAGE, "bg", TARGET)
    rho = value(fields, STAGE, "rhox_op", TARGET)
    drho = dqg / bg - qg * dbg / (bg * bg)
    dbnew = dqg / rho - qg * drho / (rho * rho)
    da = drho * (AVTG[8] - AVTG[7]) / 100.0
    db = drho * (BVTG[8] - BVTG[7]) / 100.0
    return [dqg, dbg, drho, drho, dbnew, da, db]


def derivative(fields: dict, parent) -> dict:
    producer = parent.parent_module()
    base = make_d1_base(fields, parent)
    qv = torch.tensor(
        value(fields, "c3_pre_mf_d1", "qv_before", TARGET), dtype=torch.float64
    )
    inputs = (qv, base["t"], base["qs"], base["qg"], base["rhox"])

    def fn(*args):
        d1_out, d1_sig = parent.torch_state(base, producer, *args)
        out, progb_sig = torch_progb(d1_out[7], d1_out[14])
        return out, (d1_sig, progb_sig)

    def values(*args):
        return fn(*args)[0]

    baseline_out, signature = fn(*inputs)
    need(
        all(signature[0]) and signature[1] == (True, True, True, True, 7, 8),
        "strict native16 D1/ProgB interior branch",
    )
    for i, name in enumerate(AD_OUTPUTS):
        field = {
            "qg_d1": "qg",
            "brs_d1": "bg",
            "ratio_raw": "rhox_op",
            "brs_reclamped": "bg_new",
        }.get(name, name)
        check(
            fields,
            STAGE,
            field,
            TARGET,
            baseline_out[i].item(),
            "differentiable ProgB baseline: " + name,
        )
    weights = torch.tensor(
        (2.0, -3.0, 5.0, 7.0, -11.0, 13.0, -17.0), dtype=torch.float64
    )
    _, pullback = torch.func.vjp(values, *inputs)
    pulled = pullback(weights)
    directions = {}
    for name, ix, seed, steps in (
        ("relative_qv16", 0, qv, (0.1, 0.01, 0.001)),
        ("absolute_t16", 1, torch.ones_like(inputs[1]), (0.1, 0.01, 0.001)),
        ("relative_qg16", 3, inputs[3], (1e-5, 1e-6, 1e-7)),
        ("relative_rhox16", 4, inputs[4], (1e-5, 1e-6, 1e-7)),
    ):
        tangent = tuple(
            seed if i == ix else torch.zeros_like(x) for i, x in enumerate(inputs)
        )
        _, jvp = torch.func.jvp(values, inputs, tangent)
        expected = torch.tensor(
            analytic(fields, parent, producer, name), dtype=torch.float64
        )
        cancellation_atol = {
            "ratio_raw": 1e-12,
            "rhox": 1e-12,
            "avtg": 1e-13,
            "bvtg": 1e-17,
        }
        for i, output in enumerate(AD_OUTPUTS):
            atol = (
                cancellation_atol.get(output, 2e-18)
                if name in ("relative_qv16", "absolute_t16")
                else 2e-18
            )
            need(
                abs(jvp[i].item() - expected[i].item())
                <= 2e-10 * abs(expected[i].item()) + atol,
                "independent D1→ProgB analytic JVP: " + name + "/" + output,
            )
        vjp_dot = sum((v * t for v, t in zip(pulled, tangent))).item()
        jvp_dot = torch.dot(weights, jvp).item()
        dot_scale = torch.sum(torch.abs(weights * jvp)).item()
        need(
            abs(vjp_dot - jvp_dot) <= 2e-8 * dot_scale + 1e-20,
            "D1→ProgB weighted VJP transpose: " + name,
        )
        finite_differences = {}
        for h in steps:
            plus = list(inputs)
            minus = list(inputs)
            plus[ix] = inputs[ix] + seed * h
            minus[ix] = inputs[ix] - seed * h
            high, hi_sig = fn(*plus)
            low, lo_sig = fn(*minus)
            need(
                hi_sig == signature and lo_sig == signature,
                "D1→ProgB branch-preserving endpoints: " + name,
            )
            key = ("qv", "t", "qs", "qg", "rhox")[ix]
            high_d1 = parent.scalar_state(
                fields, TARGET, producer, **{key: plus[ix].item()}
            )
            low_d1 = parent.scalar_state(
                fields, TARGET, producer, **{key: minus[ix].item()}
            )
            for output, state in ((high, high_d1), (low, low_d1)):
                scalar = scalar_progb(state["qg_after"], state["brs_after"])
                expected_values = (
                    state["qg_after"],
                    state["brs_after"],
                    scalar["rhox_op"],
                    scalar["rhox"],
                    scalar["bg_new"],
                    scalar["avtg"],
                    scalar["bvtg"],
                )
                for i, x in enumerate(expected_values):
                    need(
                        word(output[i].item()) == word(x),
                        "independent scalar D1→ProgB endpoint: " + AD_OUTPUTS[i],
                    )
            gap = (plus[ix].item() - minus[ix].item()) / seed.item()
            fd = (high - low) / gap
            errors = []
            for i, output in enumerate(AD_OUTPUTS):
                signal = abs(jvp[i].item())
                residual = abs(fd[i].item() - jvp[i].item())
                roundoff = 64 * math.ulp(baseline_out[i].item()) / gap
                bound = 5 * h * h * signal + roundoff + 1e-20
                need(
                    residual <= bound,
                    "represented D1→ProgB FD/JVP: " + name + "/" + output,
                )
                errors.append(residual / max(1.0, signal))
            finite_differences[str(h)] = {
                "represented_input_gap": gap,
                "endpoint_rho_raw": [low[2].item(), high[2].item()],
                "max_normalized_fd_jvp_error": max(errors),
            }
        directions[name] = {
            "jvp": jvp.tolist(),
            "analytic": expected.tolist(),
            "weighted_vjp_contraction": vjp_dot,
            "weighted_jvp_contraction": jvp_dot,
            "finite_differences": finite_differences,
        }

    # The already-used D1 QG h=1e-4 leaves the local ProgB branch. Record it
    # separately; its centered secant is not an acceptance check for the JVP.
    qg_entry = inputs[3].item()
    qg_d1, bg_d1 = baseline_out[0].item(), baseline_out[1].item()
    critical = (900.0 * bg_d1 - qg_d1) / qg_entry
    need(1e-5 < critical < 1e-4, "native16 upper-cap critical QG direction")
    plus = list(inputs)
    minus = list(inputs)
    plus[3] = inputs[3] * 1.0001
    minus[3] = inputs[3] * 0.9999
    high, hi_sig = fn(*plus)
    low, lo_sig = fn(*minus)
    need(
        hi_sig[1][3] is False
        and lo_sig[1][3] is True
        and high[3].item() == 900.0
        and low[3].item() < 900.0,
        "explicit QG cross-cap endpoints",
    )
    for output, candidate in ((high, plus), (low, minus)):
        state = parent.scalar_state(fields, TARGET, producer, qg=candidate[3].item())
        scalar = scalar_progb(state["qg_after"], state["brs_after"])
        need(
            word(output[2].item()) == word(scalar["rhox_op"])
            and word(output[3].item()) == word(scalar["rhox"])
            and word(output[4].item()) == word(scalar["bg_new"]),
            "independent cross-cap endpoint",
        )
    represented_gap = (plus[3].item() - minus[3].item()) / qg_entry
    cross_secant = ((high - low) / represented_gap).tolist()
    return {
        "native_level_1based": 16,
        "output_order": list(AD_OUTPUTS),
        "baseline_outputs": baseline_out.tolist(),
        "baseline_branch_signature": signature,
        "directions": directions,
        "qg_cross_cap": {
            "nominal_half_step": 1e-4,
            "critical_positive_relative_step": critical,
            "lower_rho_raw": low[2].item(),
            "upper_rho_raw": high[2].item(),
            "lower_rhox": low[3].item(),
            "upper_rhox": high[3].item(),
            "branch_signatures": [lo_sig[1], hi_sig[1]],
            "cross_branch_secant": cross_secant,
            "local_jvp": directions["relative_qg16"]["jvp"],
        },
        "fixed_inputs": "upstream D1 slopes/intercepts, density, pressure, other state/forcing, ProgB parameters, geometry and substep schedule",
    }


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    parent = parent_module()
    parent_result = parent.replay()
    need(
        parent_result["scientific_status"] == "INCONCLUSIVE", "verified parent D1 state"
    )
    source = source_and_run(parent)
    if capture_override is None:
        raw = pinned(CAPTURE)
    else:
        need(
            capture_sha is not None and sha(capture_override) == capture_sha,
            "test ProgB capture SHA-256",
        )
        raw = capture_override
    fields = load_capture(raw, parent)
    result = {
        "schema": "kdm6.native_d1_postmelt_progb_ad.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "capture_rows": 8892,
        "prior_rows_raw_bit_equal": 7917,
        "source_and_run": source,
        "baseline": baseline(fields, parent),
        "conditional_derivatives": derivative(fields, parent),
    }
    if capture_override is None and "results.json" in manifest():
        saved = json.loads(pinned("results.json"))
        need(
            saved["schema"] == result["schema"]
            and saved["capture_rows"] == result["capture_rows"]
            and saved["source_and_run"] == result["source_and_run"]
            and saved["baseline"] == result["baseline"],
            "stored ProgB summary",
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-results", action="store_true")
    args = parser.parse_args()
    result = replay()
    if args.write_results:
        (HERE / "results.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
    else:
        print("NATIVE_D1_PROGB_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {k: result[k] for k in ("schema", "scientific_status", "capture_rows")},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
