#!/usr/bin/env python3
"""Verify archived actual C++/libtorch D1-to-ProgB local AD evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PARENT = REPO / "harness/evidence/native_d1_progb_ad_2026-11-04"
PARENT_REPLAY_SHA = "bacf2717352b67b30029d01e24a1d144c1458ac4775c3d87a949aca7664c8c1e"
MANIFEST_SHA = "1680e7797b925f4156797f009992edf0f3d2bf07a03ca8d6f6f63cf2b63ab0f1"
OUTPUT_ORDER = (
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
DIRECTIONS = {
    "relative_qv16": ("qv", 0, (0.1, 0.01, 0.001)),
    "absolute_t16": ("t", 1, (0.1, 0.01, 0.001)),
    "relative_qg16": ("qg", 2, (1e-5, 1e-6, 1e-7)),
    "relative_rhox16": ("rhox", 3, (1e-5, 1e-6, 1e-7)),
}
WEIGHTS = (2.0, -3.0, 5.0, 7.0, -11.0, 13.0, -17.0, 19.0, -23.0, 29.0)
BASELINE_FIELDS = (
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


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def word(value: float) -> str:
    return format(int.from_bytes(struct.pack("<d", value), "little"), "x")


def from_word(raw: str) -> float:
    value = struct.unpack("<d", int(raw, 16).to_bytes(8, "little"))[0]
    need(math.isfinite(value), "nonfinite binary64 word")
    return value


def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    data = {}
    for key, value in pairs:
        need(key not in data, "duplicate JSON key: " + key)
        data[key] = value
    return data


def parse_json(raw: bytes) -> dict:
    def bad_constant(value: str) -> None:
        raise ValueError("nonfinite JSON constant: " + value)

    data = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=bad_constant)
    need(isinstance(data, dict), "JSON object required")
    return data


def manifest() -> dict:
    raw = (HERE / "source_manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "C++ AD manifest SHA-256")
    return parse_json(raw)


def pinned(name: str) -> bytes:
    raw = (HERE / name).read_bytes()
    need(sha(raw) == manifest()[name], "C++ AD packet SHA-256: " + name)
    return raw


def parent_module():
    path = PARENT / "replay.py"
    need(sha(path.read_bytes()) == PARENT_REPLAY_SHA, "parent ProgB replay source")
    spec = importlib.util.spec_from_file_location("native_d1_progb_parent", path)
    need(spec is not None and spec.loader is not None, "parent ProgB import")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def finite_vector(value: object, count: int, label: str) -> list[float]:
    need(isinstance(value, list) and len(value) == count, label + " shape")
    need(
        all(type(x) in (float, int) and math.isfinite(x) for x in value),
        label + " finite binary64",
    )
    return [float(x) for x in value]


def parent_fields(parent):
    state_parent = parent.parent_module()
    producer = state_parent.parent_module()
    fields = parent.load_capture(parent.pinned(parent.CAPTURE), state_parent)
    return fields, state_parent, producer


def source_and_build(parent) -> dict:
    receipt = parse_json(pinned("raw/build_receipt.json"))
    parent_raw = parent.pinned("raw/build_receipt.json")
    parent_build = parse_json(parent_raw)
    need(
        receipt["schema"] == "kdm6.native_d1_progb_cpp_ad_build.v1"
        and receipt["parent_native_build_receipt_sha256"] == sha(parent_raw)
        and receipt["parent_native_archive_sha256"] == parent_build["archive_sha256"]
        and receipt["parent_native_dso_sha256"] == parent_build["new_dso_sha256"]
        and receipt["input_capture_sha256"] == sha(parent.pinned(parent.CAPTURE))
        and receipt["output_sha256"] == sha(pinned("raw/cpp_result.json")),
        "C++ AD parent archive/input/output identity",
    )
    need(
        receipt["source_sha256"]
        == {
            "cpp/main.cpp": sha(pinned("cpp/main.cpp")),
            "cpp/CMakeLists.txt": sha(pinned("cpp/CMakeLists.txt")),
        },
        "C++ AD source/CMake pins",
    )
    metadata = receipt["build_metadata_sha256"]
    need(
        set(metadata) == {"CMakeCache.txt", "flags.make", "link.txt"}
        and all(
            metadata[name] == sha(pinned("build_metadata/" + name)) for name in metadata
        ),
        "C++ AD build metadata pins",
    )
    flags = pinned("build_metadata/flags.make").decode()
    cache = pinned("build_metadata/CMakeCache.txt").decode()
    link = pinned("build_metadata/link.txt").decode()
    need(
        "-ffp-contract=off" in flags
        and "-DNDEBUG" not in flags
        and "CMAKE_BUILD_TYPE:STRING=Debug" in cache
        and "-DKDM6_CAPTURE_VARIANT=1" in flags
        and "/native_d1_progb_20261104/build/libkdm6.a" in link,
        "C++ AD compile/link contract",
    )
    need(
        receipt["run_exit_code"] == 0
        and receipt["run_command"][1].endswith(parent.CAPTURE)
        and receipt["run_command"][0].endswith("/native_d1_progb_cpp_ad")
        and receipt["torch_version"] == "2.13.0",
        "C++ AD completed run and Torch version",
    )
    hashes = (
        receipt["main_object_sha256"],
        receipt["executable_sha256"],
        *receipt["torch_libraries_sha256"].values(),
    )
    need(
        all(type(h) is str and re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)
        and set(receipt["torch_libraries_sha256"])
        == {"libtorch.dylib", "libtorch_cpu.dylib", "libc10.dylib"}
        and all(
            any(name in line for line in receipt["runtime_linked_libraries"])
            for name in ("libtorch.dylib", "libtorch_cpu.dylib", "libc10.dylib")
        ),
        "C++ AD object/executable/Torch library attestations",
    )
    return {
        "parent_native_archive_sha256": receipt["parent_native_archive_sha256"],
        "parent_native_dso_sha256": receipt["parent_native_dso_sha256"],
        "input_capture_sha256": receipt["input_capture_sha256"],
        "cpp_executable_sha256": receipt["executable_sha256"],
        "cpp_output_sha256": receipt["output_sha256"],
        "torch_version": receipt["torch_version"],
    }


def scalar_outputs(
    fields, state_parent, producer, parent, direction_key: str, endpoint: float
) -> tuple[list[float], dict]:
    state = state_parent.scalar_state(
        fields, parent.TARGET, producer, **{direction_key: endpoint}
    )
    prog = parent.scalar_progb(state["qg_after"], state["brs_after"])
    outputs = [
        state["ps"],
        state["pg"],
        state["qg_after"],
        state["brs_after"],
        state["nr_after"],
        prog["rhox"],
        prog["bg_new"],
        prog["avtg"],
        prog["bvtg"],
        state["t_after"],
    ]
    return outputs, prog


def analytic_outputs(fields, state_parent, producer, parent, name: str) -> list[float]:
    state = state_parent.analytic(fields, producer, name)
    prog = parent.analytic(fields, state_parent, producer, name)
    return [
        state[0],
        state[1],
        state[7],
        state[14],
        state[13],
        prog[3],
        prog[4],
        prog[5],
        prog[6],
        state[15],
    ]


def verify_output(raw: bytes, fields, state_parent, producer, parent) -> dict:
    saved = parse_json(raw)
    need(
        saved["schema"] == "kdm6.native_d1_progb_cpp_ad.v1"
        and saved["output_order"] == list(OUTPUT_ORDER)
        and set(saved["directions"]) == set(DIRECTIONS),
        "C++ AD schema/output inventory",
    )
    baseline = saved["baseline"]
    base = finite_vector(baseline["values"], len(OUTPUT_ORDER), "C++ baseline")
    words = baseline["raw_hex"]
    need(
        isinstance(words, list) and len(words) == len(base),
        "C++ baseline raw inventory",
    )
    for i, ((stage, field), value) in enumerate(zip(BASELINE_FIELDS, base)):
        need(
            type(words[i]) is str and words[i] == word(value),
            "C++ baseline value/raw word: " + OUTPUT_ORDER[i],
        )
        need(
            words[i] == fields[(stage, field, parent.TARGET)]["raw_hex"],
            "actual C++ baseline versus native capture: " + OUTPUT_ORDER[i],
        )

    input0 = {
        "qv": parent.value(fields, "c3_pre_mf_d1", "qv_before", parent.TARGET),
        "t": parent.value(fields, "d1_melt_producer", "t", parent.TARGET),
        "qg": parent.value(fields, "d1_melt_producer", "qg", parent.TARGET),
        "rhox": parent.value(fields, "d1_melt_producer", "rhox", parent.TARGET),
    }
    max_analytic_error = 0.0
    max_fd_normalized_error = 0.0
    for name, (key, index, steps) in DIRECTIONS.items():
        section = saved["directions"][name]
        seed = 1.0 if name == "absolute_t16" else input0[key]
        need(
            type(section["seed"]) in (float, int)
            and word(section["seed"]) == word(seed),
            "C++ AD input seed: " + name,
        )
        jvp = finite_vector(section["jvp"], len(OUTPUT_ORDER), "C++ JVP " + name)
        analytic = analytic_outputs(fields, state_parent, producer, parent, name)
        for i, output in enumerate(OUTPUT_ORDER):
            # QV/T co-move QG and BRS, so the ratio derivative cancels at
            # the source's floating-point resolution. Bound that residual
            # per direction/output rather than using one broad allowance.
            cancellation_allowance = {
                "relative_qv16": {"rhox": 2e-17, "avtg": 2e-18, "bvtg": 2e-22},
                "absolute_t16": {
                    "rhox": math.ulp(base[5]),
                    "avtg": 0.5 * math.ulp(base[7]),
                    "bvtg": 0.01 * math.ulp(base[8]),
                },
            }
            atol = cancellation_allowance.get(name, {}).get(output, 2e-18)
            err = abs(jvp[i] - analytic[i])
            need(
                err <= 2e-10 * abs(analytic[i]) + atol,
                "actual C++ versus independent analytic JVP: " + name + "/" + output,
            )
            max_analytic_error = max(max_analytic_error, err)
        vjp_dot, jvp_dot = section["vjp_dot"], section["jvp_dot"]
        need(
            type(vjp_dot) in (float, int)
            and type(jvp_dot) in (float, int)
            and math.isfinite(vjp_dot)
            and math.isfinite(jvp_dot),
            "finite C++ VJP/JVP dot",
        )
        products = [weight * tangent for weight, tangent in zip(WEIGHTS, jvp)]
        need(
            all(math.isfinite(term) for term in products),
            "finite weighted C++ JVP products: " + name,
        )
        expected_dot = math.fsum(products)
        scale = math.fsum(abs(term) for term in products)
        eps = 2.0**-53
        gamma = (len(products) * eps) / (1.0 - len(products) * eps)
        sum_tol = gamma * scale + 2.0 * math.ulp(expected_dot)
        need(
            abs(jvp_dot - expected_dot) <= sum_tol,
            "saved C++ JVP dot versus verified JVP vector: " + name,
        )
        # For VJP this is a fixed-packet consistency gate, not a general
        # rounding bound for the full reverse-mode tape.
        need(
            abs(vjp_dot - expected_dot) <= sum_tol,
            "saved C++ VJP dot versus verified JVP vector: " + name,
        )
        need(
            abs(vjp_dot - jvp_dot) <= 2e-10 * scale + 1e-14,
            "actual C++ VJP/JVP transpose: " + name,
        )
        need(
            set(map(float, section["finite_differences"])) == set(steps),
            "C++ FD step inventory: " + name,
        )
        for h_text, trial in section["finite_differences"].items():
            h = float(h_text)
            high = finite_vector(trial["high"], len(OUTPUT_ORDER), "C++ FD high")
            low = finite_vector(trial["low"], len(OUTPUT_ORDER), "C++ FD low")
            fd = finite_vector(trial["fd"], len(OUTPUT_ORDER), "C++ FD secant")
            upper = input0[key] + seed * h
            lower = input0[key] - seed * h
            gap = (upper - lower) / seed
            need(word(trial["gap"]) == word(gap), "represented C++ input gap: " + name)
            for output_values, endpoint in ((high, upper), (low, lower)):
                scalar, branch = scalar_outputs(
                    fields, state_parent, producer, parent, key, endpoint
                )
                need(
                    branch["active"]
                    and 800.0 < branch["rhox_op"] < 900.0
                    and branch["idx_left"] == 7
                    and branch["idx_right"] == 8,
                    "same ProgB branch at C++ FD endpoint: " + name,
                )
                for i, got in enumerate(output_values):
                    need(
                        word(got) == word(scalar[i]),
                        "actual C++ FD endpoint versus scalar replay: "
                        + name
                        + "/"
                        + OUTPUT_ORDER[i],
                    )
            for i, got in enumerate(fd):
                need(
                    abs(got - (high[i] - low[i]) / gap) <= 2 * math.ulp(got),
                    "saved C++ FD calculation: " + name + "/" + OUTPUT_ORDER[i],
                )
                residual = abs(got - jvp[i])
                bound = (
                    5 * h * h * abs(jvp[i]) + 64 * math.ulp(base[i]) / abs(gap) + 1e-20
                )
                need(
                    residual <= bound,
                    "actual C++ FD/JVP: " + name + "/" + OUTPUT_ORDER[i],
                )
                max_fd_normalized_error = max(
                    max_fd_normalized_error, residual / max(1.0, abs(jvp[i]))
                )

    cross = saved["qg_cross_cap"]
    high = finite_vector(cross["high"], len(OUTPUT_ORDER), "C++ crossing high")
    low = finite_vector(cross["low"], len(OUTPUT_ORDER), "C++ crossing low")
    for output_values, endpoint in (
        (high, input0["qg"] * 1.0001),
        (low, input0["qg"] * 0.9999),
    ):
        scalar, _ = scalar_outputs(
            fields, state_parent, producer, parent, "qg", endpoint
        )
        for i, got in enumerate(output_values):
            need(
                word(got) == word(scalar[i]),
                "actual C++ crossing endpoint versus scalar replay: " + OUTPUT_ORDER[i],
            )
    high_ratio, low_ratio = high[2] / high[3], low[2] / low[3]
    need(
        low_ratio < 900.0 < high_ratio and high[5] == 900.0 and low[5] < 900.0,
        "actual C++ QG cross-cap branch",
    )
    critical = (900.0 * base[3] - base[2]) / input0["qg"]
    need(1e-5 < critical < 1e-4, "actual C++ cap crossing threshold")
    return {
        "baseline_raw_bit_equal_outputs": len(OUTPUT_ORDER),
        "directions": list(DIRECTIONS),
        "max_abs_analytic_jvp_error": max_analytic_error,
        "max_normalized_fd_jvp_error": max_fd_normalized_error,
        "qg_upper_cap_critical_relative_step": critical,
        "qg_crossing_lower_raw_ratio": low_ratio,
        "qg_crossing_upper_raw_ratio": high_ratio,
        "qg_crossing_upper_selected_rhox": high[5],
    }


def replay(
    *, output_override: bytes | None = None, output_sha: str | None = None
) -> dict:
    parent = parent_module()
    parent_result = parent.replay()
    need(parent_result["scientific_status"] == "INCONCLUSIVE", "verified native parent")
    fields, state_parent, producer = parent_fields(parent)
    source = source_and_build(parent)
    if output_override is None:
        raw_output = pinned("raw/cpp_result.json")
    else:
        need(
            output_sha is not None and sha(output_override) == output_sha,
            "test C++ output SHA-256",
        )
        raw_output = output_override
    checked = verify_output(raw_output, fields, state_parent, producer, parent)
    result = {
        "schema": "kdm6.native_d1_progb_cpp_ad_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "source_and_build": source,
        "verified": checked,
    }
    if output_override is None and "results.json" in manifest():
        saved = parse_json(pinned("results.json"))
        need(
            saved["schema"] == result["schema"] and saved["verified"] == checked,
            "stored C++ AD summary",
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
        print("NATIVE_D1_PROGB_CPP_AD_REPLAY_PASSED")
        print(
            json.dumps(
                {k: result[k] for k in ("schema", "scientific_status")}, sort_keys=True
            )
        )


if __name__ == "__main__":
    main()
