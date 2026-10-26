#!/usr/bin/env python3
"""Offline stdout-only replay for hash-bound V2 native QC/NC trace inputs.

The manifest names host/kernel trace files and a compact NPZ of READY/FINAL
float32 moments. Trace bytes are SHA-checked before being parsed through the
existing V2 reader in a temporary directory; the context NPZ is opened from
the exact SHA-checked bytes using BytesIO. No model, RTTOV, or KDM code runs.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
import tempfile
from typing import Any

import numpy as np

from harness.analyze_native_moment_trace import (
    analyze_native_moment_trace,
    compare_native_moment_runs,
)
from harness.native_moment_trace_records import read_moment_trace_v2


SCHEMA = "kdm6.native_moment_trace_replay_inputs.v1"
CONTEXT_KEYS = ("ready_qc", "ready_nc", "final_qc", "final_nc")


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _required_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _read_asset(base: Path, asset: dict[str, Any], *, label: str) -> bytes:
    rel = Path(asset["file"])
    if rel.is_absolute():
        raise ValueError(f"{label} path must be relative to the manifest")
    base_resolved = base.resolve()
    path = (base / rel).resolve()
    if base_resolved not in path.parents:
        raise ValueError(f"{label} path escapes the manifest directory")
    raw = path.read_bytes()
    expected_bytes = _required_int(asset["bytes"], f"{label} byte count")
    if len(raw) != expected_bytes:
        raise ValueError(f"{label} byte count differs: {len(raw)} != {asset['bytes']}")
    digest = _sha(raw)
    if digest != asset["sha256"]:
        raise ValueError(f"{label} SHA-256 differs: {digest} != {asset['sha256']}")
    return raw


def _f64_from_hex(bits: str, label: str) -> float:
    if len(bits) != 16:
        raise ValueError(f"{label} must be exactly 16 hexadecimal digits")
    try:
        value = struct.unpack(">d", bytes.fromhex(bits))[0]
    except (ValueError, struct.error) as exc:
        raise ValueError(f"{label} is not a binary64 hex word") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _load_context(raw: bytes, *, target_count: int, levels: int, run_id: str) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    try:
        with np.load(BytesIO(raw), allow_pickle=False) as archive:
            if set(archive.files) != set(CONTEXT_KEYS):
                raise ValueError(f"run {run_id} context NPZ must contain exactly {CONTEXT_KEYS}")
            for key in CONTEXT_KEYS:
                value = np.array(archive[key], copy=True)
                if value.dtype != np.float32 or value.shape != (target_count, levels):
                    raise ValueError(f"run {run_id} {key} must be float32[{target_count},{levels}]")
                if not np.isfinite(value).all():
                    raise ValueError(f"run {run_id} {key} contains nonfinite values")
                result[key] = value
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid run {run_id} context NPZ: {exc}") from exc
    return result


def replay_manifest(manifest_path: Path) -> dict[str, Any]:
    """Verify all inputs, analyze each run, compare requested pairs, return JSON data."""
    manifest_path = Path(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"expected manifest schema {SCHEMA}")
    runs = manifest.get("runs")
    targets_raw = manifest.get("targets")
    if not isinstance(runs, list) or not runs:
        raise ValueError("manifest.runs must be a nonempty list")
    if not isinstance(targets_raw, list) or len(targets_raw) != 3:
        raise ValueError("manifest.targets must be the three ordered native target points")
    target_names = [row["name"] for row in targets_raw]
    if len(set(target_names)) != len(target_names):
        raise ValueError("target names must be unique")
    targets = {
        row["name"]: (
            _required_int(row["i"], f"target {row['name']} i"),
            _required_int(row["j"], f"target {row['name']} j"),
        )
        for row in targets_raw
    }
    if len(set(targets.values())) != 3:
        raise ValueError("target coordinates must be unique")
    levels = _required_int(manifest["levels"], "levels")
    if levels != 39:
        raise ValueError("native moment trace replay requires 39 levels")
    global_shape = tuple(
        _required_int(x, f"global_shape_i_k_j[{n}]")
        for n, x in enumerate(manifest["global_shape_i_k_j"])
    )
    if global_shape != (234, 39, 282):
        raise ValueError("manifest global native shape must be (234,39,282) in i,k,j order")
    expected_step = _required_int(manifest["step"], "step")
    if expected_step != 3:
        raise ValueError("this trace protocol replay expects one actual step=3")
    expected_dt = _f64_from_hex(manifest["dt_hex64"], "dt_hex64")
    if expected_dt != 20.0:
        raise ValueError("manifest dt must equal the actual 20-second timestep")
    expected_land = _f64_from_hex(manifest["ncmin_land_hex64"], "ncmin_land_hex64")
    expected_sea = _f64_from_hex(manifest["ncmin_sea_hex64"], "ncmin_sea_hex64")
    levels_of_interest = tuple(
        _required_int(x, f"levels_of_interest[{n}]")
        for n, x in enumerate(manifest.get("levels_of_interest", [19, 6, 4]))
    )
    if levels_of_interest != (19, 6, 4):
        raise ValueError("levels_of_interest must be the frozen native levels (19,6,4)")

    run_results: dict[str, dict[str, Any]] = {}
    input_receipts: dict[str, dict[str, Any]] = {}
    base = manifest_path.parent
    for run in runs:
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in run_results:
            raise ValueError("run_id must be unique and nonempty")
        trace_files = run.get("traces", {})
        if set(trace_files) != {"host", "kernel"}:
            raise ValueError(f"run {run_id} must provide host and kernel trace artifacts")
        host_bytes = _read_asset(base, trace_files["host"], label=f"{run_id} host trace")
        kernel_bytes = _read_asset(base, trace_files["kernel"], label=f"{run_id} kernel trace")
        context_bytes = _read_asset(base, run["context_npz"], label=f"{run_id} context NPZ")
        context = _load_context(context_bytes, target_count=len(targets), levels=levels, run_id=run_id)
        expected_calls = _required_int(run["expected_call_count"], f"run {run_id} expected_call_count")
        if expected_calls < 1:
            raise ValueError(f"run {run_id} expected_call_count must be positive")

        # Use temporary, automatically removed parse inputs. The original trace
        # bytes have already been verified and are not rewritten in place.
        with tempfile.TemporaryDirectory(prefix="kdm6_moment_trace_v2_") as temp_name:
            temp = Path(temp_name)
            host_path = temp / "host.hex"
            kernel_path = temp / "kernel.hex"
            host_path.write_bytes(host_bytes)
            kernel_path.write_bytes(kernel_bytes)
            inventory = read_moment_trace_v2(host_path, kernel_path)
            analysis = analyze_native_moment_trace(
                inventory,
                targets=targets,
                ready_qc=context["ready_qc"],
                ready_nc=context["ready_nc"],
                final_qc=context["final_qc"],
                final_nc=context["final_nc"],
                run_id=run_id,
                expected_call_count=expected_calls,
                expected_ncmin_land=expected_land,
                expected_ncmin_sea=expected_sea,
                levels=levels,
                expected_step=expected_step,
                dt_seconds=expected_dt,
                global_shape=global_shape,
                levels_of_interest=levels_of_interest,
            )
        run_results[run_id] = analysis
        input_receipts[run_id] = {
            "host_trace_sha256": trace_files["host"]["sha256"],
            "kernel_trace_sha256": trace_files["kernel"]["sha256"],
            "context_npz_sha256": run["context_npz"]["sha256"],
            "expected_call_count": expected_calls,
        }

    comparisons = []
    for pair in manifest.get("comparisons", []):
        control_id = pair["control_run_id"]
        candidate_id = pair["candidate_run_id"]
        if control_id not in run_results or candidate_id not in run_results:
            raise ValueError(f"comparison references unknown run: {control_id}/{candidate_id}")
        comparisons.append(
            compare_native_moment_runs(
                run_results[control_id],
                run_results[candidate_id],
                levels_of_interest=levels_of_interest,
            )
        )

    optional_noninterference = None
    if "instrumentation_noninterference" in manifest:
        raw = _read_asset(base, manifest["instrumentation_noninterference"], label="instrumentation noninterference receipt")
        optional_noninterference = json.loads(raw)
    return {
        "schema": "kdm6.native_moment_trace_replay_result.v1",
        "status": "NATIVE_MOMENT_TRACE_REPLAY_PASSED",
        "input_manifest_sha256": _sha(manifest_bytes),
        "levels": levels,
        "targets": targets_raw,
        "runs": run_results,
        "input_receipts": input_receipts,
        "comparisons": comparisons,
        "instrumentation_noninterference": optional_noninterference,
        "scope_limits": [
            "Describes saved QC/NC state boundaries only; no causal mechanism is inferred.",
            "Raw number-moment physical units are not certified.",
            "QC_RATE and tendencies are not substituted for QC state.",
            "No derivative, observation-cost, or optimization claim is produced.",
        ],
        "model_calls": {"host": 0, "KDM": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("input_manifest.json"))
    args = parser.parse_args()
    result = replay_manifest(args.manifest)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
