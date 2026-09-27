"""Source-pinned S15 face-to-RK record contract and binary32 replay.

This is a preparatory validator, not a native capture probe.  It deliberately
does not modify the historical ``g33_s15_probe.py`` protocol.  The public
module contains hashes, coordinates, and source anchors; private host source
and captured runtime operands stay outside the repository.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any


class ProbeError(ValueError):
    """An invalid source tree, event stream, or replay contract."""


SOURCE_PINS = {
    "dyn_em/solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
    "dyn_em/module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
    "dyn_em/module_advect_em.F": "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d",
}
PROJECTION_PATH = Path(
    "harness/evidence/s15_step2_public/s15_upstream_coordinate_projection_2026-09-27.json"
)
PROJECTION_SHA256 = "d3c84443c3f095eedfd435dd7f780350cdc2d4126eb0c550b3cf281585bbfc11"
WITNESS_PATH = Path(
    "harness/evidence/s15_step2_public/s15_native_step2_qib_witnesses_public_2026-09-26.json"
)
WITNESS_SHA256 = "6faed36e9f16354d117a8227fecff3a44d6f33839fb58782547f87b431cbc2aa"
SCHEDULE = (
    (2, 1, 5, 1, 235, 1, 142),
    (2, 1, 5, 1, 235, 143, 283),
    (2, 2, 5, 1, 235, 1, 142),
    (2, 2, 5, 1, 235, 143, 283),
    (2, 3, 5, 1, 235, 1, 142),
    (2, 3, 5, 1, 235, 143, 283),
)
KEY_FIELDS = (
    "step",
    "rk",
    "owner",
    "tile_i0",
    "tile_i1",
    "tile_j0",
    "tile_j1",
    "i",
    "j",
    "k",
)
AXES = ("y", "x", "z")
ORDINARY_ORDER = ("y", "x", "z")
PD_ORDER = ("z", "x", "y")
WORD = re.compile(r"[0-9a-fA-F]{8}\Z")


def _word(value: Any, label: str) -> str:
    if not isinstance(value, str) or not WORD.fullmatch(value):
        raise ProbeError(f"{label} must be an eight-digit raw f32 word")
    return value.upper()


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def word_value(value: str, label: str = "word") -> float:
    number = struct.unpack(">f", bytes.fromhex(_word(value, label)))[0]
    if not math.isfinite(number):
        raise ProbeError(f"{label} must be a finite binary32 value")
    return number


def value_word(value: float) -> str:
    try:
        return struct.pack(">f", f32(value)).hex().upper()
    except (OverflowError, struct.error) as exc:
        raise ProbeError("binary32 replay overflow") from exc


def _add(a: str, b: str) -> str:
    return value_word(word_value(a) + word_value(b))


def _sub(a: str, b: str) -> str:
    return value_word(word_value(a) - word_value(b))


def _mul(a: str, b: str) -> str:
    return value_word(word_value(a) * word_value(b))


def _div(a: str, b: str) -> str:
    denominator = word_value(b)
    if denominator == 0.0:
        raise ProbeError("binary32 replay division by zero")
    return value_word(word_value(a) / denominator)


def _identity(row: dict[str, Any]) -> tuple[int, ...]:
    key = []
    for name in KEY_FIELDS:
        value = row.get(name)
        if type(value) is not int:
            raise ProbeError(f"{name} must be an exact integer")
        key.append(value)
    return tuple(key)


def _projection(root: Path) -> list[tuple[int, int, int]]:
    path = root / PROJECTION_PATH
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != PROJECTION_SHA256
    ):
        raise ProbeError("independent six-coordinate projection hash mismatch")
    witness = root / WITNESS_PATH
    if (
        not witness.is_file()
        or hashlib.sha256(witness.read_bytes()).hexdigest() != WITNESS_SHA256
    ):
        raise ProbeError("step-2 QIB witness source hash mismatch")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "KDM6AD-S15-UPSTREAM-COORDINATE-PROJECTION-v1":
        raise ProbeError("coordinate projection schema mismatch")
    slots = data.get("slots")
    if not isinstance(slots, list) or len(slots) != 6:
        raise ProbeError("coordinate projection must contain six rows")
    coordinates = []
    for slot, scheduled in zip(slots, SCHEDULE):
        if slot.get("schedule_key") != list(scheduled):
            raise ProbeError(
                "coordinate projection schedule differs from the independent source schedule"
            )
        coord = slot.get("coordinate")
        if (
            not isinstance(coord, list)
            or len(coord) != 3
            or any(type(v) is not int for v in coord)
        ):
            raise ProbeError("coordinate target must contain integer i/j/k")
        i, j, k = coord
        if not (
            scheduled[3] <= i <= scheduled[4] and scheduled[5] <= j <= scheduled[6]
        ):
            raise ProbeError("coordinate target falls outside its owner tile")
        coordinates.append((i, j, k))
    return coordinates


def _safe_source_root(source_root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for relative, expected in SOURCE_PINS.items():
        path = source_root / relative
        if not path.is_file():
            raise ProbeError(f"pinned private source is missing: {relative}")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ProbeError(f"private source SHA-256 mismatch: {relative}")
        files[relative] = raw
    return files


def prepare_pinned_source_recipe(
    source_root: Path, shadow_root: Path, public_root: Path
) -> dict[str, Any]:
    """Copy pinned source files and emit a data-only recipe, not an overlay.

    Native insertion points are expressed as source path/line/hash anchors,
    avoiding private source excerpts in the public tree.  The source copies
    remain byte-identical; this is not a preprocessor, compile, or instrumentation
    check.  The function never configures or builds the host.
    """
    files = _safe_source_root(source_root)
    coordinates = _projection(public_root)
    if shadow_root.exists():
        raise ProbeError("shadow destination must be new")
    shadow_root.mkdir(parents=True)
    for relative, payload in files.items():
        destination = shadow_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    recipe = {
        "schema": "KDM6AD-S15-FACE-CAUSE-OVERLAY-RECIPE-v1",
        "status": "source-pinned-recipe-only",
        "macro": "KDM6AD_S15_FACE_CAPTURE",
        "source_pins": SOURCE_PINS,
        "projection_sha256": PROJECTION_SHA256,
        "witness_sha256": WITNESS_SHA256,
        "schedule": [list(key) for key in SCHEDULE],
        "coordinates": [list(coord) for coord in coordinates],
        "anchors": [
            {
                "path": "dyn_em/solve_em.F",
                "lines": [2847, 2863],
                "role": "owner5 dispatch/RK handoff",
            },
            {
                "path": "dyn_em/module_em.F",
                "lines": [1265, 1344],
                "role": "ordinary/PD dispatch",
            },
            {
                "path": "dyn_em/module_em.F",
                "lines": [1680, 1724],
                "role": "RK tendency assembly",
            },
            {"path": "dyn_em/module_em.F", "lines": [1750, 1774], "role": "RK store"},
            {
                "path": "dyn_em/module_advect_em.F",
                "lines": [3452, 3649],
                "role": "ordinary Y/X faces and terms",
            },
            {
                "path": "dyn_em/module_advect_em.F",
                "lines": [4230, 4346],
                "role": "ordinary Z faces and term",
            },
            {
                "path": "dyn_em/module_advect_em.F",
                "lines": [7733, 7885],
                "role": "PD low-order limiter and Z/X/Y terms",
            },
        ],
        "macro_off_check": "source copies are byte-identical to all three pinned inputs",
    }
    (shadow_root / "s15_face_cause_recipe.json").write_text(
        json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return recipe


def _face_group(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"minus", "plus"}:
        raise ProbeError(f"{label} must identify both oriented neighboring faces")
    return {side: _word(value[side], f"{label}.{side}") for side in ("minus", "plus")}


def _validate_pd(row: dict[str, Any]) -> None:
    required = (
        "pd_limiter_active",
        "pd_flux_out",
        "pd_available_state",
        "pd_low_order_fluxes",
        "pd_unlimited_high_order_fluxes",
        "pd_high_order_fluxes",
    )
    if any(name not in row for name in required):
        raise ProbeError("RK3 POSITIVEDEF producer lacks captured limiter operands")
    if type(row["pd_limiter_active"]) is not bool:
        raise ProbeError("pd_limiter_active must be boolean")
    for name in ("pd_flux_out", "pd_available_state"):
        _word(row[name], name)
    for name in (
        "pd_low_order_fluxes",
        "pd_unlimited_high_order_fluxes",
        "pd_high_order_fluxes",
    ):
        group = row[name]
        if not isinstance(group, dict) or set(group) != set(AXES):
            raise ProbeError(f"{name} must retain Y/X/Z flux groups")
        for axis in AXES:
            _face_group(group[axis], f"{name}.{axis}")
    # The source predicate is flux_out > available_state.  The captured active
    # flag must report the predicate actually executed at the selected cell.
    expected_active = word_value(row["pd_flux_out"]) > word_value(
        row["pd_available_state"]
    )
    if row["pd_limiter_active"] != expected_active:
        raise ProbeError("PD limiter branch flag disagrees with its captured operands")
    if expected_active:
        if "pd_scale" not in row or "pd_eps" not in row:
            raise ProbeError("active PD limiter lacks scale or epsilon operands")
        scale = _word(row["pd_scale"], "pd_scale")
        epsilon = _word(row["pd_eps"], "pd_eps")
        denominator = _add(row["pd_flux_out"], epsilon)
        ratio = _div(row["pd_available_state"], denominator)
        expected_scale = ratio if word_value(ratio) > 0.0 else "00000000"
        if scale != expected_scale:
            raise ProbeError(
                "PD scale does not replay from available state, outflow, and epsilon"
            )
    elif "pd_scale" in row or "pd_eps" in row:
        raise ProbeError("inactive PD limiter must omit unexecuted scale operands")

    axes = row.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(AXES):
        raise ProbeError("PD producer must include all final directional face pairs")
    # Source-pinned module_advect_em.F applies scale only to faces selected by
    # the outflow signs (lines 7764-7775); vertical mass-coordinate signs are
    # reversed. `pd_high_order_fluxes` is post-limit and must be the same pair
    # consumed by directional divergence; `pd_unlimited...` is pre-limit.
    for axis in AXES:
        original = row["pd_unlimited_high_order_fluxes"][axis]
        limited = row["pd_high_order_fluxes"][axis]
        final_axis_faces = _face_group(
            axes[axis].get("face_fluxes"), f"axes.{axis}.face_fluxes"
        )
        for side in ("minus", "plus"):
            before = _word(
                original[side], f"pd_unlimited_high_order_fluxes.{axis}.{side}"
            )
            after = _word(limited[side], f"pd_high_order_fluxes.{axis}.{side}")
            if axis == "z":
                selected = (
                    word_value(before) > 0.0
                    if side == "minus"
                    else word_value(before) < 0.0
                )
            else:
                selected = (
                    word_value(before) < 0.0
                    if side == "minus"
                    else word_value(before) > 0.0
                )
            expected_face = (
                _mul(row["pd_scale"], before)
                if expected_active and selected
                else before
            )
            if after != expected_face:
                raise ProbeError(
                    f"PD {axis}.{side} final high-order face disagrees with limiter sign branch"
                )
            if final_axis_faces[side] != after:
                raise ProbeError(
                    f"PD {axis}.{side} divergence face differs from its post-limit value"
                )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def replay_producer(row: dict[str, Any], config: dict[str, Any]) -> dict[str, str]:
    key = _identity(row)
    if key[:7] not in SCHEDULE:
        raise ProbeError(
            "producer key is outside the independently declared six-slot schedule"
        )
    branch = row.get("branch")
    order = PD_ORDER if branch == "positive_definite" else ORDINARY_ORDER
    should_pd = key[1] == config["rk_order"] and config["adv_opt"] == "POSITIVEDEF"
    if config != {"rk_order": 3, "adv_opt": "POSITIVEDEF"}:
        raise ProbeError("probe config must pin RK3 POSITIVEDEF")
    if branch != ("positive_definite" if should_pd else "ordinary"):
        raise ProbeError(
            "observed producer branch does not match executed dispatch configuration"
        )
    dispatch = row.get("dispatch")
    if dispatch != {"rk_order": 3, "adv_opt": "POSITIVEDEF", "selected_branch": branch}:
        raise ProbeError("dispatch record is missing or inconsistent")
    if should_pd:
        _validate_pd(row)
    elif any(name.startswith("pd_") for name in row):
        raise ProbeError("ordinary stage contains positive-definite-only operands")

    if tuple(row.get("tendency_order", ())) != order:
        raise ProbeError("producer tendency order differs from source branch order")
    initial = _word(row.get("initial_tendency"), "initial_tendency")
    axes = row.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(AXES):
        raise ProbeError("producer must contain exactly Y/X/Z face and prefix records")
    acc = initial
    expected_prefixes = []
    for axis in order:
        part = axes[axis]
        if not isinstance(part, dict):
            raise ProbeError(f"axis {axis} must be an object")
        faces = _face_group(part.get("face_fluxes"), f"axes.{axis}.face_fluxes")
        metric = _word(part.get("metric_factor"), f"axes.{axis}.metric_factor")
        spacing = _word(part.get("inverse_spacing"), f"axes.{axis}.inverse_spacing")
        if should_pd:
            high = _face_group(
                row["pd_high_order_fluxes"][axis], f"pd_high_order_fluxes.{axis}"
            )
            low = _face_group(
                row["pd_low_order_fluxes"][axis], f"pd_low_order_fluxes.{axis}"
            )
            if faces != high:
                raise ProbeError(
                    f"{axis} final high-order face operands differ from PD face record"
                )
            # Fortran evaluates `high_plus - high_minus + low_plus - low_minus`
            # left-to-right in the source expression. Preserve each f32
            # rounding point; grouping the two differences changes bit patterns.
            dflux = _sub(
                _add(_sub(high["plus"], high["minus"]), low["plus"]),
                low["minus"],
            )
            scaled = _mul(spacing, dflux)
            delta = _mul(metric, scaled)
        else:
            dflux = _sub(faces["plus"], faces["minus"])
            coefficient = _mul(metric, spacing)
            delta = _mul(coefficient, dflux)
        # PD retains the source's left-associated high/low face expression;
        # ordinary advection has one flux difference and a precomputed
        # directional coefficient.
        contribution = _sub("00000000", delta)
        if part.get("flux_difference") != dflux:
            raise ProbeError(f"{axis} face difference does not replay in binary32")
        if part.get("directional_contribution") != contribution:
            raise ProbeError(
                f"{axis} directional contribution does not replay in binary32"
            )
        acc = _add(acc, contribution)
        prefix = _word(part.get("tendency_prefix"), f"axes.{axis}.tendency_prefix")
        if prefix != acc:
            raise ProbeError(f"{axis} source-order tendency prefix does not replay")
        expected_prefixes.append(prefix)
    if list(row.get("prefixes", [])) != expected_prefixes:
        raise ProbeError(
            "producer prefix list is missing, duplicated, or out of source order"
        )
    if _word(row.get("advect_tend"), "advect_tend") != acc:
        raise ProbeError("aggregate advect_tend differs from final producer prefix")
    return {"advect_tend": acc}


def replay_consumer(row: dict[str, Any]) -> dict[str, str]:
    _identity(row)
    names = (
        "advect_tend",
        "msfty",
        "sc_tend",
        "tendency",
        "before",
        "after",
        "dt",
        "c1",
        "c2",
        "muold",
        "munew",
    )
    words = {name: _word(row.get(name), name) for name in names}
    scaled = _mul(words["advect_tend"], words["msfty"])
    tendency = _add(scaled, words["sc_tend"])
    if tendency != words["tendency"]:
        raise ProbeError(
            "RK consumer tendency does not replay advect_tend*msfty + sc_tend"
        )
    old_mass = _add(_mul(words["c1"], words["muold"]), words["c2"])
    new_mass = _add(_mul(words["c1"], words["munew"]), words["c2"])
    numerator = _add(_mul(old_mass, words["before"]), _mul(words["dt"], tendency))
    if word_value(new_mass) == 0.0:
        raise ProbeError("RK consumer new mass denominator is zero")
    stored = value_word(word_value(numerator) / word_value(new_mass))
    if stored != words["after"]:
        raise ProbeError("RK consumer store does not replay from the captured operands")
    return {"tendency": tendency, "after": stored}


def validate_capture(
    producers: list[dict[str, Any]],
    consumers: list[dict[str, Any]],
    public_root: Path,
    config: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    coordinates = _projection(public_root)
    if len(producers) != 6 or len(consumers) != 6:
        raise ProbeError(
            "capture must contain exactly six producer and six consumer records"
        )
    expected = {
        (*schedule, *coordinate) for schedule, coordinate in zip(SCHEDULE, coordinates)
    }
    producer_map: dict[tuple[int, ...], dict[str, Any]] = {}
    consumer_map: dict[tuple[int, ...], dict[str, Any]] = {}
    for rows, mapping, label in (
        (producers, producer_map, "producer"),
        (consumers, consumer_map, "consumer"),
    ):
        for row in rows:
            if not isinstance(row, dict):
                raise ProbeError(f"{label} record must be an object")
            key = _identity(row)
            if key in mapping:
                raise ProbeError(f"duplicate {label} identity")
            if key not in expected:
                raise ProbeError(
                    f"{label} key differs from the six projected identities"
                )
            mapping[key] = row
    if set(producer_map) != expected or set(consumer_map) != expected:
        raise ProbeError("capture is missing a scheduled producer or RK consumer")
    pairs = []
    for key in sorted(expected):
        producer, consumer = producer_map[key], consumer_map[key]
        produced = replay_producer(producer, config)
        if _identity(producer) != _identity(consumer):
            raise ProbeError("producer/consumer identity join failed")
        if (
            _word(consumer.get("advect_tend"), "consumer.advect_tend")
            != produced["advect_tend"]
        ):
            raise ProbeError("producer aggregate and RK consumer advect_tend differ")
        replay_consumer(consumer)
        pairs.append((producer, consumer))
    return pairs


def macro_off_equal(source_root: Path, shadow_root: Path) -> bool:
    """Return true only when every prepared source byte matches its pinned input."""
    for relative, expected in SOURCE_PINS.items():
        original, copy = source_root / relative, shadow_root / relative
        if (
            hashlib.sha256(original.read_bytes()).hexdigest() != expected
            or not copy.is_file()
        ):
            raise ProbeError(
                "macro-off equality check lacks pinned source or overlay copy"
            )
        if original.read_bytes() != copy.read_bytes():
            raise ProbeError(f"macro-off source copy differs: {relative}")
    return True


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a strict JSONL capture containing exactly producer/consumer tags."""
    producers: list[dict[str, Any]] = []
    consumers: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            raise ProbeError(f"blank event line {line_no}")
        try:
            row = json.loads(line, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"malformed JSON event at line {line_no}") from exc
        if not isinstance(row, dict) or row.get("tag") not in {"S15FACE", "S15RK"}:
            raise ProbeError(f"unknown S15 face-cause event at line {line_no}")
        if row["tag"] == "S15FACE":
            producers.append({key: value for key, value in row.items() if key != "tag"})
        else:
            consumers.append({key: value for key, value in row.items() if key != "tag"})
    if len(producers) != 6 or len(consumers) != 6:
        raise ProbeError("JSONL must contain exactly six S15FACE and six S15RK rows")
    return producers, consumers
