#!/usr/bin/env python3
"""Replay one-hot NR16 C ABI VJP and independent saved endpoint differences."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
NC_PARENT = HERE.parent / "native_nc16_vjp_branch_window_2026-11-06"
FD_PARENT = HERE.parent / "native_nc16_fd_expanded_2026-11-06"
STATE_PARENT = HERE.parent / "skipped_substep_ad_2026-11-05"
MANIFEST_SHA = "dc93185a2b929e8f7cf70d2f1b3422d8901987bcc6d1779d4827ddbc70b118b1"
FD_REPLAY_SHA = "0322ecba06c051913199042d2fe163fde0744876eb0065a3a81fe7b1bd9222d2"
FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
OLD_COMPONENTS = {
    "qv16_rel": ((1, 15, "relative"),),
    "qs16_rel": ((5, 15, "relative"),),
    "qg16_rel": ((6, 15, "relative"),),
}
OLD_STEPS = {
    "qv16_rel": (1e-3, 1e-4, 1e-5),
    "qs16_rel": (1e-3, 1e-4),
    "qg16_rel": (1e-5, 1e-6, 1e-7),
}
OLD_CROSSING = {("qv16_rel", 1e-3), ("qg16_rel", 1e-5)}
RELATIVE_GUARD = 5e-5


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fd_parent_module():
    need(
        sha((FD_PARENT / "replay.py").read_bytes()) == FD_REPLAY_SHA,
        "pinned expanded-FD parent replay",
    )
    spec = importlib.util.spec_from_file_location(
        "native_nc16_expanded_fd_parent", FD_PARENT / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "FD parent module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned NR16 VJP manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nr16_vjp_fd_packet.v1", "manifest schema")
    files = data["files"]
    actual = {
        str(p.relative_to(HERE))
        for folder in ("raw", "producer")
        for p in (HERE / folder).rglob("*")
        if p.is_file()
    }
    need(len(files) == 6 and set(files) == actual, "NR16 complete asset inventory")
    for path, digest in files.items():
        need(sha((HERE / path).read_bytes()) == digest, "NR16 packet file SHA: " + path)
    return files


def result_npz(raw: bytes) -> dict[str, np.ndarray]:
    names = {
        "state",
        "forcing",
        "xland",
        "value_output",
        "graph_output",
        "seed_nr16",
        "vjp_nr16",
        "coordinate_jvp_nr16",
        *(f"direction_{n}" for n in ("qv", "qs", "qg")),
        *(f"jvp_{n}" for n in ("qv", "qs", "qg")),
    }
    with np.load(io.BytesIO(raw), allow_pickle=False) as data:
        need(set(data.files) == names, "NR16 result inventory")
        arrays = {name: np.array(data[name], copy=True, order="C") for name in names}
    for name, a in arrays.items():
        shape = (
            (1,) if name == "xland" else ((4, 39) if name == "forcing" else (12, 39))
        )
        dtype = np.float32 if name == "xland" else np.float64
        need(
            a.shape == shape and a.dtype == dtype and np.isfinite(a).all(),
            "NR16 finite array shape/dtype: " + name,
        )
    return arrays


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes(), why)


def endpoint(path: Path) -> dict[str, np.ndarray]:
    expected = {
        "state": (12, 39),
        "forcing": (4, 39),
        "output": (12, 39),
        "xland": (1,),
    }
    with np.load(path, allow_pickle=False) as data:
        need(set(data.files) == set(expected), "parent FD array fields: " + str(path))
        arrays = {n: np.array(data[n], copy=True) for n in expected}
    for n, a in arrays.items():
        need(
            a.shape == expected[n]
            and a.dtype == (np.float32 if n == "xland" else np.float64)
            and np.isfinite(a).all(),
            "parent FD array shape/dtype: " + n,
        )
    return arrays


def midpoint_diagnostics(
    lo: np.ndarray,
    hi: np.ndarray,
    baseline: np.ndarray,
    gradient: np.ndarray,
    components: tuple,
) -> tuple[float, float]:
    terms = []
    for f, k, _ in components:
        a = Fraction.from_float(float(lo[f, k]))
        b = Fraction.from_float(float(hi[f, k]))
        c = Fraction.from_float(float(baseline[f, k]))
        offset = (a + b) / 2 - c
        ulp = Fraction.from_float(math.ulp(float(baseline[f, k])))
        terms.append((f, k, float(offset / ulp), float(offset)))
    return max(abs(row[2]) for row in terms), math.fsum(
        float(gradient[f, k]) * offset for f, k, _, offset in terms
    )


def replay(
    *, result_override: bytes | None = None, result_sha: str | None = None
) -> dict:
    files = manifest()
    fd_parent = fd_parent_module()
    fd_summary = fd_parent.replay()
    need(
        fd_summary["calls"] == 37
        and fd_summary["accepted_windows"] == 15
        and fd_summary["captured_cap_crossings"] == 3,
        "verified 37-case value endpoint parent",
    )
    nc_parent = fd_parent.parent_module()
    nc_summary = nc_parent.replay()
    need(
        nc_summary["seed_packed_offset"] == 327
        and nc_summary["vjp_finite_cells"] == 468,
        "verified NC16 VJP parent",
    )
    branch = nc_parent.branch_module()
    branch_summary = branch.replay()
    need(branch_summary["cases"] == 11, "verified original cap trace")
    state_parent = branch.parent_module()
    receipt = state_parent.strict_json((HERE / "raw/receipt.json").read_bytes())
    logs = state_parent.strict_json((HERE / "raw/log_manifest.json").read_bytes())
    build = state_parent.strict_json(
        (
            HERE.parent / "native_fd_outlier_branches_2026-11-05/raw/build_receipt.json"
        ).read_bytes()
    )
    prior = state_parent.strict_json(
        (STATE_PARENT / "raw/final_probe_receipt.json").read_bytes()
    )
    need(
        logs["schema"] == "kdm6.native_nr16_vjp_log_manifest.v1"
        and logs["sha256"]
        == {
            "probe_nr16.py": files["producer/probe_nr16.py.txt"],
            "nr16_result.npz": files["raw/nr16_result.npz"],
            "receipt.json": files["raw/receipt.json"],
            "run.stdout.txt": files["raw/run.stdout.txt"],
            "run.stderr.txt": files["raw/run.stderr.txt"],
        },
        "NR16 producer/result/log hash chain",
    )
    need(
        receipt["schema"] == "kdm6.native_nr16_c_abi_vjp.v1"
        and receipt["input_capture_sha256"] == prior["input_capture_sha256"]
        and receipt["library_sha256"] == build["sha256"]["dso"]
        and receipt["archive_sha256"] == build["sha256"]["archive"]
        and receipt["coordinator_source_sha256"]
        == build["sha256"]["instrumented_coordinator_source"]
        and receipt["library_path"] == build["paths"]["dso"]
        and receipt["probe_source_sha256"] == files["producer/probe_nr16.py.txt"]
        and (
            result_override is not None
            or receipt["result_sha256"] == files["raw/nr16_result.npz"]
        )
        and receipt["torch_version"] == "2.13.0"
        and receipt["value_rc"]
        == receipt["graph_rc"]
        == receipt["vjp_rc"]
        == receipt["close_rc"]
        == 0
        and receipt["jvp_rc"] == {n: 0 for n in ("qv", "qs", "qg")}
        and receipt["seed_field"] == "nr"
        and receipt["seed_native_level"] == 16,
        "NR16 C ABI build/input/run/seed contract",
    )
    need(
        receipt["environment"]
        == {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
            "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
            "KDM6_QR_TRANSPORT": "actual_departure",
            "KDM6AD_QNC_LIVE_GUARD": "1",
        },
        "NR16 variant/thread environment",
    )
    producer = (HERE / "producer/probe_nr16.py.txt").read_text()
    need(
        "seed[10, 15] = 1.0" in producer
        and "KDM6_NATIVE_CAPTURE_DIR" in producer
        and "value capture must remain disabled" in producer,
        "NR16 one-hot and capture-disabled producer source",
    )
    if result_override is not None:
        need(
            result_sha is not None and sha(result_override) == result_sha,
            "test NR16 result SHA",
        )
    arrays = result_npz(
        result_override
        if result_override is not None
        else (HERE / "raw/nr16_result.npz").read_bytes()
    )
    with np.load(NC_PARENT / "raw/nc16_result.npz", allow_pickle=False) as nc:
        for name in (
            "state",
            "forcing",
            "xland",
            "value_output",
            "graph_output",
            *(f"direction_{n}" for n in ("qv", "qs", "qg")),
            *(f"jvp_{n}" for n in ("qv", "qs", "qg")),
        ):
            exact(arrays[name], nc[name], "NR16 vs NC16 parent raw: " + name)
    seed_words = arrays["seed_nr16"].view(np.uint64)
    need(
        seed_words[10, 15] == np.float64(1.0).view(np.uint64)
        and np.count_nonzero(seed_words) == 1,
        "NR16 one-hot output seed offset 405",
    )
    need(tuple(FIELDS) == tuple(state_parent.STATE), "packed state field order")
    native, _, _ = state_parent.csv_capture(
        (STATE_PARENT / "raw/native_full_column_capture.csv.gz").read_bytes(),
        expected_rows=11271,
    )
    need(
        float(arrays["value_output"][10, 15]).hex()
        == state_parent.f64(native["runtime_full_exit", "nr", 23]["raw_hex"]).hex(),
        "NR16 output maps to native level 16",
    )
    coord_diff = np.abs(arrays["coordinate_jvp_nr16"] - arrays["vjp_nr16"])
    coord_norm = coord_diff / np.maximum(1.0, np.abs(arrays["vjp_nr16"]))
    worst = np.unravel_index(np.argmax(coord_norm), coord_norm.shape)
    sweep = receipt["coordinate_sweep"]
    need(
        sweep["jvp_calls"] == 468
        and sweep["all_return_codes_zero"] is True
        and float(np.max(coord_norm)) < 1e-13
        and math.isclose(
            float(np.max(coord_norm)), sweep["max_normalized_difference"], rel_tol=1e-12
        )
        and math.isclose(
            float(np.max(coord_diff)), sweep["max_absolute_difference"], rel_tol=1e-12
        )
        and (sweep["worst_field"], sweep["worst_level_top0"]) == worst,
        "NR16 full coordinate same-graph transpose",
    )
    transposes = {}
    for name in ("qv", "qs", "qg"):
        direction = arrays["direction_" + name]
        tangent = arrays["jvp_" + name]
        lhs = math.fsum(
            float(x) * float(y) for x, y in zip(arrays["seed_nr16"].flat, tangent.flat)
        )
        rhs = math.fsum(
            float(x) * float(y) for x, y in zip(direction.flat, arrays["vjp_nr16"].flat)
        )
        need(
            lhs == float(tangent[10, 15])
            and abs(lhs - rhs) <= 5e-12 * max(1, abs(lhs), abs(rhs)),
            "NR16 selected transpose: " + name,
        )
        saved = receipt["contractions"][name]
        need(
            math.isclose(lhs, saved["weighted_jvp"], rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(rhs, saved["weighted_vjp"], rel_tol=1e-12, abs_tol=1e-12),
            "saved NR16 contraction versus arrays: " + name,
        )
        transposes[name] = {
            "jvp_nr16": lhs,
            "vjp_relative_nr16": rhs,
            "abs_dot_gap": abs(lhs - rhs),
        }
    all_components = {**fd_parent.COMPONENTS, **OLD_COMPONENTS}
    ulp = math.ulp(float(arrays["value_output"][10, 15]))
    old_cross = OLD_CROSSING
    new_cross = fd_parent.CROSSING
    from_fd = {(r["direction"], r["h"]): r for r in fd_summary["comparisons"]}
    comparisons = []
    for family, steps_map, root in (
        ("new", fd_parent.PLAN, FD_PARENT / "raw/cases"),
        ("old", OLD_STEPS, STATE_PARENT / "raw/fd"),
    ):
        for direction, steps in steps_map.items():
            components = all_components[direction]
            nominal = math.fsum(
                float(arrays["vjp_nr16"][f, k])
                * float(arrays["state"][f, k] if mode == "relative" else 1.0)
                for f, k, mode in components
            )
            for h in steps:
                key = direction if family == "new" else direction.removesuffix("16_rel")
                lo = endpoint(root / f"{key}_{h:.0e}_minus.npz")
                hi = endpoint(root / f"{key}_{h:.0e}_plus.npz")
                exact(
                    lo["forcing"],
                    arrays["forcing"],
                    "fixed FD forcing low: " + direction,
                )
                exact(
                    hi["forcing"],
                    arrays["forcing"],
                    "fixed FD forcing high: " + direction,
                )
                exact(lo["xland"], arrays["xland"], "fixed FD xland low: " + direction)
                exact(hi["xland"], arrays["xland"], "fixed FD xland high: " + direction)
                midpoint_ulps, midpoint_effect = midpoint_diagnostics(
                    lo["state"],
                    hi["state"],
                    arrays["state"],
                    arrays["vjp_nr16"],
                    components,
                )
                need(
                    midpoint_ulps <= 0.5, "represented FD midpoint bound: " + direction
                )
                delta = hi["state"] - lo["state"]
                predicted = math.fsum(
                    float(arrays["vjp_nr16"][f, k]) * float(delta[f, k])
                    for f, k, _ in components
                )
                observed = float(hi["output"][10, 15]) - float(lo["output"][10, 15])
                err = abs(observed - predicted)
                norm1 = err / max(1.0, abs(predicted))
                true_rel = err / max(abs(observed), abs(predicted), ulp)
                crossing = (
                    (direction, h) in new_cross
                    if family == "new"
                    else (direction, h) in old_cross
                )
                if family == "new":
                    parent_row = from_fd[direction, h]
                    need(
                        parent_row["captured_cap_crossing"] == crossing,
                        "inherited new endpoint branch classification",
                    )
                else:
                    need(
                        (direction, h) in old_cross
                        or (direction, h)
                        in {
                            ("qv16_rel", 1e-4),
                            ("qv16_rel", 1e-5),
                            ("qs16_rel", 1e-3),
                            ("qs16_rel", 1e-4),
                            ("qg16_rel", 1e-6),
                            ("qg16_rel", 1e-7),
                        },
                        "inherited old endpoint branch inventory",
                    )
                cap_status = (
                    "captured_crossing"
                    if crossing
                    else "masks_only_unverified"
                    if family == "old" and direction == "qs16_rel"
                    else "recorded_cap_unchanged"
                )
                need(abs(observed) / ulp > 1e6, "NR16 FD output signal: " + direction)
                if cap_status != "captured_crossing":
                    need(
                        norm1 < 5e-6 and true_rel < RELATIVE_GUARD,
                        "selected NR16 numerical FD/VJP: " + direction + "/" + str(h),
                    )
                one_sided = {}
                for side, case in (("minus", lo), ("plus", hi)):
                    dside = case["state"] - arrays["state"]
                    one_sided[side] = {
                        "observed_nr16_gap": float(case["output"][10, 15])
                        - float(arrays["value_output"][10, 15]),
                        "vjp_predicted_gap": math.fsum(
                            float(arrays["vjp_nr16"][f, k]) * float(dside[f, k])
                            for f, k, _ in components
                        ),
                    }
                comparisons.append(
                    {
                        "family": family,
                        "direction": direction,
                        "h": h,
                        "nominal_vjp": nominal,
                        "observed_nr16_gap": observed,
                        "vjp_predicted_gap": predicted,
                        "normalized_error": norm1,
                        "signal_relative_error": true_rel,
                        "output_error_ulps": err / ulp,
                        "output_signal_ulps": abs(observed) / ulp,
                        "midpoint_input_ulps": midpoint_ulps,
                        "midpoint_vjp_output_ulps": midpoint_effect / ulp,
                        "cap_status": cap_status,
                        "captured_cap_crossing": (
                            None if cap_status == "masks_only_unverified" else crossing
                        ),
                        "one_sided": one_sided,
                    }
                )
    need(
        len(comparisons) == 26
        and sum(x["cap_status"] == "captured_crossing" for x in comparisons) == 5
        and sum(x["cap_status"] == "recorded_cap_unchanged" for x in comparisons) == 19
        and sum(x["cap_status"] == "masks_only_unverified" for x in comparisons) == 2,
        "complete 26-pair NR16 FD inventory",
    )
    return {
        "schema": "kdm6.native_nr16_vjp_fd_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "seed_packed_offset": 405,
        "seed_native_level": 16,
        "vjp_finite_cells": int(np.isfinite(arrays["vjp_nr16"]).sum()),
        "coordinate_jvp_cells": 468,
        "coordinate_max_normalized_transpose_gap": float(np.max(coord_norm)),
        "coordinate_raw_mismatches": int(
            np.count_nonzero(
                arrays["coordinate_jvp_nr16"].view(np.uint64)
                != arrays["vjp_nr16"].view(np.uint64)
            )
        ),
        "parent_raw_equal_arrays": 11,
        "transpose": transposes,
        "comparisons": comparisons,
        "numerical_agreement_pairs": 21,
        "recorded_cap_unchanged_pairs": 19,
        "masks_only_pairs": 2,
        "captured_cap_crossings": 5,
        "max_numerical_agreement_true_relative_error": max(
            x["signal_relative_error"]
            for x in comparisons
            if x["cap_status"] != "captured_crossing"
        ),
        "nr16_output_ulp": ulp,
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(replay(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
