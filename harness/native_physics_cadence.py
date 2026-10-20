"""Prepare a hash-bound restart with radiation scheduled every model step.

This is a checkpoint seed transformation only. It changes ``STEPRA`` and
preserves the source checkpoint; it does not run or certify any physics scheme.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np

from harness.native_host_transition import (
    NativeCheckpoint,
    _copy_checkpoint,
    compare_restart_metadata,
    file_sha256,
)
from harness.native_replay_compare import compare_frames


def _unused_staging_path(parent: Path, prefix: str) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, dir=parent)
    os.close(fd)
    path = Path(name)
    path.unlink()
    return path


def _write_receipt_staging(path: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_radiation_step_restart(
    state: NativeCheckpoint,
    target: str | Path,
    receipt: str | Path,
) -> NativeCheckpoint:
    """Create a separate checkpoint whose sole changed field is ``STEPRA=1``.

    The source is revalidated before and after staging. The target and receipt
    must not exist. The target is prepared beside its final path, compared
    against the source, and hard-link published without overwriting either
    destination. A failed receipt publication rolls back a target link created
    by this call.
    """
    if not isinstance(state, NativeCheckpoint):
        raise TypeError("state must be a validated NativeCheckpoint")
    if state._validated_sha256 != state.file.sha256:
        raise ValueError("source checkpoint lacks a capture validation certificate")
    source = state.file.path.resolve(strict=True)
    state.file.verify()
    target_path = Path(target).expanduser().absolute()
    receipt_path = Path(receipt).expanduser().absolute()
    if target_path.resolve(strict=False) == source or receipt_path.resolve(strict=False) == source:
        raise ValueError("source, target and receipt paths must be distinct")
    if target_path.resolve(strict=False) == receipt_path.resolve(strict=False):
        raise ValueError("target and receipt paths must be distinct")
    if not target_path.parent.is_dir() or not receipt_path.parent.is_dir():
        raise ValueError("target and receipt parent directories must already exist")
    for final in (target_path, receipt_path):
        if final.exists() or final.is_symlink():
            raise FileExistsError(final)

    verified_source = NativeCheckpoint.capture(
        source, expected_time=state.time, expected_itimestep=state.itimestep,
        receipt=state.receipt,
    )
    if verified_source.schema != state.schema:
        raise ValueError("source checkpoint schema changed since state capture")
    if verified_source.file.sha256 != state.file.sha256:
        raise RuntimeError("source checkpoint bytes changed since state capture")
    source_sha256 = verified_source.file.sha256

    import netCDF4

    with netCDF4.Dataset(source, "r") as ds:
        ds.set_auto_maskandscale(False)
        if "STEPRA" not in ds.variables:
            raise ValueError("source checkpoint is missing STEPRA")
        variable = ds["STEPRA"]
        if (np.dtype(variable.dtype) != np.dtype("int32")
                or variable.size != 1
                or tuple(variable.dimensions) not in ((), ("Time",))):
            raise ValueError("STEPRA must be one scalar int32 value")
        source_stepra = np.asarray(variable[:])
        if source_stepra.size != 1:
            raise ValueError("STEPRA must contain exactly one value")
        old_stepra = int(source_stepra.reshape(-1)[0])
        if old_stepra <= 0:
            raise ValueError("source STEPRA must be positive")

    target_stage = _unused_staging_path(target_path.parent, f".{target_path.name}.stepra-")
    receipt_stage = _unused_staging_path(receipt_path.parent, f".{receipt_path.name}.stepra-")
    target_published = False
    try:
        _copy_checkpoint(source, target_stage)
        with netCDF4.Dataset(target_stage, "r+") as ds:
            ds.set_auto_maskandscale(False)
            var = ds["STEPRA"]
            if tuple(var.dimensions) == ():
                var.assignValue(np.int32(1))
            else:
                var[0] = np.int32(1)
            ds.sync()

        candidate = NativeCheckpoint.capture(
            target_stage, expected_time=state.time, expected_itimestep=state.itimestep,
            receipt=receipt_path,
        )
        if candidate.schema != verified_source.schema:
            raise RuntimeError("STEPRA preparation changed checkpoint variable schema")
        with netCDF4.Dataset(source, "r") as before, netCDF4.Dataset(target_stage, "r") as after:
            before.set_auto_maskandscale(False)
            after.set_auto_maskandscale(False)
            comparison = compare_frames(before, after, 0, 0, state.time)
            metadata = compare_restart_metadata(before, after)

        variable_reports = comparison.get("variables", {})
        changed = sorted(
            name for name, report in variable_reports.items()
            if report.get("raw_bitwise_equal") is not True
        )
        expected_changed = ["STEPRA"] if old_stepra != 1 else []
        if (comparison.get("missing_variables") or comparison.get("extra_variables")
                or changed != expected_changed
                or not comparison.get("finite")
                or not comparison.get("complete_values")
                or comparison.get("variables", {}).get("STEPRA", {}).get("raw_bitwise_equal")
                   is not (old_stepra == 1)
                or not metadata.get("passed")
                or metadata.get("differences")
                or metadata.get("output_ringing_normalizations")):
            raise RuntimeError("prepared checkpoint differs outside the exact STEPRA change contract")

        target_sha256 = candidate.file.sha256
        receipt_payload = {
            "schema": "kdm6ad.native_stepra_seed.v1",
            "scope": "restart seed only; STEPRA cadence field change, no model execution",
            "source_path": str(source),
            "source_sha256": source_sha256,
            "target_path": str(target_path),
            "target_sha256": target_sha256,
            "time": state.time,
            "itimestep": state.itimestep,
            "variable": "STEPRA",
            "source_stepra": old_stepra,
            "target_stepra": 1,
            "changed_variables": changed,
            "expected_changed_variables": expected_changed,
            "comparison": {
                "variable_count": comparison.get("variable_count_reference"),
                "numeric_elements_compared": comparison.get("numeric_elements_compared"),
                "numeric_element_mismatches": comparison.get("numeric_element_mismatches"),
                "raw_bitwise_equal": comparison.get("raw_bitwise_equal"),
                "finite": comparison.get("finite"),
                "complete_values": comparison.get("complete_values"),
            },
            "metadata": metadata,
        }
        _write_receipt_staging(receipt_stage, receipt_payload)
        verified_source.file.verify()
        if target_path.exists() or target_path.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
            raise FileExistsError("target or receipt appeared after preflight")

        os.link(target_stage, target_path)
        target_published = True
        try:
            os.link(receipt_stage, receipt_path)
        except BaseException:
            # Only unlink the exact inode this invocation just published.
            staged_stat, final_stat = target_stage.stat(), target_path.stat()
            if (staged_stat.st_dev, staged_stat.st_ino) == (final_stat.st_dev, final_stat.st_ino):
                target_path.unlink()
                target_published = False
            raise
        return NativeCheckpoint.capture(
            target_path, expected_time=state.time, expected_itimestep=state.itimestep,
            receipt=receipt_path,
        )
    finally:
        target_stage.unlink(missing_ok=True)
        receipt_stage.unlink(missing_ok=True)
        # Defensive cleanup if publication failed after target link but before
        # the receipt link rollback path ran.
        if target_published and not receipt_path.exists():
            try:
                target_path.unlink()
            except FileNotFoundError:
                pass
