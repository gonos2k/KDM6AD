#!/usr/bin/env python3
"""Replay value-only f64 endpoint traces around two finite-step branch crossings."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct

import numpy as np


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "skipped_substep_ad_2026-11-05"
MANIFEST_SHA = "3a815c615af339dae940c32b48b93f3b02c6d5ad986ae538cc5a7fb62f7b13c6"
PARENT_REPLAY_SHA = "eed4fa99513a465fe634addf611831be7f5d3623e6b3e8648bb517463cbadb55"
LABELS = ("baseline",) + tuple(
    f"{name}_{h:.0e}_{side}"
    for name, hs in (("qv", (1e-3, 1e-4, 1e-5)), ("qg", (1e-5, 1e-6)))
    for h in hs
    for side in ("minus", "plus")
)
BOOL_FIELDS = {
    ("fd_warm", "rain_complete_evap"),
    ("fd_satadj_inner", "sw_positive"),
    ("fd_satadj_inner", "cloud_complete_evap"),
}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parent_module():
    raw = (PARENT / "replay.py").read_bytes()
    need(sha(raw) == PARENT_REPLAY_SHA, "pinned parent replay")
    spec = importlib.util.spec_from_file_location(
        "skipped_substep_parent_replay", PARENT / "replay.py"
    )
    need(spec is not None and spec.loader is not None, "parent module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned branch-trace manifest")
    data = json.loads(raw)
    need(
        data["schema"] == "kdm6.native_fd_outlier_branches_packet.v1", "manifest schema"
    )
    files = data["files"]
    actual = {
        str(path.relative_to(HERE))
        for folder in ("raw", "producer", "executed_cpp", "build_metadata")
        for path in (HERE / folder).rglob("*")
        if path.is_file()
    }
    need(set(files) == actual and len(files) == 55, "manifest file inventory")
    for path, digest in files.items():
        need(sha((HERE / path).read_bytes()) == digest, "packet file SHA: " + path)
    return files


def value(rows: dict, stage: str, field: str, k: int = 23) -> float:
    row = rows[stage, field, k]
    need(row["dtype"] == "f64", "f64 trace field: " + stage + "/" + field)
    return struct.unpack(">d", int(row["raw_hex"], 16).to_bytes(8, "big"))[0]


def bits_equal(
    rows: dict,
    stage_a: str,
    field_a: str,
    k_a: int,
    stage_b: str,
    field_b: str,
    k_b: int,
) -> bool:
    a = rows[stage_a, field_a, k_a]
    b = rows[stage_b, field_b, k_b]
    return (a["dtype"], a["raw_hex"]) == (b["dtype"], b["raw_hex"])


def case_data(
    label: str,
    parent,
    files: dict,
    receipt: dict,
    *,
    capture_override: tuple[str, bytes, str] | None,
) -> tuple[dict, dict]:
    row = next(case for case in receipt["cases"] if case["label"] == label)
    overridden = capture_override is not None and capture_override[0] == label
    gz = (
        capture_override[1]
        if overridden
        else (HERE / "raw/cases" / (label + ".csv.gz")).read_bytes()
    )
    new, new_rows, raw = parent.csv_capture(gz, expected_rows=13455)
    if not overridden:
        need(sha(raw) == row["capture_sha256"], "executed capture SHA: " + label)
    old_path = (
        PARENT / "raw/one_column_capture.csv.gz"
        if label == "baseline"
        else PARENT / "raw/fd" / (label + ".csv.gz")
    )
    _, old_rows, _ = parent.csv_capture(old_path.read_bytes(), expected_rows=11271)
    need(
        [r for r in new_rows if not r["stage"].startswith("fd_")] == old_rows,
        "parent 11271 rows unchanged: " + label,
    )
    parent_arrays = (
        PARENT / "raw/b1_ad_result.npz"
        if label == "baseline"
        else PARENT / "raw/fd" / (label + ".npz")
    )
    need(
        row["parent_arrays_sha256"] == sha(parent_arrays.read_bytes()),
        "parent probe arrays SHA: " + label,
    )
    with (
        np.load(HERE / "raw/cases" / (label + ".npz"), allow_pickle=False) as cur,
        np.load(parent_arrays, allow_pickle=False) as prior,
    ):
        mapping = (
            {
                "state": "state",
                "forcing": "forcing",
                "output": "value_output",
                "xland": "xland",
            }
            if label == "baseline"
            else {x: x for x in ("state", "forcing", "output", "xland")}
        )
        need(set(cur.files) == set(mapping), "probe array inventory: " + label)
        for field, prior_field in mapping.items():
            a, b = cur[field], prior[prior_field]
            need(
                a.dtype == b.dtype
                and a.shape == b.shape
                and a.tobytes() == b.tobytes(),
                "instrumentation changed " + field + ": " + label,
            )
        parent.exact(
            cur["state"],
            parent.matrix(new, "runtime_full_entry", parent.STATE),
            "traced state input: " + label,
        )
        parent.exact(
            cur["forcing"],
            parent.matrix(new, "runtime_full_forcing", parent.FORCING),
            "traced forcing input: " + label,
        )
        parent.exact(
            cur["output"],
            parent.matrix(new, "runtime_full_exit", parent.STATE),
            "traced state output: " + label,
        )
    need(
        row["arrays_sha256"] == files["raw/cases/" + label + ".npz"],
        "probe arrays SHA: " + label,
    )
    for suffix, key in (
        ("stdout.txt", "stdout_sha256"),
        ("stderr.txt", "stderr_sha256"),
    ):
        need(
            row[key] == files["raw/cases/" + label + "." + suffix],
            "probe log SHA: " + label,
        )
    need(row["returncode"] == 0, "probe return code: " + label)
    return new, row


def replay(*, capture_override: tuple[str, bytes, str] | None = None) -> dict:
    parent = parent_module()
    parent_summary = parent.replay()
    need(parent_summary["scientific_status"] == "INCONCLUSIVE", "parent status")
    files = manifest()
    if capture_override is not None:
        label, raw, digest = capture_override
        need(label in LABELS and sha(raw) == digest, "test trace SHA/label")
    build = parent.strict_json((HERE / "raw/build_receipt.json").read_bytes())
    receipt = parent.strict_json((HERE / "raw/run_receipt.json").read_bytes())
    source = (HERE / "executed_cpp/coordinator.cpp").read_bytes()
    parent_source = (PARENT / "executed_cpp/coordinator.cpp").read_bytes()
    stripped = b"".join(
        line
        for line in source.splitlines(keepends=True)
        if not line.lstrip().startswith(b'capture_native_tensor("fd_')
    )
    need(
        stripped == parent_source and source != parent_source,
        "instrumentation-only coordinator source",
    )
    stage_fields = set(
        re.findall(rb'capture_native_tensor\("(fd_[^"]+)", "([^"]+)"', source)
    )
    need(len(stage_fields) == 56, "instrumented stage/field inventory")
    cmake_cache = gzip.decompress(
        (HERE / "build_metadata/CMakeCache.txt.gz").read_bytes()
    )
    kdm6_flags = gzip.decompress(
        (HERE / "build_metadata/kdm6_flags.make.gz").read_bytes()
    )
    link_command = gzip.decompress(
        (HERE / "build_metadata/kdm6_c_link.txt.gz").read_bytes()
    )
    patch = gzip.decompress(
        (HERE / "executed_cpp/instrumentation.patch.gz").read_bytes()
    )
    need(
        build["schema"] == "kdm6.native_fd_outlier_trace_build.v1"
        and receipt["schema"] == "kdm6.native_fd_outlier_trace.v1"
        and build["sha256"]["instrumented_coordinator_source"]
        == files["executed_cpp/coordinator.cpp"]
        and build["sha256"]["parent_coordinator_source"] == sha(parent_source)
        and build["sha256"]["cmake_source"] == files["executed_cpp/CMakeLists.txt"]
        and build["sha256"]["cmake_cache"] == sha(cmake_cache)
        and build["sha256"]["kdm6_flags"] == sha(kdm6_flags)
        and build["sha256"]["instrumentation_patch"] == sha(patch)
        and receipt["library"] == build["paths"]["dso"]
        and receipt["library_sha256"] == build["sha256"]["dso"]
        and receipt["archive_sha256"] == build["sha256"]["archive"]
        and receipt["cmake_cache_sha256"] == build["sha256"]["cmake_cache"]
        and receipt["parent_coordinator_source_sha256"]
        == build["sha256"]["parent_coordinator_source"]
        and receipt["coordinator_source_sha256"]
        == files["executed_cpp/coordinator.cpp"]
        and receipt["runtime_source_sha256"]
        == build["sha256"]["runtime_source"]
        == files["executed_cpp/runtime.cpp"]
        and receipt["probe_source_sha256"] == files["producer/probe_ad.py.txt"]
        and receipt["producer_source_sha256"] == files["producer/run_endpoints.py.txt"],
        "source/build/run hash chain",
    )
    need(
        b"-ffp-contract=off" in kdm6_flags
        and b"KDM6_NATIVE_SCALAR_CAPTURE:BOOL=ON" in cmake_cache
        and b"KDM6_ENABLE_TEST_HOOKS:BOOL=OFF" in cmake_cache
        and b"libkdm6_c.2.0.0.dylib" in link_command,
        "isolated build flags",
    )
    recorded = {case["label"]: case for case in receipt["cases"]}
    need(
        len(recorded) == len(LABELS) and set(recorded) == set(LABELS),
        "trace case inventory",
    )
    traces = {}
    for label in LABELS:
        rows, case = case_data(
            label, parent, files, receipt, capture_override=capture_override
        )
        new_keys = {
            (s.encode(), f.encode(), k) for s, f, k in rows if s.startswith("fd_")
        }
        need(
            new_keys == {(s, f, k) for s, f in stage_fields for k in range(39)},
            "new 56x39 trace inventory: " + label,
        )
        for s, f, k in rows:
            if not s.startswith("fd_"):
                continue
            row = rows[s, f, k]
            need(
                row["dtype"] == ("bool" if (s, f) in BOOL_FIELDS else "f64")
                and row["one_step_call"] == ("0" if s == "fd_main" else "1")
                and row["runtime_call"] == "1"
                and row["substep"] == "0"
                and row["b_zero"] == "0"
                and row["B"] == "1"
                and row["K"] == "39",
                "trace dtype/call identity: " + label,
            )
        need(
            bits_equal(rows, "fd_main", "qg_before", 15, "runtime_full_entry", "qg", 23)
            and bits_equal(
                rows, "fd_main", "qg_after", 15, "d1_upstream_entry", "qg", 23
            )
            and bits_equal(
                rows, "fd_main", "brs_reslope", 15, "d1_upstream_entry", "brs", 23
            ),
            "top-first main sedimentation mapping: " + label,
        )
        qg = value(rows, "runtime_full_entry", "qg")
        brs = value(rows, "runtime_full_entry", "bg")
        ratio = qg / max(brs, 1e-15)
        selected_rho = min(max(ratio, 100.0), 900.0)
        expected_brs = qg / selected_rho
        got_brs = value(rows, "fd_main", "brs_before", 15)
        need(
            math.isfinite(got_brs) and got_brs.hex() == expected_brs.hex(),
            "entry ProgB density/BRS branch: " + label,
        )
        traces[label] = rows
        if label == "baseline":
            need(
                case["direction"] is None and case["relative_step"] == 0.0,
                "baseline direction",
            )
        else:
            direction, hstr, side = label.split("_")
            step = float(hstr) * (-1 if side == "minus" else 1)
            need(
                case["direction"] == direction and case["relative_step"] == step,
                "endpoint direction/step: " + label,
            )
    base = traces["baseline"]
    qv_minus = traces["qv_1e-03_minus"]
    qv_plus = traces["qv_1e-03_plus"]
    sw = {
        label: value(traces[label], "fd_satadj_inner", "sw_percent")
        for label in (
            "qv_1e-03_minus",
            "qv_1e-04_minus",
            "baseline",
            "qv_1e-04_plus",
            "qv_1e-03_plus",
        )
    }
    need(
        sw["qv_1e-03_minus"] < 0.48
        and all(sw[label] > 0.48 for label in sw if label != "qv_1e-03_minus"),
        "QV finite endpoint crosses activation-fraction cap",
    )
    for label in LABELS:
        rows = traces[label]
        sw_value = value(rows, "fd_satadj_inner", "sw_percent")
        qv_input = value(rows, "fd_satadj_inner", "qv_input")
        qs1 = value(rows, "fd_satadj_inner", "qs1")
        expected_sw = (qv_input / max(qs1, 1e-9) - 1.0) * 100.0
        need(sw_value.hex() == expected_sw.hex(), "sw producer operands: " + label)
        frac = value(rows, "fd_satadj_inner", "activated_fraction")
        need(
            math.isclose(
                frac,
                min(1.0, max(sw_value / 0.48, 0.0) ** 0.6),
                rel_tol=2e-12,
                abs_tol=2e-15,
            ),
            "activation fraction producer: " + label,
        )
        need(
            int(rows["fd_satadj_inner", "sw_positive", 23]["raw_hex"], 16) == 1
            and int(rows["fd_satadj_inner", "cloud_complete_evap", 23]["raw_hex"], 16)
            == 0,
            "activation and evaporation gates: " + label,
        )
        nc0 = value(rows, "fd_satadj_inner", "nc_input")
        ncact = value(rows, "fd_satadj_inner", "ncact")
        nc1 = value(rows, "fd_satadj_inner", "nc_after_activation")
        need(
            abs((nc0 + 20.0 * ncact) - nc1) <= math.ulp(nc1),
            "NC activation store arithmetic: " + label,
        )
        need(
            all(
                bits_equal(rows, a, fa, 23, b, fb, 23)
                for a, fa, b, fb in (
                    (
                        "fd_satadj_inner",
                        "nc_after_activation",
                        "fd_satadj_inner",
                        "nc_final",
                    ),
                    ("fd_satadj_inner", "nc_final", "fd_satadj", "nc_after"),
                    ("fd_satadj", "nc_after", "fd_cleanup", "nc"),
                    ("fd_cleanup", "nc", "fd_dsd", "nc_before"),
                    ("fd_dsd", "nc_before", "fd_dsd", "nc_after"),
                    ("fd_dsd", "nc_after", "runtime_full_exit", "nc"),
                )
            ),
            "NC activation-to-exit handoff: " + label,
        )
    need(
        value(qv_minus, "fd_satadj_inner", "activated_fraction") < 1.0
        and value(base, "fd_satadj_inner", "activated_fraction") == 1.0
        and value(qv_plus, "fd_satadj_inner", "activated_fraction") == 1.0,
        "QV activation cap selection",
    )
    qg_ratios = {
        label: value(traces[label], "runtime_full_entry", "qg")
        / value(traces[label], "runtime_full_entry", "bg")
        for label in (
            "qg_1e-05_minus",
            "qg_1e-05_plus",
            "qg_1e-06_minus",
            "qg_1e-06_plus",
            "baseline",
        )
    }
    need(
        qg_ratios["qg_1e-05_minus"] < 900.0
        and all(
            qg_ratios[label] > 900.0 for label in qg_ratios if label != "qg_1e-05_minus"
        ),
        "QG finite endpoint crosses entry ProgB rho cap",
    )
    nr0 = value(base, "d1_state_entry", "nr")
    need(
        all(
            value(traces[label], "d1_state_entry", "nr") == nr0
            and value(traces[label], "d1_melt_consumer", "nr_before") == nr0
            for label in ("qg_1e-05_minus", "qg_1e-05_plus")
        ),
        "QG D1 number entry unchanged",
    )
    need(
        value(traces["qg_1e-05_minus"], "d1_melt_consumer", "nr2")
        != value(traces["qg_1e-05_plus"], "d1_melt_consumer", "nr2"),
        "QG D1 sequential NR first recorded split",
    )
    with np.load(PARENT / "raw/b1_ad_result.npz", allow_pickle=False) as b1:
        qv_jvp = float(b1["jvp_qv"][8, 15])
        qg_jvp = float(b1["jvp_qg"][10, 15])
        qv_x = float(b1["state"][1, 15])
        qv_nc = float(b1["value_output"][8, 15])
        qg_x = float(b1["state"][6, 15])
        qg_nr = float(b1["value_output"][10, 15])

    def endpoint(
        label: str, state_field: int, output_field: int
    ) -> tuple[float, float]:
        with np.load(HERE / "raw/cases" / (label + ".npz"), allow_pickle=False) as data:
            return float(data["state"][state_field, 15]), float(
                data["output"][output_field, 15]
            )

    qv_small_minus = endpoint("qv_1e-05_minus", 1, 8)
    qv_small_plus = endpoint("qv_1e-05_plus", 1, 8)
    qv_gap = (qv_small_plus[0] - qv_small_minus[0]) / qv_x
    qv_fd = (qv_small_plus[1] - qv_small_minus[1]) / qv_gap
    qv_error_ulp = abs(qv_fd - qv_jvp) * abs(qv_gap) / math.ulp(qv_nc)
    need(1.0 < qv_error_ulp < 2.0, "QV small-step output-ULP residual")

    def one_sided(
        label: str, x0: float, y0: float, state_field: int, output_field: int
    ) -> float:
        x, y = endpoint(label, state_field, output_field)
        return (y - y0) / ((x - x0) / x0)

    qg_minus = one_sided("qg_1e-05_minus", qg_x, qg_nr, 6, 10)
    qg_plus = one_sided("qg_1e-05_plus", qg_x, qg_nr, 6, 10)
    need(
        abs(qg_plus - qg_jvp) < 1e-3 and abs(qg_minus - qg_jvp) > 10.0,
        "QG one-sided secants separate cap crossing",
    )
    return {
        "schema": "kdm6.native_fd_outlier_branches_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "cases": len(LABELS),
        "rows_per_case": 13455,
        "parent_rows_preserved_per_case": 11271,
        "new_stage_fields_per_case": 56,
        "same_value_outputs_as_parent": len(LABELS) * 468,
        "qv_activation": {
            "sw_percent": sw,
            "minus_fraction": value(qv_minus, "fd_satadj_inner", "activated_fraction"),
            "baseline_fraction": value(base, "fd_satadj_inner", "activated_fraction"),
            "minus_ncact": value(qv_minus, "fd_satadj_inner", "ncact"),
            "baseline_ncact": value(base, "fd_satadj_inner", "ncact"),
            "jvp_nc16": qv_jvp,
            "small_step_fd_error_in_output_ulps": qv_error_ulp,
        },
        "qg_entry_progb": {
            "uncapped_qg_over_brs": qg_ratios,
            "critical_relative_qg_change": 900.0 / qg_ratios["baseline"] - 1.0,
            "jvp_nr16": qg_jvp,
            "minus_one_sided_nr16": qg_minus,
            "plus_one_sided_nr16": qg_plus,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    print(json.dumps(replay(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
