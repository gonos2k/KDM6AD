#!/usr/bin/env python3
"""Pinned native D1 melt producer-to-state replay and conditional local AD."""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
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
PARENT = REPO / "harness/evidence/native_d1_melt_producer_ad_2026-11-04"
PARENT_SOURCE_SHA = "5c945b47cd018c53d63c4a120a92063ae491da2c4fa7173a4f6bf5a1667ef2fd"
CAPTURE = "raw/native_qnice_applied_61367_runtime2.csv"
MANIFEST_SHA = "3d005e9f8451046e3b48d2ee5317daec665eb961a4ebe7510ba21663dc4fe1a3"
ORDER_SHA = "f049c8bbcdb672393fa5bc398fd65426500d2ba5ffa5cc9d6eb9df172102db14"
K = 39
TARGET = 23  # top-first zero-based position of native level 16
PRODUCER = "d1_melt_producer"
CONSUMER = "d1_melt_consumer"
RESLOPE = "d1_brs_reslope"
ENTRY = "d1_state_entry"
ENTRY_FIELDS = ("qr", "nr", "brs")
NEW_PRODUCER = (
    "sfac_raw",
    "sfac",
    "gfac_raw",
    "gfac",
    "rhox_div",
    "delta_brs",
    "delta_brs_capped",
)
CONSUMER_FIELDS = (
    "qs_before",
    "qs_after",
    "qg_before",
    "qg_after",
    "qr_before",
    "qr1",
    "qr2",
    "qr_after",
    "nr_before",
    "nr1",
    "nr2",
    "nr_after",
    "brs_before",
    "brs_after",
    "warm_mask",
    "pfrzdtr",
    "nfrzdtr",
    "delta_brs_freeze",
    "sfac_melt",
    "gfac_melt",
    "delta_brs_capped",
)
RESLOPE_FIELDS = ("brs_before", "brs_after")
STATE_OUTPUTS = (
    "ps",
    "pg",
    "sfac",
    "gfac",
    "delta_brs",
    "delta_brs_capped",
    "qs_after",
    "qg_after",
    "qr1",
    "qr2",
    "qr_after",
    "nr1",
    "nr2",
    "nr_after",
    "brs_after",
    "t_after",
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def f64(raw_hex: str) -> float:
    result = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(result), "nonfinite native D1 field")
    return result


def manifest() -> dict:
    raw = (HERE / "source_manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "source manifest SHA-256")
    return json.loads(raw)


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == manifest()[name], "D1 state packet SHA-256: " + name)
    return raw


def parent_module():
    path = PARENT / "replay.py"
    need(sha(path.read_bytes()) == PARENT_SOURCE_SHA, "parent producer replay source")
    spec = importlib.util.spec_from_file_location(
        "native_d1_melt_producer_parent", path
    )
    need(spec is not None and spec.loader is not None, "parent producer import")
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
        "native D1 CSV header",
    )
    return lines, list(reader)


def load_capture(raw: bytes, parent) -> dict:
    need(len(raw) < 3 << 20 and raw.endswith(b"\n"), "D1 state capture byte bound")
    lines, data = rows(raw)
    old_lines, old_data = rows(parent.pinned(parent.CAPTURE))
    need(
        len(lines) == 7921
        and len(data) == 7917
        and lines[0] == old_lines[0]
        and lines[1] == old_lines[1]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=27945; K=39; max_rows=8000; max_bytes=3145728"
        and lines[-1] == "# native_rows=7917,status=complete",
        "D1 state capture header/footer/inventory",
    )
    old_keys = {(r["stage"], r["field"], int(r["k_zero"])) for r in old_data}
    expected = old_keys | {
        (stage, name, k)
        for stage, names in (
            (ENTRY, ENTRY_FIELDS),
            (PRODUCER, NEW_PRODUCER),
            (CONSUMER, CONSUMER_FIELDS),
            (RESLOPE, RESLOPE_FIELDS),
        )
        for name in names
        for k in range(K)
    }
    need(len(expected) == 7917, "D1 state expected key count")
    old_subsequence = []
    fields = {}
    order = []
    for row in data:
        need(
            set(row) == set(data[0]) and None not in row.values(), "D1 state row shape"
        )
        try:
            k, bits = int(row["k_zero"]), int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("D1 state k/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < K
            and row["k_zero"] == str(k)
            and key in expected
            and key not in fields,
            "D1 state row uniqueness",
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
            "D1 state call identity",
        )
        need(
            row["substep"]
            == ("1" if row["stage"] == "ice_sedimentation_conservative_n1" else "0"),
            "D1 state substep",
        )
        need(
            row["raw_hex"] == format(bits, "x") and bits >= 0,
            "D1 state canonical raw word",
        )
        if key in old_keys:
            old_subsequence.append(row)
        else:
            need(row["dtype"] == "f64" and bits < (1 << 64), "new D1 state dtype")
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
        "complete D1 state row inventory",
    )
    need(
        old_subsequence == old_data, "parent 6630 rows preserved in order and raw bits"
    )
    need(sha(("\n".join(order) + "\n").encode()) == ORDER_SHA, "D1 state row order")
    return fields


