#!/usr/bin/env python3
"""Replay retained skipped-substep B1/B2 AD and finite-difference evidence."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MANIFEST_SHA = "c07f3042ad8a5c3f40e2627ab8c3aa0e4fe4d1c9d35e3ae382abc9a763a98ab9"
PARENT_CAPTURE = (
    REPO
    / "harness/evidence/native_d1_entry_cpm_cpp_ad_2026-11-05/raw/native_qnice_applied_72033_runtime2.csv"
)
PARENT_CAPTURE_SHA = "125e122ad7fff63bd1d4c30e5d9172f291fbd7c2758022c558ef7b204b01fbad"
STATE = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
FORCING = ("rho", "pii", "p", "delz")
FIELD = {"qv": 1, "qs": 5, "qg": 6}
HALF_STEPS = {"qv": (1e-3, 1e-4, 1e-5), "qs": (1e-3, 1e-4), "qg": (1e-5, 1e-6, 1e-7)}
ACCEPTED = {("qv", 1e-4), ("qs", 1e-3), ("qs", 1e-4), ("qg", 1e-6), ("qg", 1e-7)}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes) -> dict:
    def pairs(items):
        out = {}
        for key, val in items:
            need(key not in out, "duplicate JSON key")
            out[key] = val
        return out

    def constant(token):
        raise ValueError("nonfinite JSON token: " + token)

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    need(type(result) is dict, "JSON object expected")
    return result


def manifest() -> dict:
    raw = (HERE / "manifest.json").read_bytes()
    need(sha(raw) == MANIFEST_SHA, "pinned skipped-substep manifest")
    data = strict_json(raw)
    need(data["schema"] == "kdm6.skipped_substep_ad_packet.v1", "manifest schema")
    files = data["files"]
    actual = {
        str(p.relative_to(HERE))
        for folder in ("raw", "producer", "executed_cpp")
        for p in (HERE / folder).rglob("*")
        if p.is_file()
    }
    need(set(files) == actual and len(files) == 53, "manifest file inventory")
    for path, digest in files.items():
        need(
            type(digest) is str
            and len(digest) == 64
            and sha((HERE / path).read_bytes()) == digest,
            "pinned packet file: " + path,
        )
    return data


def csv_capture(raw_gz: bytes, *, expected_rows: int) -> tuple[dict, list[dict], bytes]:
    raw = gzip.decompress(raw_gz)
    need(len(raw) < 2 << 20 and raw.endswith(b"\n"), "bounded capture gzip payload")
    lines = raw.decode("ascii").splitlines()
    reader = csv.DictReader(x for x in lines if not x.startswith("#"))
    rows = list(reader)
    need(
        len(rows) == expected_rows
        and reader.fieldnames
        == [
            "one_step_call",
            "runtime_call",
            "substep",
            "b_zero",
            "k_zero",
            "B",
            "K",
            "stage",
            "field",
            "dtype",
            "raw_hex",
        ],
        "capture shape/header",
    )
    d = {}
    for row in rows:
        need(
            set(row) == set(reader.fieldnames) and None not in row.values(),
            "capture row columns",
        )
        try:
            k = int(row["k_zero"])
            int(row["raw_hex"], 16)
        except ValueError as exc:
            raise ValueError("capture k/raw word") from exc
        key = (row["stage"], row["field"], k)
        need(
            0 <= k < 39 and row["k_zero"] == str(k) and key not in d,
            "capture unique stage/field/level",
        )
        d[key] = row
    return d, rows, raw


def f64(raw_hex: str) -> float:
    return struct.unpack(">d", int(raw_hex, 16).to_bytes(8, "big"))[0]


def matrix(rows: dict, stage: str, names: tuple[str, ...]) -> np.ndarray:
    values = np.ascontiguousarray(
        [
            [f64(rows[stage, name, k]["raw_hex"]) for k in range(38, -1, -1)]
            for name in names
        ],
        dtype=np.float64,
    )
    need(np.isfinite(values).all(), "finite selected matrix: " + stage)
    return values


def exact(a: np.ndarray, b: np.ndarray, why: str) -> None:
    need(
        a.shape == b.shape
        and a.dtype == b.dtype == np.float64
        and a.view(np.uint64).tobytes() == b.view(np.uint64).tobytes(),
        why,
    )


def npz(raw: bytes, expected: dict[str, tuple[int, ...]]) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        need(set(archive.files) == set(expected), "array inventory")
        result = {
            name: np.array(archive[name], copy=True, order="C") for name in expected
        }
    for name, shape in expected.items():
        value = result[name]
        dtype = np.float32 if name == "xland" else np.float64
        need(
            value.dtype == dtype and value.shape == shape and np.isfinite(value).all(),
            "finite numeric array: " + name,
        )
    return result


def source_and_runs(files: dict) -> tuple[dict, dict]:
    receipt = strict_json((HERE / "raw/final_probe_receipt.json").read_bytes())
    old = strict_json((HERE / "raw/parent_on_run_result.json").read_bytes())
    off = strict_json((HERE / "raw/off_run_result.json").read_bytes())
    on = strict_json((HERE / "raw/on_run_result.json").read_bytes())
    need(
        receipt["schema"] == "kdm6.native_full_column_mask_ad_probe.v1"
        and receipt["library_sha256"]
        == "4c7849af3cb2a36599b968b018569d9f955b94eb38cacd58749f5b5e679a5caf"
        and receipt["archive_sha256"]
        == "44099b67b14b15450796fb3b648778c96635d22eec614c8b3b5f40f59762608d"
        and receipt["coordinator_source_sha256"]
        == files["executed_cpp/coordinator.cpp"]
        and receipt["baseline_raw_equal_cells"] == 468
        and receipt["B1_B2_jvp_raw_equal_cells"] == 1404
        and receipt["B1_B2_vjp_raw_equal_cells"] == 468
        and receipt["witness_vjp_nonzero_cells"] == 0,
        "pinned final B1/B2 AD probe contract",
    )
    need(
        receipt["input_capture_sha256"]
        == "0919ce378f47b4ace8c447bc7ddba8f9e14ea06a3b9de750f9c19be7a703ebcb"
        and receipt["arrays_sha256"]
        == {"B1": files["raw/b1_ad_result.npz"], "B2": files["raw/b2_ad_result.npz"]}
        and receipt["probe_source_sha256"]
        == {
            "probe_ad.py": files["producer/probe_ad.py.txt"],
            "probe_schedule_witness.py": files[
                "producer/probe_schedule_witness.py.txt"
            ],
        },
        "probe input/result/source hash chain",
    )
    need(
        len(receipt["calls"]) == 2
        and all(call["returncode"] == 0 for call in receipt["calls"])
        and receipt["calls"][0]["stdout_sha256"] == files["raw/b1_stdout.txt"]
        and receipt["calls"][0]["stderr_sha256"] == files["raw/b1_stderr.txt"]
        and receipt["calls"][1]["stdout_sha256"] == files["raw/b2_stdout.txt"]
        and receipt["calls"][1]["stderr_sha256"] == files["raw/b2_stderr.txt"],
        "probe call/log hash chain",
    )
    need(
        receipt["environment"]["KDM6_PROBE_LIB"] == receipt["library_path"]
        and receipt["environment"]["KDM6_ICE_FACTORIAL_MODE"] == "norm_actual"
        and receipt["environment"]["KDM6_QR_TRANSPORT"] == "actual_departure"
        and receipt["environment"]["OMP_NUM_THREADS"] == "1"
        and receipt["environment"]["MKL_NUM_THREADS"] == "1",
        "actual probe variant/thread environment",
    )
    for name, run in (("off", off), ("on", on)):
        need(
            run["schema"] == "kdm6.native_d1_full_state_mask_trial_run.v1"
            and run["mode"] == name + "_final"
            and run["dso_sha256"] == receipt["library_sha256"]
            and run["object_sha256"]["coordinator.cpp.o"]
            == receipt["coordinator_object_sha256"]
            and run["source_sha256"]["coordinator.cpp"]
            == receipt["coordinator_source_sha256"]
            and run["endpoint_sha256"] == old["endpoint_sha256"]
            and run["startup_sha256"] == old["startup_sha256"]
            and run["executable_sha256"] == old["executable_sha256"],
            "same-build host value pair: " + name,
        )
    need(
        off["captures"] == {}
        and set(on["captures"].values()) == {receipt["input_capture_sha256"]}
        and old["dso_sha256"] != receipt["library_sha256"],
        "host capture-off/on and between-variant attribution",
    )
    return receipt, {
        "endpoint_sha256": off["endpoint_sha256"],
        "old_dso_sha256": old["dso_sha256"],
        "new_dso_sha256": receipt["library_sha256"],
    }


def replay(
    *,
    native_override: bytes | None = None,
    native_sha: str | None = None,
    b2_override: bytes | None = None,
    b2_sha: str | None = None,
    fd_npz_override: tuple[str, bytes, str] | None = None,
) -> dict:
    files = manifest()["files"]
    receipt, host = source_and_runs(files)
    if native_override is not None:
        need(
            native_sha is not None and sha(native_override) == native_sha,
            "test native capture SHA",
        )
    if b2_override is not None:
        need(b2_sha is not None and sha(b2_override) == b2_sha, "test B2 AD result SHA")
    if fd_npz_override is not None:
        fd_label, fd_raw, fd_sha = fd_npz_override
        need(
            fd_label in {
                f"{name}_{h:.0e}_{side}"
                for name, hs in HALF_STEPS.items()
                for h in hs
                for side in ("minus", "plus")
            }
            and sha(fd_raw) == fd_sha,
            "test FD array SHA/label",
        )
    native, native_rows, native_raw = csv_capture(
        native_override
        if native_override is not None
        else (HERE / "raw/native_full_column_capture.csv.gz").read_bytes(),
        expected_rows=11271,
    )
    local, _, local_raw = csv_capture(
        (HERE / "raw/one_column_capture.csv.gz").read_bytes(), expected_rows=11271
    )
    witness, _, witness_raw = csv_capture(
        (HERE / "raw/schedule_witness_capture.csv.gz").read_bytes(), expected_rows=11271
    )
    if native_override is None:
        need(sha(native_raw) == receipt["input_capture_sha256"], "native capture SHA")
    need(set(native) == set(local) == set(witness), "full-column stage inventory")
    native_witness_diff = [
        k
        for k in native
        if (native[k]["dtype"], native[k]["raw_hex"])
        != (witness[k]["dtype"], witness[k]["raw_hex"])
    ]
    native_local_diff = [
        k
        for k in native
        if (native[k]["dtype"], native[k]["raw_hex"])
        != (local[k]["dtype"], local[k]["raw_hex"])
    ]
    need(
        not native_witness_diff
        and len(native_local_diff) == 39
        and {(k[0], k[1]) for k in native_local_diff}
        == {("runtime_full_schedule", "mstepmax_main")},
        "native B=32248 / synthetic B=2 / replay B=1 stage relation",
    )
    need(
        all(
            f64(native["runtime_full_schedule", name, 23]["raw_hex"]) == value
            for name, value in (
                ("mstep_main_col", 1.0),
                ("mstep_ice_col", 1.0),
                ("mstepmax_main", 5.0),
                ("mstepmax_ice", 1.0),
            )
        )
        and f64(local["runtime_full_schedule", "mstepmax_main", 23]["raw_hex"]) == 1.0,
        "local and global schedule distinction",
    )
    parent_raw = PARENT_CAPTURE.read_bytes()
    need(sha(parent_raw) == PARENT_CAPTURE_SHA, "pinned prior 9750 capture")
    parent_rows = list(
        csv.DictReader(
            x for x in parent_raw.decode("ascii").splitlines() if not x.startswith("#")
        )
    )
    new_stages = {
        "runtime_full_entry",
        "runtime_full_forcing",
        "runtime_full_meta",
        "runtime_full_schedule",
        "runtime_full_exit",
    }
    need(
        [r for r in native_rows if r["stage"] not in new_stages] == parent_rows,
        "prior 9750 rows preserved raw and ordered",
    )
    b1 = npz(
        (HERE / "raw/b1_ad_result.npz").read_bytes(),
        {
            "state": (12, 39),
            "forcing": (4, 39),
            "value_output": (12, 39),
            "graph_output": (12, 39),
            "u": (12, 39),
            "vjp": (12, 39),
            "xland": (1,),
            **{f"direction_{name}": (12, 39) for name in FIELD},
            **{f"jvp_{name}": (12, 39) for name in FIELD},
            **{
                f"fd_{name}_{h}_{side}": (12, 39)
                for name, hs in (
                    ("qv", (0.001, 0.0001)),
                    ("qs", (0.001, 0.0001)),
                    ("qg", (1e-5, 1e-6)),
                )
                for h in hs
                for side in ("high_input", "low_input", "high_output", "low_output")
            },
            **{
                f"fd_{name}_{h}_gap": ()
                for name, hs in (
                    ("qv", (0.001, 0.0001)),
                    ("qs", (0.001, 0.0001)),
                    ("qg", (1e-5, 1e-6)),
                )
                for h in hs
            },
        },
    )
    b2 = npz(
        b2_override
        if b2_override is not None
        else (HERE / "raw/b2_ad_result.npz").read_bytes(),
        {
            "target_output": (12, 39),
            "target_grad": (12, 39),
            "witness_grad": (12, 39),
            **{f"jvp_{name}_target": (12, 39) for name in FIELD},
            **{f"jvp_{name}_witness": (12, 39) for name in FIELD},
        },
    )
    exact(
        b1["state"], matrix(native, "runtime_full_entry", STATE), "captured full state"
    )
    exact(
        b1["forcing"],
        matrix(native, "runtime_full_forcing", FORCING),
        "captured forcing",
    )
    exact(
        b1["value_output"],
        matrix(native, "runtime_full_exit", STATE),
        "native full exit",
    )
    exact(b1["graph_output"], b1["value_output"], "graph/value forward")
    exact(b2["target_output"], b1["value_output"], "B2/B1 target value")
    exact(b2["target_grad"], b1["vjp"], "B2/B1 target VJP")
    need(np.count_nonzero(b2["witness_grad"]) == 0, "zero witness VJP")
    duality = {}
    for name, field in FIELD.items():
        exact(b2[f"jvp_{name}_target"], b1[f"jvp_{name}"], "B2/B1 target JVP: " + name)
        need(
            np.count_nonzero(b2[f"jvp_{name}_witness"]) == 0,
            "zero witness JVP: " + name,
        )
        direction = b1[f"direction_{name}"]
        expected = np.zeros_like(direction)
        expected[field, 15] = b1["state"][field, 15]
        exact(direction, expected, "one native-level relative direction: " + name)
        lhs = math.fsum(
            float(x) * float(y)
            for x, y in zip(b1["u"].ravel(), b1[f"jvp_{name}"].ravel())
        )
        rhs = math.fsum(
            float(x) * float(y) for x, y in zip(direction.ravel(), b1["vjp"].ravel())
        )
        need(
            abs(lhs - rhs) <= 1e-12 * max(1.0, abs(lhs), abs(rhs)),
            "C ABI JVP/VJP transpose contraction: " + name,
        )
        saved = receipt["duality"][name]
        need(
            abs(lhs - saved["weighted_jvp"]) <= 1e-12
            and abs(rhs - saved["weighted_vjp"]) <= 1e-12,
            "saved C ABI dot versus verified arrays: " + name,
        )
        duality[name] = abs(lhs - rhs)
    fd_receipt = strict_json((HERE / "raw/fd_receipt.json").read_bytes())
    need(
        fd_receipt["schema"] == "kdm6.selected_column_fd_capture.v2"
        and fd_receipt["library_sha256"] == receipt["library_sha256"]
        and fd_receipt["archive_sha256"] == receipt["archive_sha256"]
        and fd_receipt["producer_source_sha256"]
        == files["producer/run_fd_capture.py.txt"]
        and fd_receipt["probe_source_sha256"] == files["producer/probe_ad.py.txt"],
        "same final library for FD endpoints",
    )
    case_map = {case["label"]: case for case in fd_receipt["cases"]}
    need(len(case_map) == 16, "FD endpoint inventory")
    bools = {k: r["raw_hex"] for k, r in local.items() if r["dtype"] == "bool"}
    schedule = {
        k: r["raw_hex"] for k, r in local.items() if k[0] == "runtime_full_schedule"
    }
    meta = {
        k: (r["dtype"], r["raw_hex"])
        for k, r in local.items()
        if k[0] == "runtime_full_meta"
    }
    need(
        b1["xland"].view(np.uint32).tobytes()
        == int(local["runtime_full_meta", "xland", 23]["raw_hex"], 16).to_bytes(
            4, "little" if sys.byteorder == "little" else "big"
        ),
        "B1 xland versus captured call control",
    )
    audit = strict_json((HERE / "raw/audit_probe_final.json").read_bytes())
    need(
        audit["schema"] == "kdm6.selected_full_column_ad_audit.v2"
        and audit["split_raw_mismatches"] == 0
        and audit["one_column_global_schedule_mismatches"] == 39,
        "saved independent FD audit identity",
    )
    diagnostics = []
    for name, hs in HALF_STEPS.items():
        for h in hs:
            ends = {}
            for sign, suffix in ((-1, "minus"), (1, "plus")):
                label = f"{name}_{h:.0e}_{suffix}"
                case = case_map[label]
                gz = (HERE / "raw/fd" / (label + ".csv.gz")).read_bytes()
                rows, _, raw = csv_capture(gz, expected_rows=11271)
                need(
                    sha(raw) == case["capture_sha256"]
                    and case["relative_step"] == sign * h,
                    "FD case capture/step: " + label,
                )
                arrays_raw = (
                    fd_npz_override[1]
                    if fd_npz_override is not None and fd_npz_override[0] == label
                    else (HERE / "raw/fd" / (label + ".npz")).read_bytes()
                )
                if fd_npz_override is None or fd_npz_override[0] != label:
                    need(
                        sha(arrays_raw) == case["arrays_sha256"],
                        "FD case arrays SHA: " + label,
                    )
                arrays = npz(
                    arrays_raw,
                    {
                        "state": (12, 39),
                        "forcing": (4, 39),
                        "output": (12, 39),
                        "xland": (1,),
                    },
                )
                exact(
                    arrays["state"],
                    matrix(rows, "runtime_full_entry", STATE),
                    "FD input capture: " + label,
                )
                exact(arrays["forcing"], b1["forcing"], "FD fixed forcing: " + label)
                need(
                    arrays["xland"].view(np.uint32).tobytes()
                    == b1["xland"].view(np.uint32).tobytes(),
                    "FD fixed xland: " + label,
                )
                exact(
                    arrays["output"],
                    matrix(rows, "runtime_full_exit", STATE),
                    "FD output capture: " + label,
                )
                target = b1["state"].copy()
                target[FIELD[name], 15] = b1["state"][FIELD[name], 15] * (
                    1.0 + sign * h
                )
                exact(
                    arrays["state"], target, "FD one-field represented input: " + label
                )
                need(
                    all(rows[k]["raw_hex"] == value for k, value in bools.items())
                    and all(
                        rows[k]["raw_hex"] == value for k, value in schedule.items()
                    ),
                    "FD recorded masks/schedule unchanged: " + label,
                )
                need(
                    all(
                        (rows[k]["dtype"], rows[k]["raw_hex"]) == value
                        for k, value in meta.items()
                    ),
                    "FD recorded call controls unchanged: " + label,
                )
                ends[suffix] = arrays
            low, high = ends["minus"], ends["plus"]
            gap = (high["state"][FIELD[name], 15] - low["state"][FIELD[name], 15]) / b1[
                "state"
            ][FIELD[name], 15]
            fd = (high["output"] - low["output"]) / gap
            jvp = b1[f"jvp_{name}"]
            normalized = np.abs(fd - jvp) / np.maximum(1.0, np.abs(jvp))
            error = float(np.max(normalized))
            saved = next(
                row
                for row in audit["finite_differences"]
                if row["direction"] == name and row["h"] == h
            )
            need(
                math.isclose(
                    error, saved["max_normalized_error"], rel_tol=5e-12, abs_tol=1e-15
                )
                and math.isclose(gap, saved["gap"], rel_tol=0, abs_tol=1e-15),
                "independent saved FD arithmetic: " + name,
            )
            if (name, h) in ACCEPTED:
                need(error < 5e-6, "selected local FD/JVP signal: " + name)
            else:
                need(error > 1e-5, "separate finite-change outlier: " + name)
            diagnostics.append(
                {
                    "direction": name,
                    "h": h,
                    "max_normalized_fd_jvp": error,
                    "local_fd_accepted": (name, h) in ACCEPTED,
                }
            )
    return {
        "schema": "kdm6.skipped_substep_ad_replay.v1",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "native_rows": 11271,
        "parent_rows_raw_equal": 9750,
        "native_vs_B2_stage_raw_equal": 11271,
        "native_vs_B1_stage_mismatches": 39,
        "B1_graph_and_native_exit_raw_equal": 468,
        "B2_B1_jvp_raw_equal": 1404,
        "B2_B1_vjp_raw_equal": 468,
        "weighted_dot_abs_difference": duality,
        "finite_differences": diagnostics,
        "host": host,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(replay(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
