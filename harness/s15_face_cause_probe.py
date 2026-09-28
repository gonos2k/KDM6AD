"""Source-pinned S15 face-to-RK record contract and binary32 replay.

This is a preparatory validator, not a native capture probe.  It deliberately
does not modify the historical ``g33_s15_probe.py`` protocol.  The public
module contains hashes, coordinates, and source anchors; private host source
and captured runtime operands stay outside the repository.
"""

from __future__ import annotations

import ctypes
import ctypes.util
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
# Fixed RK3 face receivers for the two projected negative-store donors.  These
# extend the six witness targets only in the explicit neighbors capture mode.
NEIGHBOR_RECEIVERS = (
    (1, (140, 2, 17)),
    (1, (142, 2, 17)),
    (1, (141, 2, 16)),
    (1, (141, 142, 16)),
    (2, (140, 143, 16)),
    (2, (142, 143, 16)),
    (2, (141, 144, 16)),
    (2, (141, 143, 17)),
)
NEIGHBOR_SCHEDULE_BY_TILE = {
    1: (2, 3, 5, 1, 235, 1, 142),
    2: (2, 3, 5, 1, 235, 143, 283),
}
QN_SCHEDULE = (2, 3, 3, 1, 235, 1, 142)
QN_DONOR = (233, 124, 12)
QN_RECEIVERS = (
    (232, 124, 12),
    (233, 123, 12),
    (233, 125, 12),
    (233, 124, 13),
)
QN_XR_SHADOW_INPUT_WORD = "502AB870"
QN_XR_SHADOW_FACTOR_WORD = "3F7FFE97"
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

_LIBM = None
_FMAF = None
try:
    _libm_name = ctypes.util.find_library("m")
    if not _libm_name:
        raise OSError("system libm was not found")
    _LIBM = ctypes.CDLL(_libm_name)
    _FMAF = _LIBM.fmaf
    _FMAF.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float]
    _FMAF.restype = ctypes.c_float
except (AttributeError, OSError) as exc:
    _FMAF_ERROR = str(exc)
else:
    _FMAF_ERROR = ""


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


def _fma32(a: str, b: str, c: str) -> str:
    """Return one correctly rounded binary32 fused multiply-add word."""
    if _FMAF is None:
        raise ProbeError(f"system libm fmaf is unavailable: {_FMAF_ERROR}")
    return value_word(_FMAF(word_value(a), word_value(b), word_value(c)))


def _negate_word(value: str) -> str:
    return f"{int(_word(value, 'word'), 16) ^ 0x80000000:08X}"


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


def _capture_roster(
    public_root: Path, *, neighbors: bool = False, qn: bool = False
) -> dict[tuple[int, ...], dict[str, Any]]:
    """Return one fixed witness roster, optionally with its fixed face receivers."""
    if neighbors and qn:
        raise ProbeError("S15 neighbor and S3 QNCLOUD capture modes are exclusive")
    if qn:
        roster = {(*QN_SCHEDULE, *QN_DONOR): {"tile": 1, "role": "witness"}}
        roster.update(
            {
                (*QN_SCHEDULE, *coordinate): {"tile": 1, "role": "receiver"}
                for coordinate in QN_RECEIVERS
            }
        )
        return roster
    coordinates = _projection(public_root)
    roster: dict[tuple[int, ...], dict[str, Any]] = {}
    for index, (schedule, coordinate) in enumerate(zip(SCHEDULE, coordinates)):
        key = (*schedule, *coordinate)
        roster[key] = {"tile": index % 2 + 1, "role": "witness"}
    if neighbors:
        for tile, coordinate in NEIGHBOR_RECEIVERS:
            schedule = NEIGHBOR_SCHEDULE_BY_TILE[tile]
            key = (*schedule, *coordinate)
            if key in roster:
                raise ProbeError("neighbor receiver duplicates a projected witness")
            roster[key] = {"tile": tile, "role": "receiver"}
    return roster


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


