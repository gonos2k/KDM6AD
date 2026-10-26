#!/usr/bin/env python3
"""Replay hash-bound, saved native QNC RK records without model calls."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile

import numpy as np

from harness.analyze_upstream_nc_trace import (
    TARGETS,
    analyze_upstream_nc_trace,
    read_upstream_nc_trace,
)
from harness.native_moment_trace_records import read_moment_trace_v2


SCHEMA = "kdm6.native_upstream_nc_replay_inputs.v1"
CONTEXT_KEYS = {"ready_qc", "ready_nc", "final_qc", "final_nc"}


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _asset(base: Path, item: dict, label: str) -> bytes:
    rel = Path(item["file"])
    if rel.is_absolute() or rel.is_symlink():
        raise ValueError(f"{label} must name a relative, regular asset")
    path = (base / rel).resolve(strict=True)
    if base.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"{label} escapes the replay packet")
    raw = path.read_bytes()
    if len(raw) != _integer(item["bytes"], f"{label} byte count"):
        raise ValueError(f"{label} byte count differs")
    if sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError(f"{label} SHA-256 differs")
    return raw


def _context(raw: bytes, run_id: str) -> dict[str, np.ndarray]:
    try:
        with np.load(BytesIO(raw), allow_pickle=False) as archive:
            if set(archive.files) != CONTEXT_KEYS:
                raise ValueError("unexpected context fields")
            result = {key: np.array(archive[key], copy=True) for key in CONTEXT_KEYS}
    except (OSError, ValueError) as exc:
        raise ValueError(f"{run_id} context is invalid: {exc}") from exc
    for key, array in result.items():
        if array.dtype != np.float32 or array.shape != (3, 39) or not np.isfinite(array).all():
            raise ValueError(f"{run_id} {key} must be finite float32[3,39]")
    return result


def _f32_bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _context_links(upstream, kdm, context, targets) -> dict:
    links = {}
    for spec in targets:
        name = spec["name"]
        i, j, k = (spec[key] for key in ("i", "j", "k"))
        row = spec["prior_context_row"]
        ready = _f32_bits(context["ready_nc"][row, k - 1])
        first = upstream.at((i, j, k), 1, "RKSCALAR_BEFORE", "QNC").bits
        rk3 = upstream.at((i, j, k), 3, "RKSCALAR_AFTER", "QNC").bits
        premicro = upstream.at((i, j, k), 0, "PRE_MICROPHYSICS", "QNC").bits
        owners = [call for call, header in kdm.headers.items() if header.step == 3 and header.owns(i, j)]
        if len(owners) != 1:
            raise ValueError(f"{name} must have one KDM owner")
        final_key = (owners[0], "MOMENTS_POST", i, k, j, "NC")
        final = _f32_bits(context["final_nc"][row, k - 1])
        finish = kdm.values[final_key].bits
        if ready != first or rk3 != premicro or final != finish:
            raise ValueError(f"{name} state boundary bits disagree")
        links[name] = {
            "ready40_nc_bits_hex": f"{ready:08X}",
            "rk1_input_nc_bits_hex": f"{int(first):08X}",
            "final_nc_bits_hex": f"{final:08X}",
            "finish_nc_bits_hex": f"{int(finish):08X}",
            "ready_to_rk1_bitwise_match": True,
            "rk3_to_premicro_bitwise_match": True,
            "finish_to_final_bitwise_match": True,
            "ready40_qc": float(context["ready_qc"][row, k - 1]),
            "final_qc": float(context["final_qc"][row, k - 1]),
        }
    return links


def replay_manifest(path: Path) -> dict:
    path = Path(path)
    raw_manifest = path.read_bytes()
    manifest = json.loads(raw_manifest)
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"expected {SCHEMA}")
    targets = manifest["targets"]
    if (len(targets) != 2 or
            {row["name"]: tuple(_integer(row[key], f"target {row['name']} {key}")
                                for key in ("i", "j", "k")) for row in targets} != dict(TARGETS)):
        raise ValueError("unexpected native witness coordinates")
    if [_integer(row["prior_context_row"], "prior context row") for row in targets] != [1, 2]:
        raise ValueError("unexpected PR455 context row mapping")
    if set(manifest["runs"]) != {"control", "alpha025"}:
        raise ValueError("expected control and alpha025 runs")

    base = path.parent
    runs = {}
    for case in ("control", "alpha025"):
        item = manifest["runs"][case]
        run_id = item["run_id"]
        if run_id != f"{case}_upstream_nc_v6_on":
            raise ValueError(f"unexpected {case} run ID")
        verified = {
            label: _asset(base, item[label], f"{case} {label}")
            for label in ("upstream_trace", "host_trace", "kernel_trace", "context")
        }
        context = _context(verified["context"], run_id)
        with tempfile.TemporaryDirectory(prefix="kdm6_upstream_nc_") as temp_name:
            temp = Path(temp_name)
            for label, filename in (("upstream_trace", "upstream_nc.tsv"),
                                    ("host_trace", "host.hex"),
                                    ("kernel_trace", "kernel.hex")):
                (temp / filename).write_bytes(verified[label])
            upstream = read_upstream_nc_trace(temp / "upstream_nc.tsv")
            kdm = read_moment_trace_v2(temp / "host.hex", temp / "kernel.hex")
            analysis = analyze_upstream_nc_trace(
                upstream, run_id=run_id, kdm_trace=kdm, kdm_run_id=run_id
            )
            links = _context_links(upstream, kdm, context, targets)
        for target in analysis["targets"].values():
            if not target["pre_microphysics_matches_kdm_mp_input"]["bitwise_match"]:
                raise ValueError(f"{case} premicro state differs from KDM input")
            if not target["pd_step3"]["scalar_old_bitwise_match"]:
                raise ValueError(f"{case} positive-def update replay differs")
            for step in target["generic_rk_steps"]:
                if not (step["source_order"]["qnc_bitwise_match"] or
                        step["fused_candidate"]["qnc_bitwise_match"]):
                    raise ValueError(f"{case} generic RK replay differs")
        runs[case] = {"analysis": analysis, "context_links": links}

    receipt_raw = _asset(base, manifest["execution_summary"], "execution summary")
    receipt = json.loads(receipt_raw)
    if (_integer(receipt.get("executed_steps"), "executed_steps") != 4
            or _integer(receipt.get("executed_kdm_wrapper_entries"), "KDM wrapper entries") != 8
            or _integer(receipt.get("new_rttov_calls"), "RTTOV calls") != 0
            or _integer(receipt.get("optimizer_calls"), "optimizer calls") != 0
            or len(receipt.get("pairs", [])) != 2
            or not all(row["full_checkpoint_raw_bitwise_equal"] is True
                       and row["ack_byte_identical"] is True
                       for row in receipt["pairs"])):
        raise ValueError("execution summary does not describe two complete pairs")
    return {
        "schema": "kdm6.native_upstream_nc_replay_result.v1",
        "status": "UPSTREAM_NC_REPLAY_PASSED",
        "input_manifest_sha256": sha256(raw_manifest).hexdigest(),
        "runs": runs,
        "execution_summary": receipt,
        "scope": "Saved-state arithmetic replay; model, RTTOV and optimizer are not called.",
        "replay_model_calls": {"host": 0, "KDM": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("input_manifest.json"))
    args = parser.parse_args()
    print(json.dumps(replay_manifest(args.manifest), sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
