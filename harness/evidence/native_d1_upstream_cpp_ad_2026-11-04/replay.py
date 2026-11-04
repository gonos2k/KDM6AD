#!/usr/bin/env python3
"""Replay native entry work2/ProgB production and archived C++ stage AD."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import platform
import re
import struct
import sys

import torch


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from oracle.kdm6.progb import (  # noqa: E402
    default_progb_params,
    progb_param_torch,
)
from oracle.kdm6.thermo import (  # noqa: E402
    compute_cpm,
    compute_work2_venfac,
    compute_xl,
    default_thermo_params,
)


PARENT = REPO / "harness/evidence/native_d1_progb_ad_2026-11-04"
PARENT_SOURCE_SHA = "bacf2717352b67b30029d01e24a1d144c1458ac4775c3d87a949aca7664c8c1e"
ORACLE_THERMO_SHA = "5278c14c6d87178af5ee963eef59d3297b923fa374412fd854c01e43ffb1b5cd"
ORACLE_PROGB_SHA = "d7ed7b46856ca6bf3b5558aa3cb2bacc1fb1b8e0201d32eb22f8ec4253ba5761"
CAPTURE = "raw/native_qnice_applied_42336_runtime2.csv"
MANIFEST_SHA = "d65f0e48ebef95d4ade29f4496d5ba2c07e4d90de268e1f01bef193b60cd5dca"
ORDER_SHA = "e8733cea1825d78a4aa6da37c1686b9b833ef981d07ca110701591d6681440ab"
K = 39
TARGET = 23
REFERENCE_MAX_ULPS = 128
ENTRY = "d1_upstream_entry"
PRODUCER = "d1_upstream_producer"
ENTRY_FIELDS = ("qg", "brs", "t", "qv", "p", "den", "dend")
PRODUCER_FIELDS = (
    "work2",
    "precg2",
    "rhox",
    "bg",
    "cpm",
    "xl",
    "avtg",
    "bvtg",
    "active_gate",
)
OUTPUT_ORDER = (
    "work2",
    "entry_precg2",
    "entry_rhox",
    "entry_brs",
    "entry_avtg",
    "entry_bvtg",
    "ps",
    "pg",
    "qg_d1",
    "brs_d1",
    "nr_d1",
    "rhox",
    "brs_reclamped",
    "avtg",
    "bvtg",
    "t_d1",
)
BASELINE_FIELDS = (
    (PRODUCER, "work2"),
    (PRODUCER, "precg2"),
    (PRODUCER, "rhox"),
    (PRODUCER, "bg"),
    (PRODUCER, "avtg"),
    (PRODUCER, "bvtg"),
    ("d1_melt_producer", "psmlt_capped_g"),
    ("d1_melt_producer", "pgmlt_capped_g"),
    ("d1_melt_consumer", "qg_after"),
    ("d1_melt_consumer", "brs_after"),
    ("d1_melt_consumer", "nr_after"),
    ("d1_postmelt_progb", "rhox"),
    ("d1_postmelt_progb", "bg_new"),
    ("d1_postmelt_progb", "avtg"),
    ("d1_postmelt_progb", "bvtg"),
    ("c3_pre_mf_d1", "t_after_d1"),
)
INPUTS = ("qv", "t", "qg", "brs", "p")
DIRECTIONS = {
    "relative_qv16": ("qv", (0.1, 0.01, 0.001)),
    "absolute_t16": ("t", (0.1, 0.01, 0.001)),
    "relative_qg16": ("qg", (1e-5, 1e-6, 1e-7)),
    "relative_brs_pre16": ("brs", (1e-5, 1e-6, 1e-7)),
    "relative_p16": ("p", (0.01, 0.001, 0.0001)),
}
WEIGHTS = (
    2.0,
    -3.0,
    5.0,
    7.0,
    -11.0,
    13.0,
    -17.0,
    19.0,
    -23.0,
    29.0,
    -31.0,
    37.0,
    -41.0,
    43.0,
    -47.0,
    53.0,
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def f64(raw_hex: str) -> float:
    value = struct.unpack("<d", int(raw_hex, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(value), "nonfinite upstream f64")
    return value


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(raw: bytes) -> dict:
    def nonfinite(value: str) -> None:
        raise ValueError("nonfinite JSON: " + value)

    result = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=nonfinite)
    need(type(result) is dict, "JSON object required")
    return result


def manifest() -> dict:
    raw = (HERE / "source_manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "upstream manifest SHA-256")
    return parse_json(raw)


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == manifest()[name], "upstream packet SHA-256: " + name)
    return raw


def parent_module():
    path = PARENT / "replay.py"
    need(sha(path.read_bytes()) == PARENT_SOURCE_SHA, "parent ProgB replay source")
    spec = importlib.util.spec_from_file_location("native_upstream_parent", path)
    need(spec is not None and spec.loader is not None, "parent ProgB import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def csv_rows(raw: bytes) -> tuple[list[str], list[dict]]:
    lines = raw.decode("ascii").splitlines()
    reader = csv.DictReader(
        io.StringIO(
            "\n".join([lines[0], *(x for x in lines[1:] if not x.startswith("#"))])
        )
    )
    need(
        reader.fieldnames is not None and len(reader.fieldnames) == 11,
        "upstream CSV header",
    )
    return lines, list(reader)


def load_capture(raw: bytes, parent) -> dict:
    need(len(raw) < 4 << 20 and raw.endswith(b"\n"), "upstream capture byte bound")
    lines, data = csv_rows(raw)
    old_lines, old_data = csv_rows(parent.pinned(parent.CAPTURE))
    need(
        len(lines) == 9520
        and len(data) == 9516
        and lines[0] == old_lines[0]
        and lines[1] == old_lines[1]
        and lines[2]
        == "# selected_runtime_call=2; first_one_step_call=2; selected_B_zero=27945; K=39; max_rows=10000; max_bytes=4194304"
        and lines[-1] == "# native_rows=9516,status=complete",
        "upstream capture inventory/header/footer",
    )
    old_keys = {(r["stage"], r["field"], int(r["k_zero"])) for r in old_data}
    expected = old_keys | {
        (stage, field, k)
        for stage, names in ((ENTRY, ENTRY_FIELDS), (PRODUCER, PRODUCER_FIELDS))
        for field in names
        for k in range(K)
    }
    need(len(expected) == 9516, "upstream expected row keys")
    fields, old_subsequence, order = {}, [], []
    for row in data:
        need(
            set(row) == set(data[0]) and None not in row.values(), "upstream row shape"
        )
        try:
            k, bits = int(row["k_zero"]), int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("upstream k/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < K
            and row["k_zero"] == str(k)
            and key in expected
            and key not in fields,
            "upstream row uniqueness",
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
            "upstream call/tile identity",
        )
        need(
            row["substep"]
            == ("1" if row["stage"] == "ice_sedimentation_conservative_n1" else "0"),
            "upstream substep",
        )
        need(
            row["raw_hex"] == format(bits, "x") and bits >= 0,
            "canonical upstream raw word",
        )
        if key in old_keys:
            old_subsequence.append(row)
        else:
            dtype = (
                "bool"
                if row["stage"] == PRODUCER and row["field"] == "active_gate"
                else "f64"
            )
            need(
                row["dtype"] == dtype and bits < (2 if dtype == "bool" else 1 << 64),
                "new upstream dtype/raw word",
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
        "complete upstream row inventory",
    )
    need(
        old_subsequence == old_data, "parent 8892 rows preserved in order and raw bits"
    )
    need(sha(("\n".join(order) + "\n").encode()) == ORDER_SHA, "upstream row order")
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


def same_reference_runtime() -> bool:
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and torch.__version__.split("+")[0] == "2.13.0"
    )


def check_reference_word(raw_hex: str, expected: float, why: str) -> float:
    """Keep local raw identity; bound cross-library oracle math in f64 ULPs."""
    recorded = f64(raw_hex)
    if same_reference_runtime():
        need(raw_hex == word(expected), why + ": same-runtime raw bit mismatch")
        return 0.0
    unit = max(math.ulp(recorded), math.ulp(expected))
    ulps = abs(recorded - expected) / unit
    need(
        ulps <= REFERENCE_MAX_ULPS,
        why + f": {ulps:.3g} ULP exceeds {REFERENCE_MAX_ULPS}",
    )
    return ulps


def source_and_runs(parent) -> dict:
    native = parse_json(pinned("raw/native_build_receipt.json"))
    parent_raw = parent.pinned("raw/build_receipt.json")
    prior = parse_json(parent_raw)
    need(
        native["schema"] == "kdm6.native_d1_upstream_cpp_build.v1"
        and native["parent_build_receipt_sha256"] == sha(parent_raw)
        and native["parent_dso_sha256"] == prior["new_dso_sha256"]
        and native["candidate"] == prior["candidate"]
        and native["only_source_change_vs_parent"] == ["src/coordinator.cpp"],
        "upstream native build/parent contract",
    )
    coord = pinned("executed_cpp/coordinator.cpp")
    for name in ("entry_fields.txt", "producer_fields.txt"):
        block = pinned("producer/" + name)
        need(coord.count(block) == 1, "unique upstream capture block: " + name)
        coord = coord.replace(block, b"", 1)
        need(
            native["capture_blocks_sha256"][name] == sha(block),
            "upstream capture block receipt",
        )
    need(
        coord == parent.pinned("executed_cpp/coordinator.cpp"),
        "capture-only upstream coordinator overlay",
    )
    need(
        native["source_sha256"]["coordinator.cpp"]
        == sha(pinned("executed_cpp/coordinator.cpp"))
        and all(
            native["source_sha256"][n] == prior["source_sha256"][n]
            for n in prior["source_sha256"]
            if n != "coordinator.cpp"
        )
        and native["source_headers_sha256"] == prior["source_headers_sha256"]
        and "-ffp-contract=off" in native["cxx_flags"]
        and native["runner_sha256"] == sha(pinned("producer/run.py.txt")),
        "upstream native source/header/runner/FP pins",
    )
    for mode in ("off", "on"):
        run = parse_json(pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json")
        session = parse_json(session_raw)
        need(
            run["schema"] == "kdm6.native_d1_upstream_run.v1"
            and run["mode"] == mode
            and run["session_record_sha256"] == sha(session_raw),
            "upstream run/session",
        )
        need(
            run["source_sha256"]
            == {n: native["source_sha256"][n] for n in run["source_sha256"]}
            and set(run["object_sha256"])
            == {
                "coordinator.cpp.o",
                "melt_freeze.cpp.o",
                "runtime.cpp.o",
                "sedimentation_conservative.cpp.o",
            }
            and all(
                run["object_sha256"][n] == native["object_sha256"][n]
                for n in run["object_sha256"]
            ),
            "upstream run source/object",
        )
        need(
            run["executable_sha256"]
            == session["executable_sha256"]
            == native["new_executable_sha256"]
            and run["dso_sha256"]
            == session["library_candidate_sha256"]
            == native["new_dso_sha256"]
            and session["status"] == "complete"
            and session["execution"]["experiment_valid"] is True
            and session["steps"] == 1
            and session["dt_seconds"] == 20,
            "upstream completed host/executable/DSO",
        )
        need(
            any(
                "/native_d1_upstream_20261104/host_bundle/libtorch/install/lib/libkdm6_c.2.0.0.dylib"
                in s
                for s in session["loaded_library_lines"]
            ),
            "loaded upstream isolated DSO",
        )
        need(
            run["origin_sha256"]
            == "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e"
            and run["endpoint_sha256"]
            == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
            "upstream same input/off-on/parent endpoint",
        )
        need(
            run["captures"]
            == (
                {}
                if mode == "off"
                else {"native_qnice_applied_42336_runtime2.csv": manifest()[CAPTURE]}
            ),
            "upstream capture inventory",
        )
    cpp = parse_json(pinned("raw/cpp_build_receipt.json"))
    need(
        cpp["schema"] == "kdm6.native_d1_upstream_cpp_ad_build.v1"
        and cpp["native_build_receipt_sha256"]
        == sha(pinned("raw/native_build_receipt.json"))
        and cpp["native_archive_sha256"] == native["archive_sha256"]
        and cpp["native_dso_sha256"] == native["new_dso_sha256"]
        and cpp["input_capture_sha256"] == sha(pinned(CAPTURE))
        and cpp["output_sha256"] == sha(pinned("raw/cpp_result.json")),
        "upstream C++ archive/input/output receipts",
    )
    need(
        cpp["source_sha256"]
        == {
            "cpp/main.cpp": sha(pinned("cpp/main.cpp")),
            "cpp/CMakeLists.txt": sha(pinned("cpp/CMakeLists.txt")),
        }
        and all(
            cpp["build_metadata_sha256"][n] == sha(pinned("build_metadata/" + n))
            for n in ("CMakeCache.txt", "flags.make", "link.txt")
        ),
        "upstream C++ source/build metadata",
    )
    flags = pinned("build_metadata/flags.make").decode()
    cache = pinned("build_metadata/CMakeCache.txt").decode()
    link = pinned("build_metadata/link.txt").decode()
    need(
        "-ffp-contract=off" in flags
        and "-DNDEBUG" not in flags
        and "-DKDM6_CAPTURE_VARIANT=1" in flags
        and "CMAKE_BUILD_TYPE:STRING=Debug" in cache
        and "/native_d1_upstream_20261104/build/libkdm6.a" in link,
        "upstream C++ compile/link contract",
    )
    need(
        cpp["run_exit_code"] == 0
        and cpp["run_command"][1].endswith(Path(CAPTURE).name)
        and cpp["run_command"][0].endswith("/native_d1_upstream_cpp_ad")
        and cpp["torch_version"] == "2.13.0"
        and set(cpp["torch_libraries_sha256"])
        == {"libtorch.dylib", "libtorch_cpu.dylib", "libc10.dylib"}
        and all(
            any(n in line for line in cpp["runtime_linked_libraries"])
            for n in cpp["torch_libraries_sha256"]
        ),
        "upstream C++ completed run/Torch",
    )
    for digest in (
        cpp["main_object_sha256"],
        cpp["executable_sha256"],
        *cpp["torch_libraries_sha256"].values(),
    ):
        need(
            type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest),
            "upstream C++ binary/library hash format",
        )
    return {
        "native_dso_sha256": native["new_dso_sha256"],
        "native_archive_sha256": native["archive_sha256"],
        "native_endpoint_sha256": "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        "capture_sha256": cpp["input_capture_sha256"],
        "cpp_executable_sha256": cpp["executable_sha256"],
        "cpp_output_sha256": cpp["output_sha256"],
        "torch_version": cpp["torch_version"],
    }


def upstream_baseline(fields: dict, parent) -> dict:
    need(
        sha((REPO / "oracle/kdm6/thermo.py").read_bytes()) == ORACLE_THERMO_SHA
        and sha((REPO / "oracle/kdm6/progb.py").read_bytes()) == ORACLE_PROGB_SHA,
        "pinned independent Python producer sources",
    )
    tensors = {
        n: torch.tensor(
            [[value(fields, ENTRY, n, k) for k in range(K)]], dtype=torch.float64
        )
        for n in ENTRY_FIELDS
    }
    entry = progb_param_torch(
        tensors["qg"], tensors["brs"], params=default_progb_params()
    )
    tp = default_thermo_params()
    work2 = compute_work2_venfac(tensors["p"], tensors["t"], tensors["den"], params=tp)
    cpm = compute_cpm(tensors["qv"], params=tp)
    xl = compute_xl(tensors["t"], params=tp)
    active_levels = []
    reference_ulps = {
        n: 0.0 for n in ("work2", "cpm", "xl", "precg2", "bg", "avtg", "bvtg", "rhox")
    }
    for k in range(K):
        check(
            fields,
            ENTRY,
            "qg",
            k,
            value(fields, "d1_melt_producer", "qg", k),
            "upstream QG handoff",
        )
        check(
            fields,
            ENTRY,
            "brs",
            k,
            value(fields, "d1_state_entry", "brs", k),
            "pre-reclamp BRS equals D1 entry in this call",
        )
        for name, stage, old in (
            ("t", "d1_melt_producer", "t"),
            ("qv", "c3_pre_mf_d1", "qv_before"),
            ("p", "d1_melt_producer", "p"),
            ("den", "d1_melt_producer", "den"),
            ("dend", "d1_melt_producer", "mass_den"),
        ):
            check(
                fields,
                ENTRY,
                name,
                k,
                value(fields, stage, old, k),
                "upstream input handoff: " + name,
            )
        for name, got in (
            ("work2", work2[0, k].item()),
            ("cpm", cpm[0, k].item()),
            ("xl", xl[0, k].item()),
            ("precg2", entry.precg2[0, k].item()),
            ("bg", entry.bg[0, k].item()),
            ("avtg", entry.avtg[0, k].item()),
            ("bvtg", entry.bvtg[0, k].item()),
        ):
            ulps = check_reference_word(
                fields[(PRODUCER, name, k)]["raw_hex"],
                got,
                "independent upstream Python producer: " + name,
            )
            reference_ulps[name] = max(reference_ulps[name], ulps)
        active = (
            value(fields, ENTRY, "qg", k) > 1e-9
            or value(fields, ENTRY, "brs", k) > 1e-15
        )
        check(fields, PRODUCER, "active_gate", k, active, "upstream ProgB active gate")
        if active:
            active_levels.append(K - k)
            ulps = check_reference_word(
                fields[(PRODUCER, "rhox", k)]["raw_hex"],
                entry.rhox[0, k].item(),
                "active upstream rhox",
            )
            reference_ulps["rhox"] = max(reference_ulps["rhox"], ulps)
        for name in ("work2", "precg2", "rhox", "cpm"):
            check(
                fields,
                PRODUCER,
                name,
                k,
                value(fields, "d1_melt_producer", name, k),
                "upstream-to-D1 consumed input: " + name,
            )
        check(
            fields,
            PRODUCER,
            "bg",
            k,
            value(fields, "d1_state_entry", "brs", k),
            "upstream BRS reclamp to D1",
        )
    need(TARGET == K - 16 and 16 in active_levels, "selected active upstream cell")
    return {
        "levels_thermo_progb_reference_checked": K,
        "same_runtime_exact_oracle_reference": same_reference_runtime(),
        "max_reference_ulp_by_field": reference_ulps,
        "active_rhox_native_levels": active_levels,
        "native16": {n: value(fields, PRODUCER, n, TARGET) for n in PRODUCER_FIELDS},
        "native16_input": {n: value(fields, ENTRY, n, TARGET) for n in ENTRY_FIELDS},
    }


def selected_input(fields: dict) -> dict:
    return {n: value(fields, ENTRY, n, TARGET) for n in ENTRY_FIELDS}


def scalar_endpoint(
    fields: dict, parent, state_parent, producer, input_values: dict
) -> tuple[list[float], dict]:
    x = input_values

    def t(name: str) -> torch.Tensor:
        return torch.tensor([[x[name]]], dtype=torch.float64)

    tp = default_thermo_params()
    pre = progb_param_torch(t("qg"), t("brs"), params=default_progb_params())
    work2 = compute_work2_venfac(t("p"), t("t"), t("den"), params=tp).item()
    entry = {
        n: getattr(pre, n).item() for n in ("precg2", "rhox", "bg", "avtg", "bvtg")
    }
    altered = fields.copy()
    for stage, name, new_value in (
        ("d1_melt_producer", "work2", work2),
        ("d1_melt_producer", "precg2", entry["precg2"]),
        ("d1_melt_producer", "rhox", entry["rhox"]),
        ("d1_melt_producer", "p", x["p"]),
        ("d1_melt_producer", "qg", x["qg"]),
        ("d1_melt_consumer", "brs_before", entry["bg"]),
    ):
        altered[(stage, name, TARGET)] = {
            **fields[(stage, name, TARGET)],
            "raw_hex": word(new_value),
        }
    state = state_parent.scalar_state(
        altered,
        TARGET,
        producer,
        qv=x["qv"],
        t=x["t"],
        qg=x["qg"],
        rhox=entry["rhox"],
    )
    melt = producer.scalar_producer(altered, TARGET, qv=x["qv"], temperature=x["t"])
    post = parent.scalar_progb(state["qg_after"], state["brs_after"])
    result = [
        work2,
        entry["precg2"],
        entry["rhox"],
        entry["bg"],
        entry["avtg"],
        entry["bvtg"],
        state["ps"],
        state["pg"],
        state["qg_after"],
        state["brs_after"],
        state["nr_after"],
        post["rhox"],
        post["bg_new"],
        post["avtg"],
        post["bvtg"],
        state["t_after"],
    ]
    branch = {
        "entry_active": x["qg"] > 1e-9 or x["brs"] > 1e-15,
        "entry_raw_ratio": x["qg"] / max(x["brs"], 1e-15),
        "entry_rhox": entry["rhox"],
        "post_active": post["active"],
        "post_raw_ratio": post["rhox_op"],
        "post_rhox": post["rhox"],
        "warm": melt["warm"],
        "snow_active": melt["snow_active"],
        "graupel_active": melt["graupel_active"],
        "snow_cap_open": -value(fields, "d1_melt_producer", "qs", TARGET)
        < melt["psmlt_dt"]
        < 0,
        "graupel_cap_open": -x["qg"] < melt["pgmlt_dt"] < 0,
    }
    return result, branch


def torch_dynamic(fields: dict, parent, state_parent, producer):
    base = parent.make_d1_base(fields, state_parent)
    den = torch.tensor(value(fields, ENTRY, "den", TARGET), dtype=torch.float64)
    tp, pp = default_thermo_params(), default_progb_params()

    def fn(
        qv: torch.Tensor,
        temperature: torch.Tensor,
        qg: torch.Tensor,
        brs: torch.Tensor,
        pressure: torch.Tensor,
    ) -> torch.Tensor:
        def shaped(x: torch.Tensor) -> torch.Tensor:
            return x.reshape((1, 1))

        entry = progb_param_torch(shaped(qg), shaped(brs), params=pp)
        work2 = compute_work2_venfac(
            shaped(pressure), shaped(temperature), shaped(den), params=tp
        ).reshape(())
        dynamic = {
            **base,
            "work2": work2,
            "precg2": entry.precg2.reshape(()),
            "rhox": entry.rhox.reshape(()),
            "brs_before": entry.bg.reshape(()),
            "p": pressure,
        }
        d1, _ = state_parent.torch_state(
            dynamic, producer, qv, temperature, base["qs"], qg, entry.rhox.reshape(())
        )
        post, _ = parent.torch_progb(d1[7], d1[14])
        return torch.stack(
            (
                work2,
                entry.precg2.reshape(()),
                entry.rhox.reshape(()),
                entry.bg.reshape(()),
                entry.avtg.reshape(()),
                entry.bvtg.reshape(()),
                d1[0],
                d1[1],
                d1[7],
                d1[14],
                d1[13],
                post[3],
                post[4],
                post[5],
                post[6],
                d1[15],
            )
        )

    return fn


def finite_vector(value_in: object, count: int, label: str) -> list[float]:
    need(type(value_in) is list and len(value_in) == count, label + " shape")
    need(
        all(type(x) in (float, int) and math.isfinite(x) for x in value_in),
        label + " finite values",
    )
    return [float(x) for x in value_in]


def verify_cpp_output(raw: bytes, fields: dict, parent, state_parent, producer) -> dict:
    saved = parse_json(raw)
    need(
        saved["schema"] == "kdm6.native_d1_upstream_cpp_ad.v1"
        and saved["output_order"] == list(OUTPUT_ORDER)
        and set(saved["directions"]) == set(DIRECTIONS),
        "upstream C++ output schema/directions",
    )
    base = finite_vector(
        saved["baseline"]["values"], len(OUTPUT_ORDER), "C++ upstream baseline"
    )
    raw_words = saved["baseline"]["raw_hex"]
    need(
        type(raw_words) is list and len(raw_words) == len(base),
        "C++ upstream baseline words",
    )
    for i, ((stage, field), got) in enumerate(zip(BASELINE_FIELDS, base)):
        need(
            type(raw_words[i]) is str
            and raw_words[i] == word(got)
            and raw_words[i] == fields[(stage, field, TARGET)]["raw_hex"],
            "actual C++ baseline/native raw bits: " + OUTPUT_ORDER[i],
        )
    x0 = selected_input(fields)
    fn = torch_dynamic(fields, parent, state_parent, producer)
    inputs = tuple(torch.tensor(x0[n], dtype=torch.float64) for n in INPUTS)
    oracle_base = fn(*inputs).tolist()
    max_oracle_baseline_ulps = 0.0
    for i, expected in enumerate(oracle_base):
        max_oracle_baseline_ulps = max(
            max_oracle_baseline_ulps,
            check_reference_word(
                word(base[i]),
                expected,
                "Python oracle/C++ upstream baseline: " + OUTPUT_ORDER[i],
            ),
        )
    max_oracle_jvp_error = 0.0
    max_fd_normalized_error = 0.0
    max_oracle_endpoint_ulps = 0.0
    for name, (key, steps) in DIRECTIONS.items():
        section = saved["directions"][name]
        seed = 1.0 if key == "t" else x0[key]
        need(
            type(section["seed"]) in (float, int)
            and word(section["seed"]) == word(seed),
            "C++ upstream direction seed: " + name,
        )
        jvp = finite_vector(section["jvp"], len(OUTPUT_ORDER), "upstream JVP " + name)
        tangent = tuple(
            x
            if n == key and key != "t"
            else torch.ones_like(x)
            if n == key
            else torch.zeros_like(x)
            for n, x in zip(INPUTS, inputs)
        )
        _, oracle_jvp = torch.func.jvp(fn, inputs, tangent)
        for i, output in enumerate(OUTPUT_ORDER):
            expected = oracle_jvp[i].item()
            # Near-zero postmelt density/table tangents are cancellation-scale.
            # Keep QV's observed f64 residual much tighter than a full output
            # ULP; T/P use explicit fractions of their output ULPs.
            cancellation_allowance = {
                "relative_qv16": {"rhox": 2e-17, "avtg": 2e-18, "bvtg": 2e-22},
                "absolute_t16": {
                    "rhox": 0.25 * math.ulp(base[11]),
                    "avtg": 0.1 * math.ulp(base[13]),
                    "bvtg": 0.01 * math.ulp(base[14]),
                },
                "relative_p16": {
                    "rhox": 0.25 * math.ulp(base[11]),
                    "avtg": 0.1 * math.ulp(base[13]),
                    "bvtg": 0.01 * math.ulp(base[14]),
                },
            }
            atol = cancellation_allowance.get(name, {}).get(output, 2e-18)
            err = abs(jvp[i] - expected)
            need(
                err <= 1e-12 * abs(expected) + atol,
                "actual C++ versus independent Python producer JVP: "
                + name
                + "/"
                + output,
            )
            max_oracle_jvp_error = max(max_oracle_jvp_error, err)
        # Independent smooth-branch expectations for the newly connected producers.
        if key == "p":
            need(
                abs(jvp[0] - 0.3333333 * base[0]) <= 2e-12,
                "source-derived relative-pressure work2 JVP",
            )
        if key == "t":
            temp = x0["t"]
            a = 0.3333333
            expected = base[0] * (
                (a - 0.5) * (1.5 / temp - 1.0 / (temp + 120.0)) - a * 1.81 / temp
            )
            need(
                abs(jvp[0] - expected) <= 2e-12, "source-derived temperature work2 JVP"
            )
        if key in ("qg", "brs"):
            expected = base[2] if key == "qg" else -base[2]
            need(abs(jvp[2] - expected) <= 2e-10, "source-derived entry-rhox JVP")
            need(abs(jvp[1]) > 1.0, "nonzero entry precg2 producer response")
        products = [w * j for w, j in zip(WEIGHTS, jvp)]
        need(
            all(math.isfinite(term) for term in products),
            "finite upstream weighted JVP",
        )
        expected_dot = math.fsum(products)
        scale = math.fsum(abs(term) for term in products)
        u = 2.0**-53
        gamma = len(products) * u / (1.0 - len(products) * u)
        tol = gamma * scale + 2.0 * math.ulp(expected_dot)
        # The VJP comparison is a fixed-packet consistency gate; gamma here
        # is not a universal error bound for the entire reverse-mode tape.
        need(
            abs(section["jvp_dot"] - expected_dot) <= tol
            and abs(section["vjp_dot"] - expected_dot) <= tol,
            "upstream C++ saved JVP/VJP dot versus checked JVP",
        )
        need(
            set(map(float, section["finite_differences"])) == set(steps),
            "upstream FD step inventory: " + name,
        )
        for h_text, trial in section["finite_differences"].items():
            h = float(h_text)
            high = finite_vector(trial["high"], len(OUTPUT_ORDER), "upstream FD high")
            low = finite_vector(trial["low"], len(OUTPUT_ORDER), "upstream FD low")
            fd = finite_vector(trial["fd"], len(OUTPUT_ORDER), "upstream FD secant")
            upper, lower = x0[key] + seed * h, x0[key] - seed * h
            gap = (upper - lower) / seed
            need(word(trial["gap"]) == word(gap), "upstream realized FD gap")
            for got, endpoint in ((high, upper), (low, lower)):
                x = {**x0, key: endpoint}
                scalar, branch = scalar_endpoint(
                    fields, parent, state_parent, producer, x
                )
                need(
                    branch["entry_active"]
                    and branch["post_active"]
                    and 800.0 < branch["entry_raw_ratio"] < 900.0
                    and 800.0 < branch["post_raw_ratio"] < 900.0
                    and branch["warm"]
                    and branch["snow_active"]
                    and branch["graupel_active"]
                    and branch["snow_cap_open"]
                    and branch["graupel_cap_open"]
                    and x["t"] > 1.0
                    and x["p"] > 0.0,
                    "same entry/D1/postmelt branches at upstream FD endpoint: " + name,
                )
                for i, output in enumerate(OUTPUT_ORDER):
                    max_oracle_endpoint_ulps = max(
                        max_oracle_endpoint_ulps,
                        check_reference_word(
                            word(got[i]),
                            scalar[i],
                            "actual C++ versus independent scalar upstream endpoint: "
                            + name
                            + "/"
                            + output,
                        ),
                    )
            for i, output in enumerate(OUTPUT_ORDER):
                need(
                    abs(fd[i] - (high[i] - low[i]) / gap) <= 2.0 * math.ulp(fd[i]),
                    "saved upstream C++ FD arithmetic: " + name + "/" + output,
                )
                residual = abs(fd[i] - jvp[i])
                bound = (
                    5 * h * h * abs(jvp[i]) + 64 * math.ulp(base[i]) / abs(gap) + 1e-20
                )
                need(
                    residual <= bound,
                    "actual upstream C++ FD/JVP: " + name + "/" + output,
                )
                max_fd_normalized_error = max(
                    max_fd_normalized_error, residual / max(1.0, abs(jvp[i]))
                )
    cross = saved["qg_cross_cap"]
    high = finite_vector(cross["high"], len(OUTPUT_ORDER), "upstream crossing high")
    low = finite_vector(cross["low"], len(OUTPUT_ORDER), "upstream crossing low")
    for got, endpoint in ((high, x0["qg"] * 1.0001), (low, x0["qg"] * 0.9999)):
        scalar, _ = scalar_endpoint(
            fields, parent, state_parent, producer, {**x0, "qg": endpoint}
        )
        for i, output in enumerate(OUTPUT_ORDER):
            max_oracle_endpoint_ulps = max(
                max_oracle_endpoint_ulps,
                check_reference_word(
                    word(got[i]),
                    scalar[i],
                    "upstream C++ cross-cap endpoint scalar replay: " + output,
                ),
            )
    need(
        high[2] == 900.0 and high[11] == 900.0 and low[2] < 900.0 and low[11] < 900.0,
        "separate entry/postmelt upper-cap crossing",
    )
    critical = (900.0 * x0["brs"] - x0["qg"]) / x0["qg"]
    need(1e-5 < critical < 1e-4, "upstream entry upper-cap threshold")
    return {
        "cpp_baseline_raw_bit_equal_outputs": len(OUTPUT_ORDER),
        "directions": list(DIRECTIONS),
        "max_abs_cpp_python_jvp_error": max_oracle_jvp_error,
        "max_cpp_python_baseline_ulps": max_oracle_baseline_ulps,
        "max_cpp_python_endpoint_ulps": max_oracle_endpoint_ulps,
        "max_normalized_cpp_fd_jvp_error": max_fd_normalized_error,
        "qg_entry_upper_cap_critical_relative_step": critical,
        "qg_crossing_entry_rhox_high": high[2],
        "qg_crossing_postmelt_rhox_high": high[11],
    }


def replay(
    *,
    cpp_output_override: bytes | None = None,
    cpp_output_sha: str | None = None,
    capture_override: bytes | None = None,
    capture_sha: str | None = None,
) -> dict:
    parent = parent_module()
    parent_result = parent.replay()
    need(parent_result["scientific_status"] == "INCONCLUSIVE", "verified parent ProgB")
    state_parent = parent.parent_module()
    producer = state_parent.parent_module()
    source = source_and_runs(parent)
    if capture_override is None:
        native_raw = pinned(CAPTURE)
    else:
        need(
            capture_sha is not None and sha(capture_override) == capture_sha,
            "test native upstream capture SHA-256",
        )
        native_raw = capture_override
    fields = load_capture(native_raw, parent)
    baseline = upstream_baseline(fields, parent)
    if cpp_output_override is None:
        cpp_raw = pinned("raw/cpp_result.json")
    else:
        need(
            cpp_output_sha is not None and sha(cpp_output_override) == cpp_output_sha,
            "test upstream C++ output SHA-256",
        )
        cpp_raw = cpp_output_override
    verified = verify_cpp_output(cpp_raw, fields, parent, state_parent, producer)
    result = {
        "schema": "kdm6.native_d1_upstream_cpp_ad_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "native_rows": 9516,
        "parent_rows_raw_bit_equal": 8892,
        "source_and_runs": source,
        "upstream_baseline": baseline,
        "verified_cpp": verified,
    }
    if (
        cpp_output_override is None
        and capture_override is None
        and "results.json" in manifest()
    ):
        saved = parse_json(pinned("results.json"))
        stable_baseline = ("active_rhox_native_levels", "native16", "native16_input")
        stable_cpp = (
            "cpp_baseline_raw_bit_equal_outputs",
            "directions",
            "qg_entry_upper_cap_critical_relative_step",
            "qg_crossing_entry_rhox_high",
            "qg_crossing_postmelt_rhox_high",
        )
        need(
            saved["schema"] == result["schema"]
            and saved["source_and_runs"] == source
            and all(
                saved["upstream_baseline"][n] == baseline[n] for n in stable_baseline
            )
            and all(saved["verified_cpp"][n] == verified[n] for n in stable_cpp),
            "stored upstream result summary",
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
        print("NATIVE_D1_UPSTREAM_CPP_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {k: result[k] for k in ("schema", "scientific_status", "native_rows")},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