def _validate_pd(
    row: dict[str, Any], *, qn: bool = False, shadow: bool = False
) -> None:
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
    # reversed. A face shared with the adjacent cell may be changed later by
    # that cell's limiter, so the local S15PD post value is final only when this
    # cell owns that face's outflow. S15AX carries the later divergence value.
    shadow_donor = (
        shadow
        and qn
        and row.get("tile_slot") == 1
        and tuple(row.get(name) for name in KEY_FIELDS) == (*QN_SCHEDULE, *QN_DONOR)
    )
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
            if shadow_donor and axis == "x" and side == "plus":
                if expected_face != QN_XR_SHADOW_INPUT_WORD:
                    raise ProbeError(
                        "QNCLOUD xR shadow input differs from its pinned f32 face word"
                    )
                expected_face = _mul(QN_XR_SHADOW_FACTOR_WORD, expected_face)
            if after != expected_face:
                raise ProbeError(
                    f"PD {axis}.{side} local post-limit face disagrees with limiter sign branch"
                )
            if selected and final_axis_faces[side] != after:
                raise ProbeError(
                    f"PD {axis}.{side} target outflow differs from its post-limit value"
                )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def replay_producer(
    row: dict[str, Any],
    config: dict[str, Any],
    *,
    qn: bool = False,
    shadow: bool = False,
) -> dict[str, str]:
    if shadow and not qn:
        raise ProbeError("the xR shadow replay mode requires QNCLOUD")
    key = _identity(row)
    schedule = (QN_SCHEDULE,) if qn else SCHEDULE
    if key[:7] not in schedule:
        raise ProbeError(
            "producer key is outside the independently declared capture schedule"
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
        _validate_pd(row, qn=qn, shadow=shadow)
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
            high = _face_group(faces, f"axes.{axis}.face_fluxes")
            low = _face_group(
                row["pd_low_order_fluxes"][axis], f"pd_low_order_fluxes.{axis}"
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
            # The pinned Fortran O2 build contracts the outer metric multiply
            # with the incoming tendency. Keep the inner spacing product and
            # the left-associated face expression rounded as source does.
            next_acc = _fma32(_negate_word(metric), scaled, acc)
        else:
            dflux = _sub(faces["plus"], faces["minus"])
            coefficient = _mul(metric, spacing)
            delta = _mul(coefficient, dflux)
            # Ordinary advection stores its directional coefficient, then the
            # O2 build contracts coefficient*flux with the incoming tendency.
            next_acc = _fma32(_negate_word(coefficient), dflux, acc)
        # The directional contribution is retained as a separately rounded
        # diagnostic; the source tendency prefix follows the contracted store.
        contribution = _sub("00000000", delta)
        if part.get("flux_difference") != dflux:
            raise ProbeError(f"{axis} face difference does not replay in binary32")
        if part.get("directional_contribution") != contribution:
            raise ProbeError(
                f"{axis} directional contribution does not replay in binary32"
            )
        acc = next_acc
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
    old_mass = _fma32(words["c1"], words["muold"], words["c2"])
    dt_tendency = _mul(words["dt"], tendency)
    numerator = _fma32(old_mass, words["before"], dt_tendency)
    # The pinned O2 build contracts both mass sums and the numerator, while
    # dt*tendency remains a separately rounded binary32 product.
    new_mass = _fma32(words["c1"], words["munew"], words["c2"])
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
    *,
    neighbors: bool = False,
    qn: bool = False,
    shadow: bool = False,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if neighbors and qn:
        raise ProbeError("S15 neighbor and S3 QNCLOUD capture modes are exclusive")
    if shadow and not qn:
        raise ProbeError("the xR shadow capture mode requires QNCLOUD")
    roster = _capture_roster(public_root, neighbors=neighbors, qn=qn)
    witness_keys = {key for key, item in roster.items() if item["role"] == "witness"}
    receiver_keys = {key for key, item in roster.items() if item["role"] == "receiver"}
    expected_witnesses = 1 if qn else 6
    expected_receivers = 4 if qn else (8 if neighbors else 0)
    if (
        len(witness_keys) != expected_witnesses
        or len(receiver_keys) != expected_receivers
    ):
        raise ProbeError("capture roster has the wrong witness or receiver set")
    if witness_keys & receiver_keys:
        raise ProbeError("neighbor receiver identities overlap witness identities")
    expected = witness_keys | receiver_keys
    expected_count = len(expected)
    if len(producers) != expected_count or len(consumers) != expected_count:
        raise ProbeError(
            f"capture must contain exactly {expected_count} producer and consumer records"
        )
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
                scope = (
                    "witness/receiver roster"
                    if qn
                    else "witness/receiver roster"
                    if neighbors
                    else "six projected identities"
                )
                raise ProbeError(f"{label} key differs from the {scope}")
            mapping[key] = row
    if set(producer_map) != expected or set(consumer_map) != expected:
        raise ProbeError("capture is missing a scheduled producer or RK consumer")
    pairs = []
    for key in sorted(expected):
        producer, consumer = producer_map[key], consumer_map[key]
        produced = replay_producer(producer, config, qn=qn, shadow=shadow)
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
