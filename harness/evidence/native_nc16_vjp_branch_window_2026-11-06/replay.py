#!/usr/bin/env python3
"""Replay a one-hot NC16 C ABI VJP against saved JVPs and branch-aware FDs."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
BRANCH = HERE.parent / "native_fd_outlier_branches_2026-11-05"
STATE_AD = HERE.parent / "skipped_substep_ad_2026-11-05"
MANIFEST_SHA = "8c20d6bac0371e3d95b6a4c55cedee36d9958c49b97e5e5382d095a843712432"
BRANCH_REPLAY_SHA = "ba850281ca865f682f4c134ca31e2ee52663b16e56529b5f6007b4cf09323b34"
STATE_FIELDS = (
    "th",
    "qv",
    "qc",
    "qr",
    "qi",
    "qs",
    "qg",
    "nccn",
    "nc",
    "ni",
    "nr",
    "bg",
)
FIELD = {"qv": 1, "qs": 5, "qg": 6}
LOCAL = {"qv": (1e-4, 1e-5), "qs": (1e-3, 1e-4), "qg": (1e-6, 1e-7)}
CROSSING = {"qv": 1e-3, "qg": 1e-5}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def branch_module():
    need(
        sha((BRANCH / "replay.py").read_bytes()) == BRANCH_REPLAY_SHA,
        "pinned branch-trace replay",
    )
    spec = importlib.util.spec_from_file_location(
        "native_fd_branch_parent", BRANCH / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "branch module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned NC16 VJP manifest")
    data = json.loads(raw)
    need(
        data["schema"] == "kdm6.native_nc16_vjp_branch_window_packet.v1",
        "manifest schema",
    )
    files = data["files"]
    actual = {
        str(p.relative_to(HERE))
        for folder in ("raw", "producer", "executed_cpp", "build_metadata")
        for p in (HERE / folder).rglob("*")
        if p.is_file()
    }
    need(len(files) == 11 and set(files) == actual, "manifest inventory")
    for path, digest in files.items():
        need(sha((HERE / path).read_bytes()) == digest, "packet file SHA: " + path)
    return files


def npz(raw: bytes) -> dict[str, np.ndarray]:
    names = {
        "state",
        "forcing",
        "xland",
        "value_output",
        "graph_output",
        "seed_nc16",
        "vjp_nc16",
        "coordinate_jvp_nc16",
        *(f"direction_{n}" for n in FIELD),
        *(f"jvp_{n}" for n in FIELD),
    }
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        need(set(archive.files) == names, "NC16 result array inventory")
        arrays = {name: np.array(archive[name], copy=True, order="C") for name in names}
    for name, array in arrays.items():
        dtype = np.float32 if name == "xland" else np.float64
        shape = (
            (1,) if name == "xland" else ((4, 39) if name == "forcing" else (12, 39))
        )
        need(
            array.dtype == dtype and array.shape == shape and np.isfinite(array).all(),
            "NC16 finite array shape/dtype: " + name,
        )
    return arrays


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), why)


def close(a: float, b: float, *, scale: float = 1.0) -> bool:
    return abs(a - b) <= 5e-12 * max(scale, abs(a), abs(b))


def replay(
    *, result_override: bytes | None = None, result_sha: str | None = None
) -> dict:
    files = manifest()
    branch = branch_module()
    branch_result = branch.replay()
    need(
        branch_result["scientific_status"] == "INCONCLUSIVE"
        and branch_result["cases"] == 11,
        "verified branch parent",
    )
    state_parent = branch.parent_module()
    state_parent_result = state_parent.replay()
    need(
        state_parent_result["B1_graph_and_native_exit_raw_equal"] == 468,
        "verified state-AD parent",
    )
    receipt = state_parent.strict_json((HERE / "raw/receipt.json").read_bytes())
    logs = state_parent.strict_json((HERE / "raw/log_manifest.json").read_bytes())
    bridge_attestation = state_parent.strict_json(
        (HERE / "raw/bridge_attestation.json").read_bytes()
    )
    build = state_parent.strict_json((BRANCH / "raw/build_receipt.json").read_bytes())
    prior_probe = state_parent.strict_json(
        (STATE_AD / "raw/final_probe_receipt.json").read_bytes()
    )
    need(
        logs["schema"] == "kdm6.native_nc16_vjp_log_manifest.v1"
        and logs["sha256"]
        == {
            "probe_nc16.py": files["producer/probe_nc16.py.txt"],
            "nc16_result.npz": files["raw/nc16_result.npz"],
            "receipt.json": files["raw/receipt.json"],
            "run.stdout.txt": files["raw/run.stdout.txt"],
            "run.stderr.txt": files["raw/run.stderr.txt"],
        },
        "probe/log hash inventory",
    )
    bridge_source = (HERE / "executed_cpp/kdm6_c_api.cpp").read_bytes()
    state_header = (HERE / "executed_cpp/state.h").read_bytes()
    bridge_flags = gzip.decompress(
        (HERE / "build_metadata/bridge_flags.make.gz").read_bytes()
    )
    parent_link = gzip.decompress(
        (BRANCH / "build_metadata/kdm6_c_link.txt.gz").read_bytes()
    )
    need(
        bridge_attestation["schema"] == "kdm6.native_nc16_bridge_attestation.v1"
        and bridge_attestation["sha256"]["bridge_source"]
        == files["executed_cpp/kdm6_c_api.cpp"]
        and bridge_attestation["sha256"]["bridge_header"]
        == files["executed_cpp/kdm6_c_api.h"]
        and bridge_attestation["sha256"]["state_header"]
        == files["executed_cpp/state.h"]
        and bridge_attestation["sha256"]["bridge_flags"] == sha(bridge_flags)
        and bridge_attestation["sha256"]["link_command"] == sha(parent_link)
        and bridge_attestation["sha256"]["dso"] == build["sha256"]["dso"]
        and bridge_attestation["sha256"]["archive"] == build["sha256"]["archive"]
        and bridge_attestation["paths"]["dso"] == build["paths"]["dso"]
        and len(bridge_attestation["sha256"]["bridge_object"]) == 64
        and b"-ffp-contract=off" in bridge_flags
        and b"unpack_packed_state" in bridge_source
        and b"kdm6_handle_vjp_c" in bridge_source
        and b"return {&th, &qv, &qc, &qr, &qi, &qs, &qg, &nccn, &nc, &ni, &nr, &bg};"
        in state_header,
        "C ABI bridge source/object attestation and packing order",
    )
    need(
        receipt["schema"] == "kdm6.native_nc16_c_abi_vjp.v1"
        and receipt["input_capture_sha256"] == prior_probe["input_capture_sha256"]
        and receipt["library_sha256"] == build["sha256"]["dso"]
        and receipt["archive_sha256"] == build["sha256"]["archive"]
        and receipt["coordinator_source_sha256"]
        == build["sha256"]["instrumented_coordinator_source"]
        and receipt["library_path"] == build["paths"]["dso"]
        and receipt["probe_source_sha256"] == files["producer/probe_nc16.py.txt"]
        and (
            result_override is not None
            or receipt["result_sha256"] == files["raw/nc16_result.npz"]
        )
        and receipt["torch_version"] == "2.13.0"
        and receipt["value_rc"]
        == receipt["graph_rc"]
        == receipt["vjp_rc"]
        == receipt["close_rc"]
        == 0
        and receipt["jvp_rc"] == {name: 0 for name in FIELD}
        and receipt["seed_field"] == "nc"
        and receipt["seed_native_level"] == 16,
        "C ABI source/build/input/run contract",
    )
    env = receipt["environment"]
    need(
        env
        == {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
            "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
            "KDM6_QR_TRANSPORT": "actual_departure",
            "KDM6AD_QNC_LIVE_GUARD": "1",
        },
        "C ABI variant/thread environment",
    )
    source = (HERE / "producer/probe_nc16.py.txt").read_text()
    need(
        "seed[8, 15] = 1.0" in source
        and "KDM6_NATIVE_CAPTURE_DIR" in source
        and "value capture must remain disabled" in source,
        "NC16 one-hot and capture-disabled producer source",
    )
    if result_override is not None:
        need(
            result_sha is not None and sha(result_override) == result_sha,
            "test NC16 result SHA",
        )
    arrays = npz(
        result_override
        if result_override is not None
        else (HERE / "raw/nc16_result.npz").read_bytes()
    )
    coordinate_error = np.abs(arrays["coordinate_jvp_nc16"] - arrays["vjp_nc16"])
    coordinate_normalized = coordinate_error / np.maximum(
        1.0, np.abs(arrays["vjp_nc16"])
    )
    worst = np.unravel_index(
        np.argmax(coordinate_normalized), coordinate_normalized.shape
    )
    sweep = receipt["coordinate_sweep"]
    need(
        sweep["jvp_calls"] == 468
        and sweep["all_return_codes_zero"] is True
        and float(np.max(coordinate_normalized)) < 1e-13
        and close(
            float(np.max(coordinate_normalized)), sweep["max_normalized_difference"]
        )
        and close(float(np.max(coordinate_error)), sweep["max_absolute_difference"])
        and (sweep["worst_field"], sweep["worst_level_top0"]) == worst,
        "NC16 full coordinate JVP/VJP transpose map",
    )
    with np.load(STATE_AD / "raw/b1_ad_result.npz", allow_pickle=False) as parent:
        for name in (
            "state",
            "forcing",
            "xland",
            "value_output",
            "graph_output",
            *(f"direction_{n}" for n in FIELD),
            *(f"jvp_{n}" for n in FIELD),
        ):
            exact(arrays[name], parent[name], "NC16 C ABI versus parent raw: " + name)
        need(
            np.array_equal(
                arrays["value_output"].view(np.uint64),
                arrays["graph_output"].view(np.uint64),
            ),
            "NC16 value/graph forward",
        )
        seed_words = arrays["seed_nc16"].view(np.uint64).copy()
        need(
            seed_words[8, 15] == np.float64(1.0).view(np.uint64)
            and np.count_nonzero(seed_words) == 1,
            "NC16 one-hot seed at packed offset 327",
        )
        need(
            tuple(STATE_FIELDS) == tuple(state_parent.STATE), "packed state field order"
        )
        native, _, _ = state_parent.csv_capture(
            (STATE_AD / "raw/native_full_column_capture.csv.gz").read_bytes(),
            expected_rows=11271,
        )
        need(
            float(parent["value_output"][8, 15]).hex()
            == state_parent.f64(native["runtime_full_exit", "nc", 23]["raw_hex"]).hex(),
            "NC16 seed maps to native level 16",
        )
        transpose = {}
        fd_results = []
        for name, field in FIELD.items():
            direction = arrays["direction_" + name]
            tangent = arrays["jvp_" + name]
            lhs = math.fsum(
                float(x) * float(y)
                for x, y in zip(arrays["seed_nc16"].flat, tangent.flat)
            )
            rhs = math.fsum(
                float(x) * float(y)
                for x, y in zip(direction.flat, arrays["vjp_nc16"].flat)
            )
            need(
                lhs == float(tangent[8, 15]) and close(lhs, rhs),
                "NC16 C ABI transpose: " + name,
            )
            saved = receipt["contractions"][name]
            need(
                close(lhs, saved["weighted_jvp"])
                and close(rhs, saved["weighted_vjp"])
                and close(abs(lhs - rhs), saved["max_abs_difference"]),
                "saved NC16 contraction versus arrays: " + name,
            )
            transpose[name] = {
                "jvp_nc16": lhs,
                "vjp_relative_nc16": rhs,
                "abs_dot_gap": abs(lhs - rhs),
            }
            for h in LOCAL[name] + ((CROSSING[name],) if name in CROSSING else ()):
                a = "minus"
                b = "plus"
                with (
                    np.load(
                        STATE_AD / "raw/fd" / f"{name}_{h:.0e}_{a}.npz",
                        allow_pickle=False,
                    ) as lo,
                    np.load(
                        STATE_AD / "raw/fd" / f"{name}_{h:.0e}_{b}.npz",
                        allow_pickle=False,
                    ) as hi,
                ):
                    x0 = float(arrays["state"][field, 15])
                    gap = (
                        float(hi["state"][field, 15]) - float(lo["state"][field, 15])
                    ) / x0
                    delta = float(hi["output"][8, 15]) - float(lo["output"][8, 15])
                fd = delta / gap
                err = abs(fd - lhs) / max(1.0, abs(lhs))
                out_ulp = (
                    abs(fd - lhs)
                    * abs(gap)
                    / math.ulp(float(arrays["value_output"][8, 15]))
                )
                crossing = name in CROSSING and h == CROSSING[name]
                if crossing:
                    need(err > 1e-2, "separate branch-crossing NC16 secant: " + name)
                elif name == "qv" and h == 1e-5:
                    need(1.0 < out_ulp < 2.0, "small QV NC16 output-ULP residual")
                else:
                    need(err < 5e-6, "selected NC16 local FD/JVP: " + name)
                fd_results.append(
                    {
                        "direction": name,
                        "h": h,
                        "fd_nc16": fd,
                        "normalized_fd_jvp": err,
                        "error_output_ulps": out_ulp,
                        "branch_crossing": crossing,
                    }
                )
    return {
        "schema": "kdm6.native_nc16_vjp_branch_window_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "seed_packed_offset": 327,
        "seed_native_level": 16,
        "vjp_finite_cells": int(np.isfinite(arrays["vjp_nc16"]).sum()),
        "coordinate_jvp_cells": 468,
        "coordinate_max_normalized_transpose_gap": float(np.max(coordinate_normalized)),
        "coordinate_raw_mismatches": int(
            np.count_nonzero(
                arrays["coordinate_jvp_nc16"].view(np.uint64)
                != arrays["vjp_nc16"].view(np.uint64)
            )
        ),
        "parent_raw_equal_arrays": 11,
        "transpose": transpose,
        "finite_differences": fd_results,
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(replay(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
