#!/usr/bin/env python3
"""Replay the native outer entry-cpm handoff and isolated C++ stage AD."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from oracle.kdm6.thermo import compute_cpm, default_thermo_params  # noqa: E402

PARENT = REPO / "harness/evidence/native_d1_slope_cpp_ad_2026-11-05"
PARENT_REPLAY_SHA = "a3dbd4f11b147dafd091f297d60cc930f8d0cfa73d9dae50d268a961f57ad8d8"
CAPTURE = "raw/native_qnice_applied_72033_runtime2.csv"
CAPTURE_SHA = "125e122ad7fff63bd1d4c30e5d9172f291fbd7c2758022c558ef7b204b01fbad"
CPP_SHA = "b2c92d70ab3d8e58d03a6ed6edbdceb5b8dbed537dc2e7cbfa0f294e409e4f4b"
NATIVE_RECEIPT_SHA = "1068f8124e3ebfb7026026d36054d7514c948ff5710da4e34b350b9e4f159d8b"
CPP_RECEIPT_SHA = "b1dca8f38ba4f4c01057e3d28ca9017339c1263533286667b210239d96506e05"
STARTUP_COMPARE_SHA = "3ffb9788b00174b1677bd727c4762d1c3f072cb7ae1c9bdd74b84a5a8fa78873"
RESULTS_SHA = "bf0038b6f00baab980d5f3728c544420c68c0b4ac2b06a5546a70b9479dce257"
K = 39
TARGET = 23
NEW_FIELDS = {
    "runtime_entry_thermo": ("qv_for_cpm", "entry_cpm"),
    "d1_entry_thermo": ("qv", "entry_cpm_arg", "fresh_cpm", "applied_cpm"),
}
INPUTS = ("qv_d1", "t", "qg", "brs", "p", "qs", "qv_outer")
DIRECTIONS = {
    "relative_qv_outer16": (("qv_outer",), (0.1, 0.01, 0.001)),
    "relative_qv_d1_16": (("qv_d1",), (0.1, 0.01, 0.001)),
    "relative_qv_joint16": (("qv_d1", "qv_outer"), (0.1, 0.01, 0.001)),
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
    -59.0,
    61.0,
    -67.0,
    71.0,
    -73.0,
    79.0,
    -83.0,
    89.0,
    -97.0,
    101.0,
    -103.0,
)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parent_module():
    need(
        sha((PARENT / "replay.py").read_bytes()) == PARENT_REPLAY_SHA,
        "pinned parent slope replay",
    )
    spec = importlib.util.spec_from_file_location(
        "native_entry_cpm_parent", PARENT / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "parent slope replay import")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned(name: str, digest: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == digest, "pinned entry-cpm file: " + name)
    return raw


def vector(raw: object, count: int, why: str) -> list[float]:
    need(type(raw) is list and len(raw) == count, why + " shape")
    need(
        all(type(x) in (float, int) and math.isfinite(x) for x in raw), why + " finite"
    )
    return [float(x) for x in raw]


def source_and_runs(upstream) -> dict:
    parse = upstream.parse_json
    native = parse(pinned("raw/native_build_receipt.json", NATIVE_RECEIPT_SHA))
    cpp = parse(pinned("raw/cpp_build_receipt.json", CPP_RECEIPT_SHA))
    old = parse(upstream.pinned("raw/native_build_receipt.json"))
    startup_compare = parse(
        pinned("raw/startup_origin_comparison.json", STARTUP_COMPARE_SHA)
    )
    bad_startup = [
        name
        for name, item in startup_compare["variables"].items()
        if not item["raw_bitwise_equal"]
    ]
    need(
        startup_compare["schema"] == "kdm6ad.native_replay_compare.v1"
        and startup_compare["variable_count_reference"] == 652
        and startup_compare["variable_count_candidate"] == 652
        and startup_compare["numeric_element_mismatches"] == 1
        and not startup_compare["raw_bitwise_equal"]
        and startup_compare["finite"]
        and startup_compare["complete_values"]
        and bad_startup == ["WE_JUST_D01_LBC"]
        and startup_compare["variables"]["WE_JUST_D01_LBC"]["reference_dtype"]
        == "int32"
        and startup_compare["variables"]["WE_JUST_D01_LBC"]["max_abs_difference"]
        == 1.0,
        "bounded origin-to-READY restart difference",
    )
    need(
        native["schema"] == "kdm6.native_d1_entry_cpm_build.v1"
        and native["candidate"]
        == {
            "native_ij_1based": [203, 149],
            "native_level_1based": 16,
            "b_zero": 27945,
            "B": 32248,
            "runtime_call": 2,
            "one_step_call": 2,
            "K": 39,
            "dt_seconds": 20,
        }
        and native["only_source_change_vs_parent"] == ["runtime.cpp", "coordinator.cpp"]
        and "-ffp-contract=off" in native["cxx_flags"],
        "native entry-cpm build contract",
    )
    need(
        native["parent_native_build_receipt_sha256"]
        == sha(upstream.pinned("raw/native_build_receipt.json"))
        and native["parent_dso_sha256"] == old["new_dso_sha256"]
        and native["parent_endpoint_sha256"]
        == "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070"
        and native["new_executable_sha256"] == old["new_executable_sha256"]
        and native["input_plan_sha256"]
        == "6032da73badc756c06410669d540daf53491afaa4f9705765ba7f270ac4343f7"
        and native["runner_sha256"] == sha((HERE / "producer/run.py.txt").read_bytes()),
        "native parent/source/run provenance",
    )
    for name in ("runtime.cpp", "coordinator.cpp", "thermo.cpp"):
        need(
            sha((HERE / "executed_cpp" / name).read_bytes())
            == native["source_sha256"][name],
            "executed entry-cpm source: " + name,
        )
    for name in ("melt_freeze.cpp", "sedimentation_conservative.cpp"):
        need(
            native["source_sha256"][name] == old["source_sha256"][name],
            "unchanged native source: " + name,
        )
    removal = {
        "runtime.cpp": (
            '    capture_native_tensor("runtime_entry_thermo", "qv_for_cpm", cur.qv, true);\n',
            '    capture_native_tensor("runtime_entry_thermo", "entry_cpm", entry_cpm, true);\n',
        ),
        "coordinator.cpp": (
            '    capture_native_tensor("d1_entry_thermo", "qv", state_pre.qv);\n',
            '    capture_native_tensor("d1_entry_thermo", "entry_cpm_arg", entry_cpm);\n',
            '    capture_native_tensor("d1_entry_thermo", "fresh_cpm", pre.cpm);\n',
            '    capture_native_tensor("d1_entry_thermo", "applied_cpm", pre.cpm);\n',
        ),
    }
    parent_sources = {
        "runtime.cpp": REPO
        / "harness/evidence/native_qnice_d1_qi_2026-11-03/executed_cpp/runtime.cpp",
        "coordinator.cpp": upstream.HERE / "executed_cpp/coordinator.cpp",
    }
    for name, lines in removal.items():
        text = (HERE / "executed_cpp" / name).read_text()
        for line in lines:
            need(text.count(line) == 1, "unique value-only capture insertion: " + name)
            text = text.replace(line, "", 1)
        need(
            text.encode() == parent_sources[name].read_bytes(),
            "capture-only native source change: " + name,
        )
    startup_by_mode = {}
    for mode in ("off", "on"):
        run = parse(pinned(f"raw/{mode}_run_result.json", RUN_SHAS[mode]))
        startup_by_mode[mode] = run["startup_sha256"]
        old_run = parse(upstream.pinned(f"raw/{mode}_run_result.json"))
        session_raw = pinned(f"raw/{mode}_live_session.json", SESSION_SHAS[mode])
        session = parse(session_raw)
        need(
            run["schema"] == "kdm6.native_d1_entry_cpm_run.v1"
            and run["mode"] == mode
            and run["dso_sha256"] == native["new_dso_sha256"]
            and run["executable_sha256"] == native["new_executable_sha256"]
            and run["source_sha256"]["runtime.cpp"]
            == native["source_sha256"]["runtime.cpp"]
            and run["source_sha256"]["coordinator.cpp"]
            == native["source_sha256"]["coordinator.cpp"]
            and run["object_sha256"]["runtime.cpp.o"]
            == native["object_sha256"]["runtime.cpp.o"]
            and run["object_sha256"]["coordinator.cpp.o"]
            == native["object_sha256"]["coordinator.cpp.o"]
            and run["session_record_sha256"] == sha(session_raw)
            and run["endpoint_sha256"] == native["parent_endpoint_sha256"]
            and run["origin_sha256"] == old_run["origin_sha256"]
            and run["startup_sha256"] == old_run["startup_sha256"],
            "same-build off/on native run: " + mode,
        )
        need(
            all(
                run["source_sha256"][name] == native["source_sha256"][name]
                for name in run["source_sha256"]
            )
            and all(
                run["object_sha256"][name] == native["object_sha256"][name]
                for name in run["object_sha256"]
            ),
            "run source/object actually linked: " + mode,
        )
        need(
            session["status"] == "complete"
            and session["executable_sha256"] == native["new_executable_sha256"]
            and session["library_candidate_sha256"] == native["new_dso_sha256"]
            and session["initial_sha256"] == run["origin_sha256"]
            and session["startup_sha256"] == run["startup_sha256"]
            and session["startup_origin_comparison"]["sha256"] == STARTUP_COMPARE_SHA
            and session["dt_seconds"] == 20
            and session["steps"] == 1,
            "native live session: " + mode,
        )
        if mode == "off":
            need(run["captures"] == {}, "capture-off inventory")
        else:
            need(
                run["captures"] == {Path(CAPTURE).name: CAPTURE_SHA},
                "capture-on exact file",
            )
    need(
        startup_by_mode["off"] == startup_by_mode["on"],
        "same READY checkpoint for capture off/on",
    )
    need(
        cpp["schema"] == "kdm6.native_d1_entry_cpm_cpp_ad_build.v1"
        and cpp["build_type"] == "Debug"
        and cpp["run_exit_code"] == 0
        and "-ffp-contract=off" in cpp["cxx_flags"]
        and "NDEBUG" not in cpp["cxx_flags"]
        and cpp["native_archive_sha256"] == native["archive_sha256"]
        and cpp["native_dso_sha256"] == native["new_dso_sha256"]
        and cpp["native_build_receipt_sha256"] == NATIVE_RECEIPT_SHA
        and cpp["input_capture_sha256"] == CAPTURE_SHA
        and cpp["output_sha256"] == CPP_SHA
        and cpp["torch_version"] == "2.13.0",
        "isolated C++ entry-cpm lineage",
    )
    need(
        set(cpp["source_sha256"])
        == {"cpp/main.cpp", "cpp/CMakeLists.txt", "executed_cpp/thermo.cpp"},
        "entry-cpm C++ source inventory",
    )
    for name, digest in cpp["source_sha256"].items():
        need(sha((HERE / name).read_bytes()) == digest, "C++ entry-cpm source: " + name)
    need(
        set(cpp["build_metadata_sha256"])
        == {"CMakeCache.txt", "flags.make", "link.txt"},
        "C++ metadata inventory",
    )
    for name, digest in cpp["build_metadata_sha256"].items():
        need(
            sha((HERE / "build_metadata" / name).read_bytes()) == digest,
            "C++ build metadata: " + name,
        )
    need(
        set(cpp["torch_libraries_sha256"])
        == {"libc10.dylib", "libtorch.dylib", "libtorch_cpu.dylib"}
        and all(len(x) == 64 for x in cpp["torch_libraries_sha256"].values())
        and len(cpp["runtime_linked_libraries"]) >= 3
        and len(cpp["main_object_sha256"]) == 64
        and len(cpp["executable_sha256"]) == 64,
        "isolated C++ binary/library hash inventory",
    )
    return {
        "native_dso_sha256": native["new_dso_sha256"],
        "native_endpoint_sha256": native["parent_endpoint_sha256"],
        "origin_to_ready_mismatch": "WE_JUST_D01_LBC:int32:one_element",
        "cpp_executable_sha256": cpp["executable_sha256"],
        "cpp_output_sha256": CPP_SHA,
    }


RUN_SHAS = {
    "off": "1937c2e0b8e2b2bf91e5b8001b57a274bd41f8b7428f586c36431cecadecb3d5",
    "on": "fbbe89567d89959421eeeac5e311459240d4d958463b82ac35b6ad280cafbb0f",
}
SESSION_SHAS = {
    "off": "5366e609d2027f1e20afd52a6847303f02881255b4098e6f822f9bb7ba71fe9a",
    "on": "6f030839dc41cc412e28c1f104d18fd6ec21a689d375008d545eb0e19a1dffbf",
}


def load_capture(raw: bytes, upstream) -> dict:
    old_lines, old_rows = upstream.csv_rows(upstream.pinned(upstream.CAPTURE))
    lines, rows = upstream.csv_rows(raw)
    need(
        len(lines) == 9754
        and len(rows) == 9750
        and lines[:3] == old_lines[:3]
        and lines[-1] == "# native_rows=9750,status=complete",
        "entry-cpm capture header/count/footer",
    )
    new_keys = {
        (stage, field, k)
        for stage, names in NEW_FIELDS.items()
        for field in names
        for k in range(K)
    }
    new_order = [
        (stage, field, k)
        for stage, names in NEW_FIELDS.items()
        for field in names
        for k in range(K)
    ]
    new_rows = []
    old_subsequence = []
    fields = {}
    for row in rows:
        need(set(row) == set(rows[0]) and None not in row.values(), "capture row shape")
        try:
            k = int(row["k_zero"])
            int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("entry-cpm k/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < K and row["k_zero"] == str(k) and key not in fields,
            "entry-cpm unique level/field",
        )
        fields[key] = row
        if row["stage"] in NEW_FIELDS:
            need(
                key in new_keys
                and row["dtype"] == "f64"
                and math.isfinite(upstream.f64(row["raw_hex"]))
                and row["substep"] == "0"
                and (
                    row["one_step_call"],
                    row["runtime_call"],
                    row["b_zero"],
                    row["B"],
                    row["K"],
                )
                == ("2", "2", "27945", "32248", "39"),
                "entry-cpm new row identity",
            )
            new_rows.append(row)
        else:
            old_subsequence.append(row)
    need(
        old_subsequence == old_rows
        and len(new_rows) == len(new_keys)
        and [(r["stage"], r["field"], int(r["k_zero"])) for r in new_rows] == new_order,
        "old 9516 rows preserved, six new 39-level fields",
    )
    return fields


def val(fields: dict, stage: str, field: str, k: int, upstream) -> float:
    return upstream.f64(fields[stage, field, k]["raw_hex"])


def verify_handoff(fields: dict, upstream) -> dict:
    for k in range(K):

        def bits(stage, field):
            return fields[stage, field, k]["raw_hex"]

        need(
            bits("runtime_entry_pre_clamp", "qv")
            == bits("runtime_entry_thermo", "qv_for_cpm")
            == bits("d1_entry_thermo", "qv")
            == bits("d1_upstream_entry", "qv"),
            "outer-to-D1 QV handoff",
        )
        q = val(fields, "runtime_entry_thermo", "qv_for_cpm", k, upstream)
        qsafe = max(q, 1.0e-15)
        expected = 1004.5 * (1.0 - qsafe) + 1846.4 * qsafe
        need(
            bits("runtime_entry_thermo", "entry_cpm") == upstream.word(expected),
            "independent outer entry-cpm producer",
        )
        need(
            bits("runtime_entry_thermo", "entry_cpm")
            == bits("d1_entry_thermo", "entry_cpm_arg")
            == bits("d1_entry_thermo", "applied_cpm")
            == bits("d1_upstream_producer", "cpm")
            == bits("d1_melt_producer", "cpm")
            == bits("c3_pre_mf_d1", "pre_cpm"),
            "outer entry-cpm to D1 consumed word",
        )
        qd1 = val(fields, "d1_entry_thermo", "qv", k, upstream)
        fresh = 1004.5 * (1.0 - max(qd1, 1.0e-15)) + 1846.4 * max(qd1, 1.0e-15)
        need(
            bits("d1_entry_thermo", "fresh_cpm") == upstream.word(fresh),
            "independent one-step preamble cpm",
        )
        need(
            bits("d1_entry_thermo", "fresh_cpm")
            == bits("d1_entry_thermo", "applied_cpm"),
            "first-subcycle fresh/applied cpm identity",
        )
    return {
        "levels_raw_bit_joined": K,
        "native16_outer_qv": val(
            fields, "runtime_entry_thermo", "qv_for_cpm", TARGET, upstream
        ),
        "native16_entry_cpm": val(
            fields, "runtime_entry_thermo", "entry_cpm", TARGET, upstream
        ),
        "fresh_equals_applied_levels": K,
    }


def dynamic(fields: dict, slope_parent, upstream, progb_parent, state_parent, producer):
    old = slope_parent.dynamic(fields, upstream, progb_parent, state_parent, producer)
    tp = default_thermo_params()

    def fn(qv_d1, t, qg, brs, p, qs, qv_outer):
        # Reuse only the parent's selected 25 outputs: after the cpm override,
        # none reads CoordinatorState.qv directly. The separate fresh-cpm output
        # below uses qv_d1. Later saturation/state outputs need a reference that
        # threads state QV and outer cpm as distinct arguments.
        legacy = old(qv_outer, t, qg, brs, p, qs)
        entry = compute_cpm(qv_outer.reshape((1, 1)), params=tp).reshape(())
        fresh = compute_cpm(qv_d1.reshape((1, 1)), params=tp).reshape(())
        return torch.cat((legacy, torch.stack((entry, fresh))))

    return fn


def verify_cpp(
    raw: bytes,
    fields: dict,
    slope_parent,
    upstream,
    progb_parent,
    state_parent,
    producer,
) -> dict:
    saved = upstream.parse_json(raw)
    order = (
        list(upstream.OUTPUT_ORDER)
        + list(slope_parent.SLOPE_FIELDS)
        + ["entry_cpm", "fresh_cpm"]
    )
    need(
        saved["schema"] == "kdm6.native_d1_entry_cpm_cpp_ad.v1"
        and saved["output_order"] == order
        and set(saved["directions"]) == set(DIRECTIONS),
        "entry-cpm C++ output schema",
    )
    base = vector(saved["baseline"]["values"], 27, "entry-cpm baseline")
    words = saved["baseline"]["raw_hex"]
    need(type(words) is list and len(words) == 27, "entry-cpm baseline words")
    old = upstream.parse_json((slope_parent.HERE / "raw/cpp_result.json").read_bytes())
    for i, got in enumerate(base):
        expected = (
            old["baseline"]["raw_hex"][i]
            if i < 25
            else fields[("runtime_entry_thermo", "entry_cpm", TARGET)]["raw_hex"]
            if i == 25
            else fields[("d1_entry_thermo", "fresh_cpm", TARGET)]["raw_hex"]
        )
        need(
            words[i] == upstream.word(got) == expected,
            "actual C++/native entry-cpm baseline raw bits: " + order[i],
        )
    fn = dynamic(fields, slope_parent, upstream, progb_parent, state_parent, producer)
    x0 = {
        "qv_d1": val(fields, "d1_entry_thermo", "qv", TARGET, upstream),
        "t": val(fields, "d1_upstream_entry", "t", TARGET, upstream),
        "qg": val(fields, "d1_upstream_entry", "qg", TARGET, upstream),
        "brs": val(fields, "d1_upstream_entry", "brs", TARGET, upstream),
        "p": val(fields, "d1_upstream_entry", "p", TARGET, upstream),
        "qs": val(fields, "d1_melt_producer", "qs", TARGET, upstream),
        "qv_outer": val(fields, "runtime_entry_thermo", "qv_for_cpm", TARGET, upstream),
    }
    x = tuple(torch.tensor(x0[name], dtype=torch.float64) for name in INPUTS)
    py_base = vector(fn(*x).tolist(), 27, "independent entry-cpm baseline")
    for i, expected in enumerate(py_base):
        upstream.check_reference_word(
            words[i], expected, "entry-cpm Python/C++ baseline: " + order[i], max_ulps=0
        )
    parent_qv = old["directions"]["relative_qv16"]["jvp"]
    max_jvp_err = max_fd_norm = max_endpoint_ulps = 0.0
    for name, (changed, steps) in DIRECTIONS.items():
        section = saved["directions"][name]
        seed = x0[changed[0]]
        need(
            upstream.word(section["seed"]) == upstream.word(seed),
            "entry-cpm direction seed",
        )
        tangent = tuple(
            xi if key in changed else torch.zeros_like(xi) for key, xi in zip(INPUTS, x)
        )
        _, py_jvp = torch.func.jvp(fn, x, tangent)
        jvp = vector(section["jvp"], 27, "entry-cpm C++ JVP")
        for i, expected in enumerate(py_jvp.tolist()):
            error = abs(jvp[i] - expected)
            tol = 1e-10 * abs(expected) + max(2e-18, 0.25 * math.ulp(base[i]))
            need(error <= tol, "entry-cpm C++/Python JVP: " + name + "/" + order[i])
            max_jvp_err = max(max_jvp_err, error)
        dcpm = (1846.4 - 1004.5) * seed
        if name == "relative_qv_outer16":
            need(abs(jvp[25] - dcpm) < 2e-12 and jvp[26] == 0, "outer-only cpm tangent")
        elif name == "relative_qv_d1_16":
            need(
                jvp[25] == 0
                and abs(jvp[26] - dcpm) < 2e-12
                and all(x == 0 for x in jvp[:25]),
                "D1-only fresh cpm tangent",
            )
        else:
            need(
                abs(jvp[25] - dcpm) < 2e-12 and abs(jvp[26] - dcpm) < 2e-12,
                "joint outer/D1 cpm tangent",
            )
            need(
                jvp[:25] == parent_qv,
                "joint first25 JVP equals prior same-source direction",
            )
        products = [w * y for w, y in zip(WEIGHTS, jvp)]
        dot = math.fsum(products)
        u = 2.0**-53
        gamma = len(products) * u / (1 - len(products) * u)
        dot_tol = gamma * math.fsum(map(abs, products)) + 2 * math.ulp(dot)
        need(
            abs(section["jvp_dot"] - dot) <= dot_tol
            and abs(section["vjp_dot"] - dot) <= dot_tol,
            "entry-cpm weighted VJP/JVP dots versus checked tangent: " + name,
        )
        need(
            set(map(float, section["finite_differences"])) == set(steps),
            "entry-cpm FD step inventory",
        )
        for h_text, trial in section["finite_differences"].items():
            h = float(h_text)
            high = vector(trial["high"], 27, "entry-cpm high")
            low = vector(trial["low"], 27, "entry-cpm low")
            fd = vector(trial["fd"], 27, "entry-cpm FD")
            up, down = {**x0}, {**x0}
            for key in changed:
                up[key] = x0[key] + seed * h
                down[key] = x0[key] - seed * h
            gap = (up[changed[0]] - down[changed[0]]) / seed
            need(
                upstream.word(trial["gap"]) == upstream.word(gap),
                "entry-cpm realized FD gap",
            )
            if len(changed) == 2:
                need(
                    (up[changed[1]] - down[changed[1]]) / seed == gap,
                    "joint realized FD gap",
                )
            for got, endpoint in ((high, up), (low, down)):
                py = vector(
                    fn(
                        *(
                            torch.tensor(endpoint[n], dtype=torch.float64)
                            for n in INPUTS
                        )
                    ).tolist(),
                    27,
                    "independent entry-cpm endpoint",
                )
                need(
                    endpoint["qv_outer"] > 1e-15 and endpoint["qv_d1"] > 1e-15,
                    "outer/D1 qv cpm floor inactive",
                )
                need(
                    800 < py[2] < 900
                    and 800 < py[11] < 900
                    and -endpoint["qs"] < py[6] < 0
                    and -endpoint["qg"] < py[7] < 0
                    and py[16] == 1.0,
                    "same D1/progb/slope branches",
                )
                for i, expected in enumerate(py):
                    ulps = upstream.check_reference_word(
                        upstream.word(got[i]),
                        expected,
                        "entry-cpm C++/Python endpoint: " + name + "/" + order[i],
                        max_ulps=(
                            4
                            if order[i]
                            in upstream.ENDPOINT_PORTABLE_ULPS
                            | slope_parent.SLOPE_ENDPOINT_PORTABLE
                            else 0
                        ),
                    )
                    max_endpoint_ulps = max(max_endpoint_ulps, ulps)
            for i, output in enumerate(order):
                need(
                    abs(fd[i] - (high[i] - low[i]) / gap) <= 2 * math.ulp(fd[i]),
                    "entry-cpm saved FD arithmetic: " + name + "/" + output,
                )
                residual = abs(fd[i] - jvp[i])
                bound = (
                    10 * h * h * abs(jvp[i])
                    + 128 * math.ulp(base[i]) / abs(gap)
                    + 1e-18
                )
                need(residual <= bound, "entry-cpm C++ FD/JVP: " + name + "/" + output)
                max_fd_norm = max(max_fd_norm, residual / max(1.0, abs(jvp[i])))
    return {
        "baseline_raw_bit_equal_outputs": 27,
        "directions": list(DIRECTIONS),
        "max_cpp_python_jvp_abs": max_jvp_err,
        "max_endpoint_ulps": max_endpoint_ulps,
        "max_fd_normalized": max_fd_norm,
        "joint_first25_jvp_equals_parent": True,
    }


def replay(
    *,
    capture_override: bytes | None = None,
    capture_sha: str | None = None,
    output_override: bytes | None = None,
    output_sha: str | None = None,
) -> dict:
    slope_parent = parent_module()
    parent_result = slope_parent.replay()
    need(parent_result["scientific_status"] == "INCONCLUSIVE", "verified slope parent")
    upstream = slope_parent.parent_module()
    progb_parent = upstream.parent_module()
    state_parent = progb_parent.parent_module()
    producer = state_parent.parent_module()
    source = source_and_runs(upstream)
    if capture_override is None:
        capture_raw = pinned(CAPTURE, CAPTURE_SHA)
    else:
        need(
            capture_sha is not None and sha(capture_override) == capture_sha,
            "test entry-cpm capture SHA",
        )
        capture_raw = capture_override
    fields = load_capture(capture_raw, upstream)
    handoff = verify_handoff(fields, upstream)
    if output_override is None:
        output_raw = pinned("raw/cpp_result.json", CPP_SHA)
    else:
        need(
            output_sha is not None and sha(output_override) == output_sha,
            "test entry-cpm C++ output SHA",
        )
        output_raw = output_override
    verified = verify_cpp(
        output_raw, fields, slope_parent, upstream, progb_parent, state_parent, producer
    )
    result = {
        "schema": "kdm6.native_d1_entry_cpm_cpp_ad_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "native_rows": 9750,
        "parent_rows_raw_bit_equal": 9516,
        "source_and_runs": source,
        "handoff": handoff,
        "verified_cpp": verified,
    }
    if capture_override is None and output_override is None:
        saved = upstream.parse_json(pinned("results.json", RESULTS_SHA))
        stable = (
            "schema",
            "scientific_status",
            "physical_unit_status",
            "native_rows",
            "parent_rows_raw_bit_equal",
            "source_and_runs",
            "handoff",
        )
        need(
            all(saved[k] == result[k] for k in stable)
            and saved["verified_cpp"]["baseline_raw_bit_equal_outputs"] == 27
            and saved["verified_cpp"]["joint_first25_jvp_equals_parent"],
            "saved entry-cpm stable result",
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cr = args.capture.read_bytes() if args.capture else None
    oo = args.output.read_bytes() if args.output else None
    result = replay(
        capture_override=cr,
        capture_sha=sha(cr) if cr else None,
        output_override=oo,
        output_sha=sha(oo) if oo else None,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
