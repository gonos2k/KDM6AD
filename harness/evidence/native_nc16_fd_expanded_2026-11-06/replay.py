#!/usr/bin/env python3
"""Replay prespecified NC16 C ABI value endpoints against saved NC16 VJP."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_nc16_vjp_branch_window_2026-11-06"
BRANCH = HERE.parent / "native_fd_outlier_branches_2026-11-05"
MANIFEST_SHA = "2696fb5e1f094a65ad769d464c2cb514fc1af9dfcdb4acaa8914fbdab8cb7c4e"
PARENT_REPLAY_SHA = "2ec8dc04745bef3c87b5ff062fbf94e01759f9fd3671ea3d95e1c5a6dbcfe5f4"
PLAN = {
    "nc16_rel": (1e-3, 1e-4, 1e-5),
    "qc16_rel": (1e-3, 1e-4, 1e-5),
    "th16_abs": (1e-2, 1e-3, 1e-4),
    "qg17_rel": (1e-3, 1e-4, 1e-5),
    "bg17_rel": (1e-3, 1e-4, 1e-5),
    "qg_bg17_rel": (1e-3, 1e-4, 1e-5),
}
COMPONENTS = {
    "nc16_rel": ((8, 15, "relative"),),
    "qc16_rel": ((2, 15, "relative"),),
    "th16_abs": ((0, 15, "absolute"),),
    "qg17_rel": ((6, 16, "relative"),),
    "bg17_rel": ((11, 16, "relative"),),
    "qg_bg17_rel": ((6, 16, "relative"), (11, 16, "relative")),
}
CROSS_SIDE = {
    ("th16_abs", 1e-2): "plus",
    ("qg17_rel", 1e-3): "plus",
    ("bg17_rel", 1e-3): "minus",
}
CROSSING = set(CROSS_SIDE)


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parent_module():
    need(
        sha((PARENT / "replay.py").read_bytes()) == PARENT_REPLAY_SHA,
        "pinned NC16 VJP replay",
    )
    spec = importlib.util.spec_from_file_location(
        "native_nc16_vjp_parent", PARENT / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "parent module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned expanded-FD manifest")
    data = json.loads(raw)
    need(data["schema"] == "kdm6.native_nc16_fd_expanded_packet.v1", "manifest schema")
    files = data["files"]
    actual = {
        str(p.relative_to(HERE))
        for folder in ("raw", "producer")
        for p in (HERE / folder).rglob("*")
        if p.is_file()
    }
    need(len(files) == 151 and set(files) == actual, "complete 37-case asset inventory")
    for path, digest in files.items():
        need(sha((HERE / path).read_bytes()) == digest, "asset SHA: " + path)
    return files


def f64(rows: dict, stage: str, field: str, level: int) -> float:
    row = rows[stage, field, level]
    need(row["dtype"] == "f64", "trace f64 dtype: " + stage + "/" + field)
    return struct.unpack(">d", int(row["raw_hex"], 16).to_bytes(8, "big"))[0]


def raw_equal(rows: dict, a: tuple, b: tuple) -> bool:
    return (rows[a]["dtype"], rows[a]["raw_hex"]) == (
        rows[b]["dtype"],
        rows[b]["raw_hex"],
    )


def array(raw: bytes) -> dict[str, np.ndarray]:
    expected = {
        "state": (12, 39),
        "forcing": (4, 39),
        "output": (12, 39),
        "xland": (1,),
    }
    with np.load(io.BytesIO(raw), allow_pickle=False) as data:
        need(set(data.files) == set(expected), "endpoint NPZ field inventory")
        out = {name: np.array(data[name], copy=True, order="C") for name in expected}
    for name, shape in expected.items():
        value = out[name]
        dtype = np.float32 if name == "xland" else np.float64
        need(
            value.shape == shape and value.dtype == dtype and np.isfinite(value).all(),
            "finite endpoint array shape/dtype: " + name,
        )
    return out


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes(), why)


def case_labels() -> list[tuple[str, str, float]]:
    result = [("baseline", "baseline", 0.0)]
    for direction, steps in PLAN.items():
        for h in steps:
            for sign, side in ((-1, "minus"), (1, "plus")):
                result.append((f"{direction}_{h:.0e}_{side}", direction, sign * h))
    return result


def replay(
    *,
    case_npz_override: tuple[str, bytes, str] | None = None,
    case_capture_override: tuple[str, bytes, str] | None = None,
) -> dict:
    parent = parent_module()
    parent_summary = parent.replay()
    need(
        parent_summary["seed_packed_offset"] == 327
        and parent_summary["coordinate_jvp_cells"] == 468
        and parent_summary["scientific_status"] == "INCONCLUSIVE",
        "verified NC16 VJP parent",
    )
    branch = parent.branch_module()
    branch_summary = branch.replay()
    need(branch_summary["cases"] == 11, "verified cap-branch parent")
    state_parent = branch.parent_module()
    files = manifest()
    labels = case_labels()
    allowed = {x[0] for x in labels}
    for override in (case_npz_override, case_capture_override):
        if override is not None:
            label, raw, digest = override
            need(label in allowed and sha(raw) == digest, "test case SHA/label")
    receipt = state_parent.strict_json((HERE / "raw/receipt.json").read_bytes())
    build = state_parent.strict_json((BRANCH / "raw/build_receipt.json").read_bytes())
    parent_npz = PARENT / "raw/nc16_result.npz"
    need(
        receipt["schema"] == "kdm6.native_nc16_fd_prespecified.v1"
        and receipt["library_sha256"] == build["sha256"]["dso"]
        and receipt["archive_sha256"] == build["sha256"]["archive"]
        and receipt["coordinator_source_sha256"]
        == build["sha256"]["instrumented_coordinator_source"]
        and receipt["library_path"] == build["paths"]["dso"]
        and receipt["parent_npz_sha256"] == sha(parent_npz.read_bytes())
        and receipt["evaluate_source_sha256"] == files["producer/evaluate.py.txt"]
        and receipt["runner_source_sha256"] == files["producer/run_fd.py.txt"]
        and receipt["plan"] == {name: list(hs) for name, hs in PLAN.items()}
        and receipt["environment"]
        == {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OMP_THREAD_LIMIT": "1",
            "KDM6_ICE_FACTORIAL_MODE": "norm_actual",
            "KDM6_QR_TRANSPORT": "actual_departure",
            "KDM6AD_QNC_LIVE_GUARD": "1",
        },
        "source/build/input/prespecified-plan receipt",
    )
    case_map = {row["label"]: row for row in receipt["cases"]}
    need(
        len(case_map) == len(labels) == 37 and set(case_map) == allowed,
        "complete 37-case run receipt",
    )
    with np.load(parent_npz, allow_pickle=False) as saved:
        base_state = np.array(saved["state"], copy=True)
        base_forcing = np.array(saved["forcing"], copy=True)
        base_xland = np.array(saved["xland"], copy=True)
        base_output = np.array(saved["value_output"], copy=True)
        gradient = np.array(saved["vjp_nc16"], copy=True)
    branch_baseline, branch_rows, _ = state_parent.csv_capture(
        (BRANCH / "raw/cases/baseline.csv.gz").read_bytes(), expected_rows=13611
    )
    baseline_meta = {
        k: (r["dtype"], r["raw_hex"])
        for k, r in branch_baseline.items()
        if k[0] == "runtime_full_meta"
    }
    baseline_bools = {
        k: r["raw_hex"] for k, r in branch_baseline.items() if r["dtype"] == "bool"
    }
    baseline_schedule = {
        k: r["raw_hex"]
        for k, r in branch_baseline.items()
        if k[0] == "runtime_full_schedule"
    }
    cases = {}
    for label, direction, step in labels:
        row = case_map[label]
        need(
            row["direction"] == direction
            and row["nominal_step"] == step
            and row["returncode"] == 0
            and row["capture_rows"] == 13611,
            "saved case identity/exit: " + label,
        )
        overridden_csv = (
            case_capture_override is not None and case_capture_override[0] == label
        )
        overridden_npz = case_npz_override is not None and case_npz_override[0] == label
        csv_gz = (
            case_capture_override[1]
            if overridden_csv
            else (HERE / "raw/cases" / (label + ".csv.gz")).read_bytes()
        )
        captured, rows, raw_csv = state_parent.csv_capture(csv_gz, expected_rows=13611)
        if not overridden_csv:
            need(sha(raw_csv) == row["capture_sha256"], "capture receipt SHA: " + label)
        arr_raw = (
            case_npz_override[1]
            if overridden_npz
            else (HERE / "raw/cases" / (label + ".npz")).read_bytes()
        )
        if not overridden_npz:
            need(sha(arr_raw) == row["arrays_sha256"], "array receipt SHA: " + label)
        for suffix, field in (
            ("stdout.txt", "stdout_sha256"),
            ("stderr.txt", "stderr_sha256"),
        ):
            need(
                files["raw/cases/" + label + "." + suffix] == row[field],
                "case log SHA: " + label,
            )
        need(
            set(captured) == set(branch_baseline)
            and all(
                captured[k]["dtype"] == branch_baseline[k]["dtype"]
                and tuple(
                    captured[k][part]
                    for part in (
                        "one_step_call",
                        "runtime_call",
                        "substep",
                        "b_zero",
                        "B",
                        "K",
                    )
                )
                == tuple(
                    branch_baseline[k][part]
                    for part in (
                        "one_step_call",
                        "runtime_call",
                        "substep",
                        "b_zero",
                        "B",
                        "K",
                    )
                )
                for k in captured
            ),
            "capture stage/dtype/call inventory: " + label,
        )
        arrays = array(arr_raw)
        exact(
            arrays["state"],
            state_parent.matrix(captured, "runtime_full_entry", state_parent.STATE),
            "captured endpoint input state: " + label,
        )
        exact(
            arrays["forcing"],
            state_parent.matrix(captured, "runtime_full_forcing", state_parent.FORCING),
            "captured endpoint forcing: " + label,
        )
        exact(
            arrays["output"],
            state_parent.matrix(captured, "runtime_full_exit", state_parent.STATE),
            "captured endpoint output: " + label,
        )
        exact(arrays["forcing"], base_forcing, "fixed forcing: " + label)
        exact(arrays["xland"], base_xland, "fixed xland: " + label)
        need(
            all(
                (captured[k]["dtype"], captured[k]["raw_hex"]) == val
                for k, val in baseline_meta.items()
            ),
            "fixed call controls: " + label,
        )
        expected_state = base_state.copy()
        if direction != "baseline":
            for field, level, mode in COMPONENTS[direction]:
                original = base_state[field, level]
                expected_state[field, level] = (
                    original * (1.0 + step) if mode == "relative" else original + step
                )
                need(
                    expected_state[field, level] > 0.0,
                    "positive perturbed component: " + label,
                )
        exact(
            arrays["state"],
            expected_state,
            "prespecified represented endpoint: " + label,
        )
        boolean_changes = sum(
            captured[k]["raw_hex"] != val for k, val in baseline_bools.items()
        )
        schedule_changes = sum(
            captured[k]["raw_hex"] != val for k, val in baseline_schedule.items()
        )
        need(
            boolean_changes == schedule_changes == 0,
            "recorded masks/substep schedule stable: " + label,
        )
        qv = f64(captured, "fd_satadj_inner", "qv_input", 23)
        qs1 = f64(captured, "fd_satadj_inner", "qs1", 23)
        sw = f64(captured, "fd_satadj_inner", "sw_percent", 23)
        fraction = f64(captured, "fd_satadj_inner", "activated_fraction", 23)
        need(
            sw.hex() == ((qv / max(qs1, 1e-9) - 1.0) * 100.0).hex()
            and math.isclose(
                fraction,
                min(1.0, max(sw / 0.48, 0.0) ** 0.6),
                rel_tol=2e-12,
                abs_tol=2e-15,
            ),
            "activation producer and cap: " + label,
        )
        qg17 = f64(captured, "runtime_full_entry", "qg", 22)
        bg17 = f64(captured, "runtime_full_entry", "bg", 22)
        ratio17 = qg17 / bg17
        expected_bg = qg17 / min(max(qg17 / max(bg17, 1e-15), 100.0), 900.0)
        need(
            f64(captured, "fd_main", "brs_before", 16).hex() == expected_bg.hex(),
            "entry ProgB producer at native17: " + label,
        )
        cases[label] = {
            "arrays": arrays,
            "rows": captured,
            "sw": sw,
            "fraction": fraction,
            "density_ratio17": ratio17,
            "activation_capped": fraction == 1.0,
            "density17_capped": ratio17 >= 900.0,
            "bool_changes": boolean_changes,
            "schedule_changes": schedule_changes,
        }
    exact(
        cases["baseline"]["arrays"]["state"], base_state, "same NC16 VJP baseline input"
    )
    exact(
        cases["baseline"]["arrays"]["output"],
        base_output,
        "same NC16 VJP baseline output",
    )
    # The complete baseline capture from the same DSO must be unchanged, not merely its output.
    baseline_new_rows = state_parent.csv_capture(
        (HERE / "raw/cases/baseline.csv.gz").read_bytes(), expected_rows=13611
    )[1]
    need(baseline_new_rows == branch_rows, "same-DSO baseline trace raw rows")
    baseline = cases["baseline"]
    summary = []
    for direction, steps in PLAN.items():
        nominal = math.fsum(
            float(gradient[f, k])
            * float(base_state[f, k] if mode == "relative" else 1.0)
            for f, k, mode in COMPONENTS[direction]
        )
        for h in steps:
            lo = cases[f"{direction}_{h:.0e}_minus"]
            hi = cases[f"{direction}_{h:.0e}_plus"]
            delta = hi["arrays"]["state"] - lo["arrays"]["state"]
            predicted = math.fsum(
                float(gradient[f, k]) * float(delta[f, k])
                for f, k, _ in COMPONENTS[direction]
            )
            observed = float(hi["arrays"]["output"][8, 15]) - float(
                lo["arrays"]["output"][8, 15]
            )
            midpoint_terms = []
            for f, k, _ in COMPONENTS[direction]:
                center = Fraction.from_float(float(base_state[f, k]))
                low = Fraction.from_float(float(lo["arrays"]["state"][f, k]))
                high = Fraction.from_float(float(hi["arrays"]["state"][f, k]))
                midpoint_offset = (high + low) / 2 - center
                input_ulp = Fraction.from_float(math.ulp(float(base_state[f, k])))
                midpoint_terms.append(
                    (f, k, float(midpoint_offset / input_ulp), float(midpoint_offset))
                )
            midpoint_ulps = max(abs(term[2]) for term in midpoint_terms)
            midpoint_vjp = math.fsum(
                float(gradient[f, k]) * offset for f, k, _, offset in midpoint_terms
            )
            need(
                midpoint_ulps <= 0.5, "bounded exact represented midpoint: " + direction
            )
            err = abs(observed - predicted) / max(1.0, abs(predicted))
            crossing = (direction, h) in CROSSING
            sides = {"minus": lo, "plus": hi}
            changed_sides = [
                side
                for side, case in sides.items()
                if (
                    case["activation_capped"] != baseline["activation_capped"]
                    or case["density17_capped"] != baseline["density17_capped"]
                )
            ]
            actual_crossing = bool(changed_sides)
            need(
                actual_crossing == crossing
                and changed_sides == ([CROSS_SIDE[direction, h]] if crossing else []),
                "prespecified captured-cap crossing: " + direction + "/" + str(h),
            )
            one_sided = {}
            for side, case in sides.items():
                delta_side = case["arrays"]["state"] - base_state
                predicted_side = math.fsum(
                    float(gradient[f, k]) * float(delta_side[f, k])
                    for f, k, _ in COMPONENTS[direction]
                )
                observed_side = float(case["arrays"]["output"][8, 15]) - float(
                    base_output[8, 15]
                )
                one_sided[side] = {
                    "observed_nc16_gap": observed_side,
                    "vjp_predicted_gap": predicted_side,
                    "captured_cap_changed": side in changed_sides,
                }
            if crossing:
                need(err > 1e-3, "separate branch-crossing secant: " + direction)
            else:
                need(
                    err < 5e-6
                    and abs(observed) / math.ulp(float(base_output[8, 15])) > 1e5,
                    "selected NC16 local FD signal: " + direction,
                )
            summary.append(
                {
                    "direction": direction,
                    "h": h,
                    "nominal_vjp": nominal,
                    "observed_nc16_gap": observed,
                    "vjp_predicted_gap": predicted,
                    "normalized_error": err,
                    "output_error_ulps": abs(observed - predicted)
                    / math.ulp(float(base_output[8, 15])),
                    "captured_cap_crossing": crossing,
                    "changed_side": changed_sides,
                    "one_sided": one_sided,
                    "midpoint_input_ulps": midpoint_ulps,
                    "midpoint_vjp_output_ulps": midpoint_vjp
                    / math.ulp(float(base_output[8, 15])),
                    "minus_sw": lo["sw"],
                    "plus_sw": hi["sw"],
                    "minus_density_ratio17": lo["density_ratio17"],
                    "plus_density_ratio17": hi["density_ratio17"],
                }
            )
    coupled = {x["h"]: x for x in summary if x["direction"] == "qg_bg17_rel"}
    need(
        all(not row["captured_cap_crossing"] for row in coupled.values())
        and all(
            abs(
                cases[f"qg_bg17_rel_{h:.0e}_{side}"]["density_ratio17"]
                - baseline["density_ratio17"]
            )
            <= 2 * math.ulp(baseline["density_ratio17"])
            for h in PLAN["qg_bg17_rel"]
            for side in ("minus", "plus")
        ),
        "coupled QG/BRS keeps recorded entry density branch",
    )
    return {
        "schema": "kdm6.native_nc16_fd_expanded_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "calls": len(cases),
        "levels": 39,
        "outputs_per_call": 468,
        "baseline_raw_equal": True,
        "comparisons": summary,
        "accepted_windows": len(summary) - len(CROSSING),
        "captured_cap_crossings": len(CROSSING),
        "coupled_nominal_vjp": math.fsum(
            float(gradient[f, k]) * float(base_state[f, k])
            for f, k, _ in COMPONENTS["qg_bg17_rel"]
        ),
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(replay(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