def value(fields: dict, stage: str, name: str, k: int) -> float:
    return f64(fields[(stage, name, k)]["raw_hex"])


def check(fields: dict, stage: str, name: str, k: int, got: float, why: str) -> None:
    need(fields[(stage, name, k)]["raw_hex"] == word(got), why)


def source_and_run(parent) -> dict:
    receipt = json.loads(pinned("raw/build_receipt.json"))
    parent_raw = parent.pinned("raw/build_receipt.json")
    old = json.loads(parent_raw)
    need(
        receipt["schema"] == "kdm6.native_d1_melt_state_entry_cpp_build.v1"
        and receipt["parent_build_receipt_sha256"] == sha(parent_raw)
        and receipt["parent_dso_sha256"] == old["new_dso_sha256"]
        and receipt["candidate"] == old["candidate"]
        and receipt["only_source_change_vs_parent"]
        == ["src/melt_freeze.cpp", "src/coordinator.cpp"],
        "D1 state build/parent contract",
    )
    melt = pinned("executed_cpp/melt_freeze.cpp")
    coord = pinned("executed_cpp/coordinator.cpp")
    prior_coord = pinned("executed_cpp/parent_coordinator.cpp")
    need(
        sha(prior_coord) == old["source_sha256"]["coordinator.cpp"],
        "parent coordinator source",
    )
    melt_block = pinned("producer/producer_fields.txt")
    need(
        melt.count(melt_block) == 1
        and melt.replace(melt_block, b"", 1)
        == parent.pinned("executed_cpp/melt_freeze.cpp"),
        "capture-only melt producer overlay",
    )
    for name in (
        "consumer_fields.txt",
        "reslope_before.txt",
        "reslope_after.txt",
        "entry_fields.txt",
    ):
        block = pinned("producer/" + name)
        need(coord.count(block) == 1, "unique consumer source block: " + name)
        coord = coord.replace(block, b"", 1)
    need(coord == prior_coord, "capture-only D1 consumer overlay")
    need(
        receipt["source_sha256"]["melt_freeze.cpp"] == sha(melt)
        and receipt["source_sha256"]["coordinator.cpp"]
        == sha(pinned("executed_cpp/coordinator.cpp")),
        "executed D1 state source hashes",
    )
    need(
        all(
            receipt["source_sha256"][n] == old["source_sha256"][n]
            for n in ("runtime.cpp", "sedimentation_conservative.cpp")
        ),
        "unchanged runtime/sedimentation source",
    )
    need(
        receipt["source_headers_sha256"] == old["source_headers_sha256"]
        and "-ffp-contract=off" in receipt["cxx_flags"],
        "D1 state headers and FP contract",
    )
    for name, expected in receipt["capture_blocks_sha256"].items():
        need(
            sha(pinned("producer/" + name)) == expected, "build capture block: " + name
        )
    need(
        receipt["runner_sha256"] == sha(pinned("producer/run.py.txt")),
        "D1 state runner source",
    )
    endpoints = set()
    for mode in ("off", "on"):
        run = json.loads(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = json.loads(session_raw)
        need(
            run["schema"] == "kdm6.native_d1_state_entry_run.v1"
            and run["mode"] == mode,
            "D1 state run schema/mode",
        )
        need(run["session_record_sha256"] == sha(session_raw), "D1 state run/session")
        need(
            run["source_sha256"] == receipt["source_sha256"]
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
            "D1 state source/object pins",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == receipt["new_executable_sha256"]
            and run["dso_sha256"]
            == session["library_candidate_sha256"]
            == receipt["new_dso_sha256"],
            "D1 state executable/DSO",
        )
        need(
            session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True
            and session["steps"] == 1
            and session["dt_seconds"] == 20,
            "completed D1 state host call",
        )
        need(
            any(
                "/native_d1_state_entry_20261104/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in s
                for s in session["loaded_library_lines"]
            ),
            "loaded isolated D1 state DSO",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"
            and run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "D1 state same input and prior endpoint",
        )
        need(
            run["captures"]
            == (
                {}
                if mode == "off"
                else {"native_qnice_applied_61367_runtime2.csv": manifest()[CAPTURE]}
            ),
            "D1 state off/on capture inventory",
        )
        endpoints.add(run["endpoint_sha256"])
    need(len(endpoints) == 1, "D1 state capture noninterference")
    return {
        "host_executable_sha256": receipt["new_executable_sha256"],
        "isolated_dso_sha256": receipt["new_dso_sha256"],
        "off_on_endpoint_sha256": endpoints.pop(),
        "capture_sha256": manifest()[CAPTURE],
    }


def scalar_state(
    fields: dict,
    k: int,
    parent,
    *,
    qv: float | None = None,
    t: float | None = None,
    qs: float | None = None,
    qg: float | None = None,
    rhox: float | None = None,
) -> dict:
    altered = fields
    if qs is not None or qg is not None or rhox is not None:
        altered = fields.copy()
        for name, candidate in (("qs", qs), ("qg", qg), ("rhox", rhox)):
            if candidate is not None:
                altered[(PRODUCER, name, k)] = {
                    **fields[(PRODUCER, name, k)],
                    "raw_hex": word(candidate),
                }
    p = parent.scalar_producer(altered, k, qv=qv, temperature=t)

    def x(name: str) -> float:
        return value(altered, PRODUCER, name, k)

    def c(name: str) -> float:
        return value(fields, CONSUMER, name, k)

    snow_gate = p["snow_active"] and x("qs") > x("qcrmin")
    graupel_gate = p["graupel_active"] and x("qg") > x("qcrmin")
    sfac_raw = ((x("rslope_s") * x("n0so")) * x("n0sfac")) / max(x("qs"), x("qcrmin"))
    gfac_raw = (x("rslope_g") * x("n0go")) / max(x("qg"), x("qcrmin"))
    sfac = sfac_raw if snow_gate else 0.0
    gfac = gfac_raw if graupel_gate else 0.0
    rhox_div = max(x("rhox"), 100.0)  # f64 path; constants::DENS in pinned header
    delta_brs = p["pgmlt"] / rhox_div if p["graupel_active"] else 0.0
    delta_brs_capped = p["pgmlt_capped_g"] / rhox_div if p["graupel_active"] else 0.0
    ps, pg = p["psmlt_capped_g"], p["pgmlt_capped_g"]
    warm_mask = 1.0 if p["warm"] else 0.0
    qr1 = c("qr_before") - ps * warm_mask
    qr2 = qr1 - pg * warm_mask
    nr1 = c("nr_before") - sfac * ps
    nr2 = nr1 - gfac * pg
    result = {
        "sfac_raw": sfac_raw,
        "sfac": sfac,
        "gfac_raw": gfac_raw,
        "gfac": gfac,
        "rhox_div": rhox_div,
        "delta_brs": delta_brs,
        "delta_brs_capped": delta_brs_capped,
        "warm_mask": warm_mask,
        "qs_after": x("qs") + ps,
        "qg_after": (x("qg") + pg) + c("pfrzdtr"),
        "qr1": qr1,
        "qr2": qr2,
        "qr_after": qr2 - c("pfrzdtr"),
        "nr1": nr1,
        "nr2": nr2,
        "nr_after": nr2 - c("nfrzdtr"),
        "brs_after": c("brs_before") + (delta_brs_capped + c("delta_brs_freeze")),
        "t_after": p["D1_T_out"],
        "ps": ps,
        "pg": pg,
    }
    return result


def baseline(fields: dict, parent) -> dict:
    altered_reslope = []
    mass_residuals = []
    for k in range(K):
        s = scalar_state(fields, k, parent)
        for name in ENTRY_FIELDS:
            check(
                fields,
                ENTRY,
                name,
                k,
                value(fields, CONSUMER, name + "_before", k),
                "independent D1 entry-to-consumer handoff: " + name,
            )
        for name in ("pfrzdtr", "nfrzdtr", "delta_brs_freeze"):
            need(
                fields[(CONSUMER, name, k)]["raw_hex"] == "0",
                "D1-only freeze amount must be +0: " + name,
            )
        for name in NEW_PRODUCER:
            check(
                fields, PRODUCER, name, k, s[name], "D1 sfac/gfac/BRS producer: " + name
            )
        for name in ("sfac_melt", "gfac_melt", "delta_brs_capped"):
            check(
                fields,
                CONSUMER,
                name,
                k,
                s[name.replace("_melt", "")],
                "D1 producer-to-consumer handoff: " + name,
            )
        for name in ("qs", "qg"):
            check(
                fields,
                PRODUCER,
                name,
                k,
                value(fields, CONSUMER, name + "_before", k),
                "D1 melt input handoff: " + name,
            )
        for name in ("psmlt_capped", "pgmlt_capped"):
            check(
                fields,
                "c3_pre_mf_d1",
                name,
                k,
                s["ps" if name.startswith("ps") else "pg"],
                "D1 applied mass handoff: " + name,
            )
        check(fields, CONSUMER, "warm_mask", k, s["warm_mask"], "D1 warm gate")
        for name in (
            "qs_after",
            "qg_after",
            "qr1",
            "qr2",
            "qr_after",
            "nr1",
            "nr2",
            "nr_after",
            "brs_after",
        ):
            check(fields, CONSUMER, name, k, s[name], "D1 actual state store: " + name)
        check(fields, RESLOPE, "brs_before", k, s["brs_after"], "D1 BRS reslope entry")
        before = sum(
            (
                Fraction(value(fields, CONSUMER, n + "_before", k))
                for n in ("qs", "qg", "qr")
            ),
            Fraction(),
        )
        after = sum(
            (
                Fraction(value(fields, CONSUMER, n + "_after", k))
                for n in ("qs", "qg", "qr")
            ),
            Fraction(),
        )
        mass_residuals.append(float(after - before))
        if (
            fields[(RESLOPE, "brs_before", k)]["raw_hex"]
            != fields[(RESLOPE, "brs_after", k)]["raw_hex"]
        ):
            altered_reslope.append(K - k)
    return {
        "levels_raw_bit_replayed": K,
        "native16": {
            name: value(fields, CONSUMER, name, TARGET) for name in CONSUMER_FIELDS
        },
        "native16_producer": {
            name: value(fields, PRODUCER, name, TARGET) for name in NEW_PRODUCER
        },
        "brs_reslope_changed_native_levels": altered_reslope,
        "max_abs_local_qs_qg_qr_mass_roundoff": max(map(abs, mass_residuals)),
        "native16_qs_qg_qr_mass_roundoff": mass_residuals[TARGET],
    }


def torch_state(
    base: dict,
    parent,
    qv: torch.Tensor,
    t: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    rhox: torch.Tensor,
) -> tuple:
    x = {**base, "qs": qs, "qg": qg, "rhox": rhox}
    producer, diag = parent.torch_producer(x, qv, t)
    ps, pg, tout = producer[2], producer[6], producer[7]
    qmin = x["qcrmin"]
    zero = torch.zeros_like(qs)
    snow_gate = diag["snow_active"] & (qs > qmin)
    graupel_gate = diag["graupel_active"] & (qg > qmin)
    sfac_raw = x["rslope_s"] * x["n0so"] * x["n0sfac"] / torch.clamp(qs, min=qmin)
    gfac_raw = x["rslope_g"] * x["n0go"] / torch.clamp(qg, min=qmin)
    sfac = torch.where(snow_gate, sfac_raw, zero)
    gfac = torch.where(graupel_gate, gfac_raw, zero)
    rhox_div = torch.clamp(rhox, min=100.0)
    delta_brs = torch.where(diag["graupel_active"], pg / x["dtcld"] / rhox_div, zero)
    delta_brs_capped = torch.where(diag["graupel_active"], pg / rhox_div, zero)
    warm_mask = (t > x["t0c"]).to(qs.dtype)
    qr1 = x["qr_before"] - ps * warm_mask
    qr2 = qr1 - pg * warm_mask
    nr1 = x["nr_before"] - sfac * ps
    nr2 = nr1 - gfac * pg
    out = torch.stack(
        (
            ps,
            pg,
            sfac,
            gfac,
            delta_brs,
            delta_brs_capped,
            qs + ps,
            (qg + pg) + x["pfrzdtr"],
            qr1,
            qr2,
            qr2 - x["pfrzdtr"],
            nr1,
            nr2,
            nr2 - x["nfrzdtr"],
            x["brs_before"] + (delta_brs_capped + x["delta_brs_freeze"]),
            tout,
        )
    )
    sig = (
        bool(qv > 1e-15),
        bool(t > x["t0c"]),
        bool(diag["snow_active"]),
        bool(diag["graupel_active"]),
        bool(diag["ps_dt"] > -qs),
        bool(diag["ps_dt"] < 0),
        bool(diag["pg_dt"] > -qg),
        bool(diag["pg_dt"] < 0),
        bool(qs > qmin),
        bool(qg > qmin),
        bool(rhox > 100.0),
        bool(diag["cpm"] > qmin),
    )
    return out, sig


def analytic(fields: dict, parent, direction: str) -> list[float]:
    def p(name: str) -> float:
        return value(fields, PRODUCER, name, TARGET)

    ps, pg = p("psmlt_capped_g"), p("pgmlt_capped_g")
    sf, gf, rh = p("sfac"), p("gfac"), p("rhox")
    dps = dpg = dsf = dgf = dqs = dqg = drh = dtout = 0.0
    if direction in ("relative_qv16", "absolute_t16"):
        tangent = parent.analytic_tangent(fields, direction)
        dps, dpg, dtout = tangent[2], tangent[6], tangent[7]
    elif direction == "relative_qs16":
        dqs, dsf = p("qs"), -sf
    elif direction == "relative_qg16":
        dqg, dgf = p("qg"), -gf
    elif direction == "relative_rhox16":
        drh = rh
    else:
        raise ValueError("unknown D1 state direction")
    dbrs = dpg / rh - pg * drh / (rh * rh)
    dbrs_rate = dbrs / p("dtcld")
    dqr1 = -dps
    dqr2 = dqr1 - dpg
    dnr1 = -(dsf * ps + sf * dps)
    dnr2 = dnr1 - (dgf * pg + gf * dpg)
    return [
        dps,
        dpg,
        dsf,
        dgf,
        dbrs_rate,
        dbrs,
        dqs + dps,
        dqg + dpg,
        dqr1,
        dqr2,
        dqr2,
        dnr1,
        dnr2,
        dnr2,
        dbrs,
        dtout,
    ]


def derivative(fields: dict, parent) -> dict:
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
        n: torch.tensor(value(fields, PRODUCER, n, TARGET), dtype=torch.float64)
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
        base[n] = torch.tensor(value(fields, CONSUMER, n, TARGET), dtype=torch.float64)
    qv = torch.tensor(
        value(fields, "c3_pre_mf_d1", "qv_before", TARGET), dtype=torch.float64
    )
    inputs = (qv, base["t"], base["qs"], base["qg"], base["rhox"])

    def fn(*args):
        return torch_state(base, parent, *args)[0]

    baseline_out, signature = torch_state(base, parent, *inputs)
    need(all(signature), "strict native16 D1 mass/number/BRS branch")
    for i, n in enumerate(STATE_OUTPUTS):
        stage = (
            PRODUCER
            if n in ("ps", "pg", "sfac", "gfac", "delta_brs", "delta_brs_capped")
            else CONSUMER
        )
        field = {
            "ps": "psmlt_capped_g",
            "pg": "pgmlt_capped_g",
            "t_after": "t_after_d1",
        }.get(n, n)
        if n == "t_after":
            stage = "c3_pre_mf_d1"
        check(
            fields,
            stage,
            field,
            TARGET,
            baseline_out[i].item(),
            "differentiable D1 state baseline: " + n,
        )
    weights = torch.tensor(
        (
            2.0,
            -3.0,
            5.0,
            7.0,
            11.0,
            -13.0,
            17.0,
            19.0,
            23.0,
            -29.0,
            31.0,
            -37.0,
            41.0,
            -43.0,
            47.0,
            53.0,
        ),
        dtype=torch.float64,
    )
    _, pullback = torch.func.vjp(fn, *inputs)
    pulled = pullback(weights)
    directions = {}
    for name, ix, seed, steps in (
        ("relative_qv16", 0, qv, (0.1, 0.01, 0.001)),
        ("absolute_t16", 1, torch.ones_like(inputs[1]), (0.1, 0.01, 0.001)),
        ("relative_qs16", 2, inputs[2], (0.01, 0.001, 0.0001)),
        ("relative_qg16", 3, inputs[3], (0.01, 0.001, 0.0001)),
        ("relative_rhox16", 4, inputs[4], (0.1, 0.01, 0.001)),
    ):
        tangent = tuple(
            seed if i == ix else torch.zeros_like(x) for i, x in enumerate(inputs)
        )
        _, jvp = torch.func.jvp(fn, inputs, tangent)
        expected = torch.tensor(analytic(fields, parent, name), dtype=torch.float64)
        need(
            torch.allclose(jvp, expected, rtol=2e-10, atol=2e-16),
            "independent D1 state analytic JVP: " + name,
        )
        vjp_dot = sum((v * t for v, t in zip(pulled, tangent))).item()
        jvp_dot = torch.dot(weights, jvp).item()
        need(
            abs(vjp_dot - jvp_dot) <= 2e-10 * max(1e-12, abs(jvp_dot)),
            "D1 state weighted VJP transpose: " + name,
        )
        finite_differences = {}
        for h in steps:
            plus = list(inputs)
            minus = list(inputs)
            plus[ix] = inputs[ix] + seed * h
            minus[ix] = inputs[ix] - seed * h
            high, hi_sig = torch_state(base, parent, *plus)
            low, lo_sig = torch_state(base, parent, *minus)
            need(
                hi_sig == signature and lo_sig == signature,
                "D1 state endpoint branch: " + name,
            )
            plus_kwargs = {("qv", "t", "qs", "qg", "rhox")[ix]: plus[ix].item()}
            minus_kwargs = {("qv", "t", "qs", "qg", "rhox")[ix]: minus[ix].item()}
            high_scalar = scalar_state(fields, TARGET, parent, **plus_kwargs)
            low_scalar = scalar_state(fields, TARGET, parent, **minus_kwargs)
            for i, output in enumerate(STATE_OUTPUTS):
                need(
                    word(high[i].item()) == word(high_scalar[output])
                    and word(low[i].item()) == word(low_scalar[output]),
                    "independent source-order D1 endpoint: " + output,
                )
            gap = (plus[ix].item() - minus[ix].item()) / seed.item()
            fd = (high - low) / gap
            errors = []
            for i in range(len(fd)):
                signal = abs(jvp[i].item())
                if signal > 1e-20:
                    err = abs(fd[i].item() - jvp[i].item()) / signal
                    roundoff = 16 * math.ulp(baseline_out[i].item()) / gap / signal
                    need(
                        err <= max(3 * h * h, roundoff + 2e-6),
                        "represented D1 state FD/JVP: " + name,
                    )
                    errors.append(err)
                else:
                    need(
                        abs(fd[i].item())
                        <= 16 * math.ulp(baseline_out[i].item()) / gap + 1e-24,
                        "zero D1 state FD signal: " + name,
                    )
            finite_differences[str(h)] = {
                "represented_input_gap": gap,
                "max_nonzero_relative_fd_jvp_error": max(errors, default=0.0),
                "jvp": jvp.tolist(),
                "fd": fd.tolist(),
            }
        directions[name] = {
            "jvp": jvp.tolist(),
            "analytic": expected.tolist(),
            "weighted_vjp_contraction": vjp_dot,
            "weighted_jvp_contraction": jvp_dot,
            "finite_differences": finite_differences,
        }
    return {
        "native_level_1based": 16,
        "output_order": list(STATE_OUTPUTS),
        "baseline_outputs": baseline_out.tolist(),
        "baseline_branch_signature": signature,
        "directions": directions,
        "fixed_inputs": "density, pressure, QI/NI, slopes/intercepts, work2, precg2, incoming QR/NR/BRS, geometry and substep schedule",
    }


def replay(
    *, capture_override: bytes | None = None, capture_sha: str | None = None
) -> dict:
    parent = parent_module()
    parent_result = parent.replay()
    need(
        parent_result["scientific_status"] == "INCONCLUSIVE", "verified parent producer"
    )
    source = source_and_run(parent)
    if capture_override is None:
        raw = pinned(CAPTURE)
    else:
        need(
            capture_sha is not None and sha(capture_override) == capture_sha,
            "test capture SHA-256",
        )
        raw = capture_override
    fields = load_capture(raw, parent)
    result = {
        "schema": "kdm6.native_d1_melt_state_ad.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "capture_rows": 7917,
        "prior_rows_raw_bit_equal": 6630,
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
            "stored D1 state summary",
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
        print("NATIVE_D1_MELT_STATE_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {k: result[k] for k in ("schema", "scientific_status", "capture_rows")},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
