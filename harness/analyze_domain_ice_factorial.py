"""Value-only per-column accounting of the admitted endpoint batch experiment.

No cell areas are present: statistics are unweighted column distributions,
never physical regional mass totals or map-area means. The optional uniform
cleanup/finish is an offline diagnostic, not host boundary/RK consumption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.ice_factorial_batch import pack_request, unpack_response
from harness.run_domain_ice_factorial import (
    DEFAULT_EXECUTABLE,
    DEFAULT_MANIFEST,
    MODES,
    GuardError,
    _expected_receipt,
    _load_chunk_from_bytes,
    _same_bits,
    build_plan,
    sha256,
)

N = 65988
L = 39


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def columns(values, weights):
    """Rounded binary64 products followed by fsum, field-major/level-major."""
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if (
        weights.ndim != 2
        or not weights.size
        or not np.isfinite(weights).all()
        or np.any(weights <= 0)
    ):
        raise ValueError("finite positive nonempty (B,L) weights required")
    if not np.isfinite(values).all():
        raise ValueError("finite weighted values required")
    if values.ndim == 2 and values.shape == weights.shape:
        terms = values * weights
    elif values.ndim == 3 and values.shape[1:] == weights.shape:
        terms = (values * weights[None, :, :]).transpose(1, 0, 2)
    else:
        raise ValueError("values must be (B,L) or (fields,B,L) with weights (B,L)")
    return np.fromiter(
        (math.fsum(row) for row in terms.reshape(weights.shape[0], -1)),
        dtype=np.float64,
        count=weights.shape[0],
    )


def distribution(values):
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    if not a.size or not np.isfinite(a).all():
        raise ValueError("finite nonempty statistic required")
    ordered = np.sort(a, kind="stable")
    return {
        "count": a.size,
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "unweighted_column_mean": math.fsum(a) / a.size,
        "rank_p01": float(ordered[int(0.01 * (a.size - 1))]),
        "rank_p50": float(ordered[int(0.50 * (a.size - 1))]),
        "rank_p99": float(ordered[int(0.99 * (a.size - 1))]),
    }


def admit_chunk(task, receipt_path):
    """Validate one saved chunk/receipt/response without invoking KDM6.

    Each source, request, and response file is read once. Source NPZ parsing
    uses those verified bytes, avoiding a hash-then-reopen race.
    """
    receipt_path = Path(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "complete":
        raise GuardError(f"receipt is not complete: {receipt_path.name}")
    source_path = Path(task["source_path"])
    source_bytes = source_path.read_bytes()
    if sha256(source_bytes) != task["source_sha256"]:
        raise GuardError(f"source chunk hash mismatch: {source_path.name}")
    entry = {"start_flat": task["start"], "stop_flat_exclusive": task["end"]}
    state, forcing, xland = _load_chunk_from_bytes(source_bytes, entry, task["start"])
    request_bytes = pack_request(
        state, forcing, xland, task["dt_seconds"], task["ncmin_land"], task["ncmin_sea"]
    )
    tensor_bytes = state.tobytes() + forcing.tobytes() + xland.tobytes()
    gate = _expected_receipt(task, sha256(request_bytes), sha256(tensor_bytes))
    for key, expected in gate.items():
        if receipt.get(key) != expected:
            raise GuardError(
                f"receipt admission mismatch for {key}: {receipt_path.name}"
            )
    if receipt.get("tool_sha256_after") != task["tool_sha256"]:
        raise GuardError(
            f"receipt admission mismatch for tool_sha256_after: {receipt_path.name}"
        )
    resources = receipt.get("resources", {})
    for key in ("wall", "user", "system", "wall_seconds_measured"):
        value = resources.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise GuardError(
                f"receipt lacks valid {key} measurement: {receipt_path.name}"
            )
    peak = resources.get("peak_rss_bytes")
    if type(peak) is not int or peak <= 0:
        raise GuardError(
            f"receipt lacks valid peak_rss_bytes measurement: {receipt_path.name}"
        )

    request_path = receipt_path.with_name(
        receipt_path.name.replace(".receipt.json", ".request.bin")
    )
    saved_request = request_path.read_bytes()
    if saved_request != request_bytes:
        raise GuardError(
            f"saved request differs from verified source tensors: {request_path.name}"
        )
    response_path = receipt_path.with_name(
        receipt_path.name.replace(".receipt.json", ".response.bin")
    )
    response_bytes = response_path.read_bytes()
    if sha256(response_bytes) != receipt.get("response_sha256"):
        raise GuardError(f"response hash differs from receipt: {response_path.name}")
    response = unpack_response(response_bytes)
    if response["B"] != task["B"] or response["L"] != task["L"]:
        raise GuardError(
            f"response shape differs from admitted chunk: {response_path.name}"
        )
    if not _same_bits(response["state_in"], state) or not _same_bits(
        response["forcing_in"], forcing
    ):
        raise GuardError(
            f"response echo differs from verified source tensors: {response_path.name}"
        )
    return response


def analyze(
    run_root,
    finish_reference,
    output,
    *,
    manifest=DEFAULT_MANIFEST,
    executable=DEFAULT_EXECUTABLE,
):
    import torch
    from harness.verify_native_finish_ad import _api, _zero_value, finish_value

    torch.set_num_threads(1)
    root, output = Path(run_root), Path(output)
    reference = json.loads(Path(finish_reference).read_text())
    config, zero = reference["configuration"], reference["zero_out"]
    if config["dt"] != 20.0 or zero["mode"] != 2:
        raise ValueError(
            "requires the audited dt20 uniform interior-rule finish diagnostic"
        )
    plans = {
        mode: build_plan(
            manifest,
            executable,
            mode=mode,
            workers=10,
            dt=20.0,
            ncmin_land=10.0,
            ncmin_sea=10.0,
        )
        for mode in MODES
    }
    output.mkdir(parents=True, exist_ok=False)
    metrics = {}
    for mode in MODES:
        mode_root = root / "full" / mode
        plan = plans[mode]
        rows = [
            mode_root / f"chunk-{row['index']:05d}.receipt.json"
            for row in plan["chunks"]
        ]
        if len(rows) != plan["chunk_count"] or not all(path.is_file() for path in rows):
            raise ValueError(f"incomplete arm receipts: {mode}")
        arrays = {
            key: np.empty(N, dtype=np.float64)
            for key in (
                "raw_water_change",
                "cleanup_water_change",
                "applied_water_change",
                "reported_total_precip_mm",
                "snow_ice_subset_mm",
                "graupel_subset_mm",
                "raw_plus_reported_precip_residual",
                "numerical_gate",
                "H_RATE_column_dry_mass_mean",
                "QV_RATE_column",
                "QC_RATE_column",
                "raw_dry_theta_change_column_mean",
            )
        }
        finish_profiles = np.empty((5, N, L), dtype=np.float64)
        covered = np.zeros(N, dtype=bool)
        negative_raw = np.zeros(12, dtype=np.int64)
        theta_min = math.inf
        for index, (receipt_path, task) in enumerate(zip(rows, plan["chunks"])):
            start, end = task["start"], task["end"]
            if (
                task["index"] != index
                or start != index * 512
                or end != min(start + 512, N)
            ):
                raise GuardError("planned mode/index/coverage differs")
            response = admit_chunk(task, receipt_path)
            s, f, raw, precip = (
                response[k] for k in ("state_in", "forcing_in", "state_out", "precip")
            )
            if (
                response["L"] != L
                or response["B"] != end - start
                or covered[start:end].any()
            ):
                raise ValueError("response native dimensions or coverage differ")
            if np.any(precip < 0) or np.any(
                precip[1] + precip[2]
                > precip[0] + 32 * np.finfo(float).eps * np.maximum(1.0, precip[0])
            ):
                raise ValueError("invalid total/subset precipitation")
            negative_raw += np.count_nonzero(raw < 0, axis=(1, 2))
            theta_min = min(theta_min, float(raw[0].min()))
            weights = f[0] * f[3]
            clean = raw.copy()
            clean[1] = np.maximum(raw[1], 0.0)
            clean[2:7] = np.where(raw[2:7] < zero["threshold"], 0.0, raw[2:7])
            raw_change = columns(raw[1:7] - s[1:7], weights)
            cleanup = columns(clean[1:7] - raw[1:7], weights)
            applied_change = columns(clean[1:7] - s[1:7], weights)
            before, after = (
                columns(abs(s[1:7]), weights),
                columns(abs(raw[1:7]), weights),
            )
            residual = np.fromiter(
                (math.fsum((a, p)) for a, p in zip(raw_change, precip[0])),
                dtype=np.float64,
            )
            gate = (
                256
                * np.finfo(float).eps
                * np.maximum(1.0, before + after + abs(precip[0]))
            )
            with torch.no_grad():
                finish = finish_value(
                    s[:3],
                    _zero_value(raw[:3], _api().ZeroOutConfig(**zero)),
                    _api().FinishConfig(**config),
                )
            if not np.isfinite(finish).all():
                raise ValueError("nonfinite offline finish")
            dry_mass = np.fromiter(
                (math.fsum(row) for row in weights), dtype=np.float64
            )
            values = (
                raw_change,
                cleanup,
                applied_change,
                precip[0],
                precip[1],
                precip[2],
                residual,
                gate,
                columns(finish[1], weights) / dry_mass,
                columns(finish[2], weights),
                columns(finish[3], weights),
                columns(raw[0] - s[0], weights) / dry_mass,
            )
            for key, value in zip(arrays, values):
                arrays[key][start:end] = value
            finish_profiles[:, start:end] = finish
            covered[start:end] = True
        if not covered.all():
            raise ValueError("arm column coverage incomplete")
        path = output / (mode + ".npz")
        with path.open("xb") as stream:
            np.savez(stream, **arrays, applied_finish=finish_profiles)
        passed_gate = (
            abs(arrays["raw_plus_reported_precip_residual"]) <= arrays["numerical_gate"]
        )
        metrics[mode] = {
            "columns": N,
            "completed_chunks": len(rows),
            "minimum_raw_dry_theta_K": theta_min,
            "negative_raw_counts_by_state_row": negative_raw.tolist(),
            "within_diagnostic_balance_gate_columns": int(passed_gate.sum()),
            "outside_diagnostic_balance_gate_columns": int((~passed_gate).sum()),
            "statistics": {
                key: distribution(value)
                for key, value in arrays.items()
                if key != "numerical_gate"
            },
            "analysis_npz": path.name,
            "analysis_npz_sha256": sha(path),
            "closed_water_budget_certified": False,
        }
        print(
            json.dumps(
                {
                    "mode": mode,
                    "columns": N,
                    "outside_balance_gate": metrics[mode][
                        "outside_diagnostic_balance_gate_columns"
                    ],
                }
            ),
            flush=True,
        )
    comparisons = {}
    with np.load(output / "raw_cap.npz", allow_pickle=False) as ref:
        for mode in MODES[1:]:
            with np.load(output / (mode + ".npz"), allow_pickle=False) as arm:
                delta = arm["applied_finish"][1] - ref["applied_finish"][1]
                comparisons[mode] = {
                    "raw_water_change_difference": distribution(
                        arm["raw_water_change"] - ref["raw_water_change"]
                    ),
                    "raw_balance_residual_difference": distribution(
                        arm["raw_plus_reported_precip_residual"]
                        - ref["raw_plus_reported_precip_residual"]
                    ),
                    "H_RATE_profile_maxabs_difference_per_column": distribution(
                        np.max(abs(delta), axis=1)
                    ),
                    "columns_with_any_H_RATE_bit_change": int(
                        np.any(
                            arm["applied_finish"][1].view("u8")
                            != ref["applied_finish"][1].view("u8"),
                            axis=1,
                        ).sum()
                    ),
                }
    result = {
        "schema": "kdm6.domain_ice_factorial_analysis.v1",
        "modes": metrics,
        "comparisons_to_raw_cap": comparisons,
        "producer_sha256": sha(__file__),
        "finish_reference_sha256": sha(finish_reference),
        "manifest_sha256": plans[MODES[0]]["manifest_sha256"],
        "tool_sha256": plans[MODES[0]]["tool_sha256"],
        "execution_configuration": {
            "dt_seconds": 20.0,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "chunk_columns": 512,
            "workers_per_arm": 10,
            "arms_execute_sequentially": True,
        },
        "units": {
            "water_changes": "kg/m2 per column; fixed input DEN*DELZ measure",
            "precipitation": "reported code diagnostic mm per column; total includes all species",
            "H_RATE": "offline moist-theta rate K/s; not physical T or BT change",
            "QV_QC_RATE_column": "kg/m2/s per column",
        },
        "statistics_contract": "fsum of rounded binary64 weighted terms; all spatial statistics unweighted column distributions, no cell areas; rank quantiles select sorted values without interpolation",
        "cleanup_finish_scope": "Uniform configured interior-rule cleanup/finish applied offline at every stored column; host boundary cleanup, RK/dynamics and retained-memory consumption not emulated",
        "limits": [
            "Raw velocity/code-flux dimensions and number payload basis remain conditional.",
            "No physical regional kg totals or map-area weighted averages are reported.",
            "No new-map AD/RTTOV/forecast skill certificate; reported balance gate is a diagnostic, not conservation proof.",
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-root", "finish-reference", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXECUTABLE)
    args = parser.parse_args()
    analyze(
        args.run_root,
        args.finish_reference,
        args.output,
        manifest=args.manifest,
        executable=args.executable,
    )
