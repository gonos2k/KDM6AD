"""Structural contract for the bounded S15 upstream confirmation capture.

This module deliberately stays separate from the historically pinned probe.
It validates schedule, coordinates, record identity, and captured branch shape;
it does not claim a complete face-to-RK numerical replay.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


EXPECTED_SCHEDULE = (
    (2, 1, 5, 1, 235, 1, 142),
    (2, 1, 5, 1, 235, 143, 283),
    (2, 2, 5, 1, 235, 1, 142),
    (2, 2, 5, 1, 235, 143, 283),
    (2, 3, 5, 1, 235, 1, 142),
    (2, 3, 5, 1, 235, 143, 283),
)
COORDINATE_PROJECTION_SHA256 = "d3c84443c3f095eedfd435dd7f780350cdc2d4126eb0c550b3cf281585bbfc11"
KEY_FIELDS = ("step", "rk", "owner", "tile_i0", "tile_i1", "tile_j0", "tile_j1", "i", "j", "k")
AXES = ("y", "x", "z")
COMMON_F32 = ("advect_tend", "msfty", "sc_tend", "tendency", "reference", "dt",
              "c1", "c2", "muold", "munew", "rk_store")
_F32 = re.compile(r"[0-9A-Fa-f]{8}\Z")


def _integer(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ContractError(f"{label} must be an exact integer")
    return value


def _word(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _F32.fullmatch(value):
        raise ContractError(f"{label} must be one raw f32 word")
    return value.upper()


def record_key(row: dict[str, Any]) -> tuple[int, ...]:
    return tuple(_integer(row.get(name), name) for name in KEY_FIELDS)


def load_coordinate_projection(path: Path, expected_sha256: str = COORDINATE_PROJECTION_SHA256
                               ) -> list[dict[str, Any]]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ContractError("coordinate projection SHA-256 differs from the independent pin")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "KDM6AD-S15-UPSTREAM-COORDINATE-PROJECTION-v1":
        raise ContractError("coordinate projection schema mismatch")
    if data.get("purpose") != "repeatability_targets_only":
        raise ContractError("coordinate projection is not labeled as repeatability-only")
    slots = data.get("slots")
    if not isinstance(slots, list) or len(slots) != len(EXPECTED_SCHEDULE):
        raise ContractError("coordinate projection must contain six ordered slots")
    for index, (slot, key) in enumerate(zip(slots, EXPECTED_SCHEDULE), start=1):
        if (slot.get("slot") != index or slot.get("schedule_key") != list(key) or
                not isinstance(slot.get("coordinate"), list) or len(slot["coordinate"]) != 3):
            raise ContractError("coordinate projection slot order or schedule key changed")
        coordinate = tuple(_integer(v, "coordinate") for v in slot["coordinate"])
        if not (key[3] <= coordinate[0] <= key[4] and key[5] <= coordinate[1] <= key[6]):
            raise ContractError("coordinate target is outside its owner tile")
    return slots


def _validate_producer(row: dict[str, Any], config: dict[str, Any]) -> None:
    key = record_key(row)
    slot_index = EXPECTED_SCHEDULE.index(key[:7])
    expected_coordinate = config["coordinates"][slot_index]
    if key[7:10] != expected_coordinate:
        raise ContractError("producer coordinate differs from the separately pinned projection")
    faces = row.get("face_fluxes")
    if not isinstance(faces, dict) or set(faces) != set(AXES):
        raise ContractError("producer must retain Y/X/Z face operands")
    for axis in AXES:
        pair = faces[axis]
        if not isinstance(pair, dict) or set(pair) != {"minus", "plus"}:
            raise ContractError(f"producer {axis} flux must retain both adjacent faces")
        for side in ("minus", "plus"):
            _word(pair[side], f"face_fluxes.{axis}.{side}")
    tendencies = row.get("directional_tendencies")
    if not isinstance(tendencies, dict) or set(tendencies) != {f"{a}_tendency" for a in AXES}:
        raise ContractError("producer must retain all three directional tendency terms")
    for name, value in tendencies.items():
        _word(value, f"directional_tendencies.{name}")
    branch = row.get("branch")
    expected_order = ["y", "x", "z"] if key[1] < 3 else ["z", "x", "y"]
    if row.get("tendency_order") != expected_order:
        raise ContractError("producer tendency order differs from source-pinned branch order")
    accumulated = row.get("accumulated_tendency")
    if not isinstance(accumulated, list) or len(accumulated) != 3:
        raise ContractError("producer must record each source-order accumulation result")
    for index, value in enumerate(accumulated):
        _word(value, f"accumulated_tendency[{index}]")
    initial = _word(row.get("initial_tendency"), "initial_tendency")
    replayed = source_order_prefixes(
        initial, {axis: tendencies[f"{axis}_tendency"] for axis in AXES}, expected_order)
    if [word.upper() for word in accumulated] != replayed:
        raise ContractError("producer accumulated tendency does not match source-order binary32 replay")
    dispatch = row.get("dispatch")
    if not isinstance(dispatch, dict) or dispatch.get("rk_order") != config["rk_order"] or \
            dispatch.get("adv_opt") != config["adv_opt"]:
        raise ContractError("producer dispatch record differs from the pinned active config")
    should_be_pd = key[1] == config["rk_order"] and config["adv_opt"] == "POSITIVEDEF"
    expected_branch = "positive_definite" if should_be_pd else "ordinary"
    if branch != expected_branch or dispatch.get("selected_branch") != expected_branch:
        raise ContractError("observed advection branch disagrees with active RK/adv_opt dispatch")
    if should_be_pd:
        for name in ("pd_limiter_active", "pd_scale", "pd_flux_out", "pd_available_state"):
            if name not in row:
                raise ContractError(f"positive-definite producer lacks {name}")
        if type(row["pd_limiter_active"]) is not bool:
            raise ContractError("pd_limiter_active must be boolean")
        for name in ("pd_scale", "pd_flux_out", "pd_available_state"):
            _word(row[name], name)
        for name in ("pd_low_order_fluxes", "pd_high_order_fluxes"):
            _validate_flux_group(row.get(name), name)
    elif any(name in row for name in ("pd_limiter_active", "pd_scale", "pd_flux_out")):
        raise ContractError("ordinary producer record contains positive-definite-only fields")


def _validate_flux_group(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(AXES):
        raise ContractError(f"{label} must retain Y/X/Z face groups")
    for axis in AXES:
        pair = value[axis]
        if not isinstance(pair, dict) or set(pair) != {"minus", "plus"}:
            raise ContractError(f"{label}.{axis} must retain both adjacent faces")
        for side in ("minus", "plus"):
            _word(pair[side], f"{label}.{axis}.{side}")


def _validate_consumer(row: dict[str, Any]) -> None:
    record_key(row)
    missing = [name for name in COMMON_F32 if name not in row]
    if missing:
        raise ContractError(f"RK consumer lacks separate update inputs: {', '.join(missing)}")
    for name in COMMON_F32:
        _word(row[name], name)


def validate_witnesses(producers: list[dict[str, Any]], consumers: list[dict[str, Any]],
                       coordinate_projection_path: Path,
                       run_config: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Join six producer and RK-consumer records by full stage/tile/cell key.

    The returned pairs establish structural identity only. A full source-order
    face-divergence/RK arithmetic replay remains a separate acceptance gate.
    """
    if run_config != {"rk_order": 3, "adv_opt": "POSITIVEDEF"}:
        raise ContractError("confirmation requires the pinned RK3 positive-definite config")
    coordinate_slots = load_coordinate_projection(coordinate_projection_path)
    coordinates = [tuple(slot["coordinate"]) for slot in coordinate_slots]
    if len(coordinates) != len(EXPECTED_SCHEDULE):
        raise ContractError("six pinned coordinate targets are required")
    if len(producers) != 6 or len(consumers) != 6:
        raise ContractError("confirmation requires six producer and six RK-consumer records")
    producer_map: dict[tuple[int, ...], dict[str, Any]] = {}
    consumer_map: dict[tuple[int, ...], dict[str, Any]] = {}
    for row in producers:
        if not isinstance(row, dict):
            raise ContractError("producer record must be an object")
        key = record_key(row)
        if key in producer_map:
            raise ContractError("duplicate producer record identity")
        _validate_producer(row, {**run_config, "coordinates": coordinates})
        producer_map[key] = row
    for row in consumers:
        if not isinstance(row, dict):
            raise ContractError("RK consumer record must be an object")
        key = record_key(row)
        if key in consumer_map:
            raise ContractError("duplicate RK consumer record identity")
        _validate_consumer(row)
        consumer_map[key] = row
    expected_keys = {(*key, *coordinate) for key, coordinate in zip(EXPECTED_SCHEDULE, coordinates)}
    if set(producer_map) != expected_keys or set(consumer_map) != expected_keys:
        raise ContractError("producer or consumer identity differs from the six pinned slots")
    return [(producer_map[key], consumer_map[key]) for key in sorted(expected_keys)]


def source_order_prefixes(initial: str, terms: dict[str, str], order: list[str]) -> list[str]:
    """Return each accumulated binary32 tendency in the supplied source order."""
    if set(terms) != {"y", "x", "z"} or order not in (["y", "x", "z"], ["z", "x", "y"]):
        raise ContractError("source-order accumulation requires all axes and a pinned branch order")
    acc = struct.unpack(">f", bytes.fromhex(_word(initial, "initial")))[0]
    prefixes = []
    for axis in order:
        term = struct.unpack(">f", bytes.fromhex(_word(terms[axis], axis)))[0]
        acc = struct.unpack(">f", struct.pack(">f", acc + term))[0]
        prefixes.append(struct.pack(">f", acc).hex().upper())
    return prefixes


def source_order_accumulate(initial: str, terms: dict[str, str], order: list[str]) -> str:
    """Return the final binary32 sum of already-computed directional terms."""
    return source_order_prefixes(initial, terms, order)[-1]
