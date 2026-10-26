"""Strict native QC/NC trace reader for the separate V2 moment trace format.

V1 tracing remains in :mod:`harness.native_trace_records`. V2 reads host and
kernel files independently, preserves raw IEEE bits, binds duplicate call
headers across owners only when every header field is identical, and provides
explicit global-i/j to local-batch indexing for non-square tiles.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import struct
from typing import Mapping

import numpy as np


MOMENT_TRACE_V2_MAGIC = "# KDM6AD_MOMENT_TRACE_V2"
HOST_STAGE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "MP_INPUT": ("QC", "NC"),
    "MP_OUTPUT": ("QC", "NC"),
    "HOST_WRITEBACK": ("QC", "NC"),
    "WRAPPER_POST": ("QC", "NC"),
    "ZERO_OUT_PRE": ("QC", "NC"),
    "MOMENTS_PRE": ("QC", "NC"),
    "MOMENTS_POST": ("QC", "NC"),
}
KERNEL_STAGE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "FP64_INPUT": ("QC", "NC"),
    "FP64_OUTPUT": ("QC", "NC"),
}
STAGE_OWNER = {
    **{name: "host" for name in HOST_STAGE_FIELDS},
    **{name: "kernel" for name in KERNEL_STAGE_FIELDS},
}
STAGE_DTYPE = {
    **{name: "f32" for name in HOST_STAGE_FIELDS},
    **{name: "f64" for name in KERNEL_STAGE_FIELDS},
}
_UINT = re.compile(r"[0-9]+\Z")
_HEX32 = re.compile(r"[0-9A-Fa-f]{8}\Z")
_HEX64 = re.compile(r"[0-9A-Fa-f]{16}\Z")


@dataclass(frozen=True)
class MomentCallHeader:
    """One wrapper-call header. Bounds are one-based inclusive indices."""

    call_id: int
    step: int
    its: int
    ite: int
    kts: int
    kte: int
    jts: int
    jte: int
    im: int
    km: int
    jm: int
    dt_bits: int
    ncmin_land_bits: int
    ncmin_sea_bits: int

    @property
    def dt(self) -> float:
        return _f64_from_bits(self.dt_bits)

    @property
    def ncmin_land(self) -> float:
        return _f64_from_bits(self.ncmin_land_bits)

    @property
    def ncmin_sea(self) -> float:
        return _f64_from_bits(self.ncmin_sea_bits)

    @property
    def jme(self) -> int:
        """Number of j positions in the local tile (validated against its bounds)."""
        return self.jm

    def owns(self, i: int, j: int) -> bool:
        return self.its <= i <= self.ite and self.jts <= j <= self.jte

    def global_to_local_batch_index(self, i: int, j: int) -> int:
        """Map one-based global (i,j) to the producer's i-major local batch.

        The producer packs a tile as ``local_i * jme + local_j``. This helper
        makes that order explicit and avoids silently swapping non-square axes.
        """
        if not self.owns(i, j):
            raise ValueError(f"global point ({i},{j}) is outside call {self.call_id} tile bounds")
        local_i = i - self.its
        local_j = j - self.jts
        return local_i * self.jme + local_j


@dataclass(frozen=True)
class MomentTraceValue:
    """One raw QC/NC value, retaining the binary32/binary64 bit pattern."""

    owner: str
    call_id: int
    stage: str
    i: int
    k: int
    j: int
    dtype: str
    field: str
    bits: int

    @property
    def value(self) -> np.float32 | np.float64:
        if self.dtype == "f32":
            return np.asarray([self.bits], dtype=np.uint32).view(np.float32)[0]
        return np.asarray([self.bits], dtype=np.uint64).view(np.float64)[0]


@dataclass(frozen=True)
class MomentTraceInventory:
    """Merged host/kernel V2 records. Keys omit owner to reject duplicate values."""

    headers: Mapping[int, MomentCallHeader]
    header_owners: Mapping[int, tuple[str, ...]]
    values: Mapping[tuple[int, str, int, int, int, str], MomentTraceValue]
    call_ids_by_owner: Mapping[str, tuple[int, ...]]
    source_files: Mapping[str, str]

    @property
    def call_count(self) -> int:
        return len(self.headers)


@dataclass(frozen=True)
class StageCoverage:
    """Coverage for one call, owner, target and expected stage."""

    call_id: int
    owner: str
    target_name: str
    target_i: int
    target_j: int
    local_batch_index: int
    stage: str
    fields: tuple[str, ...]
    missing: tuple[tuple[int, str], ...]

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class MomentTraceCoverage:
    call_ids: tuple[int, ...]
    call_count: int
    values_count: int
    coverage: tuple[StageCoverage, ...]
    calls_without_kernel_witness: tuple[int, ...]
    calls_with_owned_targets_without_kernel_witness: tuple[int, ...]
    unowned_targets: tuple[str, ...]
    complete: bool


def _parse_uint(token: str, label: str, line: int) -> int:
    if not _UINT.fullmatch(token):
        raise ValueError(f"line {line}: {label} must be an unsigned decimal integer")
    return int(token, 10)


def _f64_from_bits(bits: int) -> float:
    return struct.unpack(">d", bits.to_bytes(8, "big"))[0]


def _expected_f64_bits(value: float, label: str) -> int:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return int.from_bytes(struct.pack(">d", converted), "big")


def _parse_hex(token: str, dtype: str, label: str, line: int) -> int:
    pattern = _HEX32 if dtype == "f32" else _HEX64
    if not pattern.fullmatch(token):
        expected = 8 if dtype == "f32" else 16
        raise ValueError(f"line {line}: {label} must be exactly {expected} hexadecimal digits")
    bits = int(token, 16)
    value = (
        np.asarray([bits], dtype=np.uint32).view(np.float32)[0]
        if dtype == "f32"
        else _f64_from_bits(bits)
    )
    if not np.isfinite(value):
        raise ValueError(f"line {line}: {label} contains a nonfinite {dtype} value")
    return bits


def _parse_header(tokens: list[str], line: int) -> MomentCallHeader:
    if len(tokens) != 15 or tokens[0] != "CALL":
        raise ValueError(f"line {line}: CALL header requires 15 tokens")
    labels = ("call_id", "step", "its", "ite", "kts", "kte", "jts", "jte", "im", "km", "jm")
    ints = tuple(_parse_uint(token, label, line) for token, label in zip(tokens[1:12], labels))
    if any(value < 1 for value in ints):
        raise ValueError(f"line {line}: call id, step, bounds and dimensions must be positive")
    call_id, step, its, ite, kts, kte, jts, jte, im, km, jm = ints
    if its > ite or kts > kte or jts > jte:
        raise ValueError(f"line {line}: inclusive tile bounds are reversed")
    if (im, km, jm) != (ite - its + 1, kte - kts + 1, jte - jts + 1):
        raise ValueError(f"line {line}: im/km/jm must equal inclusive local tile extents")
    dt = _parse_hex(tokens[12], "f64", "dt_hex64", line)
    ncmin_land = _parse_hex(tokens[13], "f64", "ncmin_land_hex64", line)
    ncmin_sea = _parse_hex(tokens[14], "f64", "ncmin_sea_hex64", line)
    if _f64_from_bits(ncmin_land) < 0.0 or _f64_from_bits(ncmin_sea) < 0.0:
        raise ValueError(f"line {line}: ncmin values must be nonnegative")
    return MomentCallHeader(
        call_id, step, its, ite, kts, kte, jts, jte, im, km, jm,
        dt, ncmin_land, ncmin_sea,
    )


def _read_one_file(path: Path) -> tuple[str, dict[int, MomentCallHeader], dict[tuple[int, str, int, int, int, str], MomentTraceValue], tuple[int, ...]]:
    source = Path(path)
    owner = source.stem
    if owner not in ("host", "kernel"):
        raise ValueError(f"trace owner must be host or kernel, got {owner!r}")
    try:
        lines = source.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read ASCII moment trace {source}: {exc}") from exc
    if not lines or lines[0] != MOMENT_TRACE_V2_MAGIC:
        raise ValueError(f"{owner} trace must begin with {MOMENT_TRACE_V2_MAGIC}")

    headers: dict[int, MomentCallHeader] = {}
    values: dict[tuple[int, str, int, int, int, str], MomentTraceValue] = {}
    ordered_call_ids: list[int] = []
    for line_number, raw_line in enumerate(lines[1:], start=2):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        if tokens[0] == "CALL":
            header = _parse_header(tokens, line_number)
            if header.call_id in headers:
                raise ValueError(f"line {line_number}: duplicate CALL header within {owner} file for {header.call_id}")
            if ordered_call_ids and header.call_id <= ordered_call_ids[-1]:
                raise ValueError(f"line {line_number}: CALL ids must be monotonically increasing in {owner} file")
            headers[header.call_id] = header
            ordered_call_ids.append(header.call_id)
            continue
        if tokens[0] != "VAL" or len(tokens) != 9:
            raise ValueError(f"line {line_number}: VAL record requires 9 tokens")
        call_id = _parse_uint(tokens[1], "call_id", line_number)
        if call_id not in headers:
            raise ValueError(f"line {line_number}: VAL references call {call_id} before a CALL header in {owner} file")
        stage = tokens[2]
        if stage not in STAGE_OWNER:
            raise ValueError(f"line {line_number}: unknown moment trace stage {stage!r}")
        i, k, j = (_parse_uint(token, label, line_number) for token, label in zip(tokens[3:6], ("i", "k", "j")))
        if min(i, k, j) < 1:
            raise ValueError(f"line {line_number}: native coordinates must be one-based positive integers")
        dtype = tokens[6]
        expected_dtype = STAGE_DTYPE[stage]
        if dtype != expected_dtype:
            raise ValueError(f"line {line_number}: {stage} requires {expected_dtype}, got {dtype}")
        field = tokens[7]
        if field not in (HOST_STAGE_FIELDS.get(stage) or KERNEL_STAGE_FIELDS.get(stage)):
            raise ValueError(f"line {line_number}: field {field!r} is not valid for {stage}")
        header = headers[call_id]
        if not (header.its <= i <= header.ite and header.jts <= j <= header.jte and header.kts <= k <= header.kte):
            raise ValueError(f"line {line_number}: value coordinate is outside its CALL tile bounds")
        bits = _parse_hex(tokens[8], dtype, "value_hex", line_number)
        key = (call_id, stage, i, k, j, field)
        if key in values:
            raise ValueError(f"line {line_number}: duplicate VAL key across trace owners/files: {key}")
        values[key] = MomentTraceValue(owner, call_id, stage, i, k, j, dtype, field, bits)
    if not headers:
        raise ValueError(f"{owner} trace contains no CALL headers")
    return owner, headers, values, tuple(ordered_call_ids)


def read_moment_trace_v2(host_path: str | Path, kernel_path: str | Path) -> MomentTraceInventory:
    """Parse V2 host/kernel files and merge their matching CALL headers.

    Exact duplicate CALL headers are expected across host/kernel files. A call
    may be header-only in the kernel trace; it remains in the inventory and is
    reported as a missing-witness call by :func:`validate_moment_trace_v2`.
    Duplicate value keys are rejected across both files.
    """
    owners = {}
    per_owner_headers = {}
    per_owner_values = {}
    order = {}
    for path in (host_path, kernel_path):
        owner, headers, values, call_ids = _read_one_file(Path(path))
        if owner in owners:
            raise ValueError(f"multiple V2 trace inputs use owner stem {owner!r}")
        owners[owner] = Path(path)
        per_owner_headers[owner] = headers
        per_owner_values[owner] = values
        order[owner] = call_ids
    if set(owners) != {"host", "kernel"}:
        raise ValueError("V2 trace requires one host.hex and one kernel.hex input")
    if order["host"] != order["kernel"]:
        raise ValueError("host/kernel CALL header inventories or order differ")
    call_ids = order["host"]
    if call_ids != tuple(range(1, len(call_ids) + 1)):
        raise ValueError("CALL ids must be contiguous, one-based, and monotonically increasing")

    merged_headers: dict[int, MomentCallHeader] = {}
    header_owners: dict[int, tuple[str, ...]] = {}
    for call_id in call_ids:
        host_header = per_owner_headers["host"][call_id]
        kernel_header = per_owner_headers["kernel"][call_id]
        if host_header != kernel_header:
            raise ValueError(f"CALL header {call_id} differs between host and kernel files")
        merged_headers[call_id] = host_header
        header_owners[call_id] = ("host", "kernel")
    merged_values = dict(per_owner_values["host"])
    for key, record in per_owner_values["kernel"].items():
        if key in merged_values:
            raise ValueError(f"duplicate VAL key across host/kernel files: {key}")
        merged_values[key] = record
    for record in merged_values.values():
        expected_owner = STAGE_OWNER[record.stage]
        if record.owner != expected_owner:
            raise ValueError(
                f"stage {record.stage} belongs in {expected_owner}.hex, not {record.owner}.hex"
            )
    return MomentTraceInventory(
        headers=merged_headers,
        header_owners=header_owners,
        values=merged_values,
        call_ids_by_owner=order,
        source_files={"host":str(Path(host_path)),"kernel":str(Path(kernel_path))},
    )


def validate_moment_trace_v2(
    inventory: MomentTraceInventory,
    *,
    targets: Mapping[str, tuple[int, int]],
    levels: int = 39,
    expected_call_count: int | None = None,
    expected_step: int = 3,
    expected_dt: float = 20.0,
    expected_ncmin_land: float,
    expected_ncmin_sea: float,
    expected_global_shape: tuple[int, int, int] = (234, 39, 282),
    require_complete: bool = True,
) -> MomentTraceCoverage:
    """Validate scalar contracts and host/kernel QC/NC stage coverage.

    ``expected_global_shape`` is ordered ``(global_im,global_km,global_jm)``;
    each CALL header's im/km/jm fields are local tile extents, validated against
    its inclusive its:ite, kts:kte, jts:jte bounds. ``require_complete``
    raises by default if any target stage lacks one of its QC/NC values at any
    requested level. Set ``require_complete=False`` only for diagnostics; missing
    stage/level records and header-only kernel calls remain visible in the report.
    """
    if not isinstance(inventory, MomentTraceInventory):
        raise TypeError("inventory must be MomentTraceInventory from read_moment_trace_v2")
    if not targets:
        raise ValueError("targets must contain at least one named native (i,j) coordinate")
    if type(levels) is not int or levels < 1:
        raise ValueError("levels must be a positive integer")
    if expected_call_count is not None and (type(expected_call_count) is not int or expected_call_count < 1):
        raise ValueError("expected_call_count must be a positive integer")
    expected_dt_bits = _expected_f64_bits(expected_dt, "expected_dt")
    expected_land_bits = _expected_f64_bits(expected_ncmin_land, "expected_ncmin_land")
    expected_sea_bits = _expected_f64_bits(expected_ncmin_sea, "expected_ncmin_sea")
    if expected_dt <= 0.0 or expected_ncmin_land < 0.0 or expected_ncmin_sea < 0.0:
        raise ValueError("dt must be positive and ncmin values nonnegative")
    expected_im, expected_km, expected_jm = expected_global_shape
    if min(expected_im, expected_km, expected_jm) < 1 or levels > expected_km:
        raise ValueError("expected global dimensions/levels are invalid")
    if expected_km != levels:
        raise ValueError("expected global vertical dimension must equal requested mass levels")
    if expected_call_count is not None and inventory.call_count != expected_call_count:
        raise ValueError(f"expected {expected_call_count} CALL headers, found {inventory.call_count}")
    target_coordinates = set(targets.values())
    if len(target_coordinates) != len(targets):
        raise ValueError("targets must use unique native (i,j) coordinate pairs")
    unexpected_values = sorted(
        { (record.i, record.j) for record in inventory.values.values() if (record.i, record.j) not in target_coordinates }
    )
    if unexpected_values:
        raise ValueError(f"trace contains values outside the requested target columns: {unexpected_values[:8]}")

    kernel_value_call_ids = {
        record.call_id for record in inventory.values.values() if record.owner == "kernel"
    }
    no_kernel_witness = tuple(call_id for call_id in inventory.headers if call_id not in kernel_value_call_ids)
    calls_with_targets = {
        call_id
        for call_id, header in inventory.headers.items()
        if any(header.owns(i, j) for i, j in targets.values())
    }
    calls_with_owned_targets_without_kernel_witness = tuple(
        call_id for call_id in no_kernel_witness if call_id in calls_with_targets
    )
    unowned_targets = tuple(
        name
        for name, (i, j) in targets.items()
        if not any(header.owns(i, j) for header in inventory.headers.values())
    )
    coverage: list[StageCoverage] = []
    all_complete = not unowned_targets
    for call_id, header in inventory.headers.items():
        if header.step != expected_step:
            raise ValueError(f"call {call_id} step {header.step} differs from expected step {expected_step}")
        if header.im != header.ite - header.its + 1 or header.km != header.kte - header.kts + 1 or header.jm != header.jte - header.jts + 1:
            raise ValueError(f"call {call_id} local im/km/jm extents differ from inclusive tile bounds")
        if header.ite > expected_im or header.kte > expected_km or header.jte > expected_jm:
            raise ValueError(f"call {call_id} tile bounds exceed the expected global domain")
        if header.dt_bits != expected_dt_bits:
            raise ValueError(f"call {call_id} dt_hex64 differs from expected dt")
        if header.ncmin_land_bits != expected_land_bits or header.ncmin_sea_bits != expected_sea_bits:
            raise ValueError(f"call {call_id} ncmin hex values differ from expected source/config values")
        for name, (i, j) in targets.items():
            if type(i) is not int or type(j) is not int or not (1 <= i <= expected_im and 1 <= j <= expected_jm):
                raise ValueError(f"target {name!r} ({i},{j}) is outside global dimensions")
            # A call owner only covers targets within its local i/j tile.
            if not header.owns(i, j):
                continue
            local_index = header.global_to_local_batch_index(i, j)
            for owner, stage_map in (("host", HOST_STAGE_FIELDS), ("kernel", KERNEL_STAGE_FIELDS)):
                for stage, fields in stage_map.items():
                    missing = []
                    for k in range(1, levels + 1):
                        for field in fields:
                            key = (call_id, stage, i, k, j, field)
                            if key not in inventory.values:
                                missing.append((k, field))
                    record = StageCoverage(call_id, owner, name, i, j, local_index, stage, fields, tuple(missing))
                    coverage.append(record)
                    if not record.complete:
                        all_complete = False
    result = MomentTraceCoverage(
        call_ids=tuple(inventory.headers),
        call_count=len(inventory.headers),
        values_count=len(inventory.values),
        coverage=tuple(coverage),
        calls_without_kernel_witness=no_kernel_witness,
        calls_with_owned_targets_without_kernel_witness=calls_with_owned_targets_without_kernel_witness,
        unowned_targets=unowned_targets,
        complete=all_complete,
    )
    if require_complete and not result.complete:
        if result.unowned_targets:
            raise ValueError(f"requested targets are not owned by any CALL tile: {result.unowned_targets}")
        missing_items = [item for item in result.coverage if not item.complete]
        first = missing_items[0]
        raise ValueError(
            f"moment trace stage coverage incomplete: call={first.call_id} owner={first.owner} "
            f"target={first.target_name} stage={first.stage} missing={first.missing[:8]}"
        )
    return result
