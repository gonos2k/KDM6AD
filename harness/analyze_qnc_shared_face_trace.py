"""Read the seven-cell QNC RK3 face trace and check its applied source path.

This is an offline binary32 arithmetic and face-identity replay. It does not
certify a domain number budget, particle-number units or executed FMA code.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

import numpy as np

from harness.analyze_upstream_nc_trace import read_upstream_nc_trace
from harness.g33_s15_probe import fma32
from harness.replay_qnc_flux_limiter_trace import read_qnc_flux_trace


MAGIC = "# KDM6AD_QNC_SHARED_TRACE_V1"
HEADERS = (
    MAGIC,
    "# CALL id rk model_step_arg time_step_s dt_bits owned",
    "# META id field integer_value",
    "# VAL id stage i k j field dtype raw_hex",
)
TARGET = (221, 6, 63)  # field order is i,k,j; user-facing i,j,k is 221,63,6
STAR = (TARGET, (220, 6, 63), (222, 6, 63), (221, 6, 62),
        (221, 6, 64), (221, 5, 63), (221, 7, 63))
FACE_FIELDS = (
    "FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP",
    "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
    "FZ_LOW_BOTTOM", "FZ_LOW_TOP",
)
POST_FIELDS = (*FACE_FIELDS, "MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "TENDENCY")
AXES = ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y")
META_FIELDS = ("ITS", "ITE", "JTS", "JTE", "KTS", "KTE", "KTF", "IDS", "IDE",
               "JDS", "JDE", "IMS", "IME", "JMS", "JME")
_HEX = re.compile(r"[0-9A-F]{8}\Z")
_INT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


def _integer(value: str, label: str) -> int:
    if not _INT.fullmatch(value):
        raise ValueError(f"{label} must be a canonical integer")
    return int(value)


def _value(bits: int) -> np.float32:
    return np.asarray([bits], dtype=np.uint32).view(np.float32)[0]


def _bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _f32(value) -> np.float32:
    return np.float32(value)


def _add(a, b) -> np.float32:
    return _f32(_f32(a) + _f32(b))


def _sub(a, b) -> np.float32:
    return _f32(_f32(a) - _f32(b))


def _mul(a, b) -> np.float32:
    return _f32(_f32(a) * _f32(b))


def _fma(a, b, c) -> np.float32:
    return _f32(fma32(float(a), float(b), float(c)))


def _summary(bits: int) -> dict[str, object]:
    return {"bits_hex": f"{bits:08X}", "value": float(_value(bits))}


def read_shared_trace(path: Path) -> dict:
    raw = Path(path).read_bytes()
    lines = raw.decode("ascii").splitlines()
    if tuple(lines[:4]) != HEADERS:
        raise ValueError("shared trace version/header differs")
    calls: dict[int, dict] = {}
    records: dict[tuple[int, str, int, int, int, str], int] = {}
    order: list[tuple[int, str]] = []
    for line in lines[4:]:
        parts = line.split()
        if not parts:
            raise ValueError("blank shared-trace line")
        if parts[0] == "CALL" and len(parts) == 7:
            _, id_text, rk, step_arg, seconds, dt_hex, owned = parts
            call = _integer(id_text, "call id")
            if call in calls or call != len(calls) + 1:
                raise ValueError("shared call identifiers must be unique and sequential")
            if (rk, step_arg, seconds, dt_hex) != ("3", "20", "20", "41A00000"):
                raise ValueError("shared trace is not the pinned RK3 20-second call")
            if owned not in ("0", "1"):
                raise ValueError("shared owner flag must be zero/one")
            calls[call] = {"rk": 3, "source_time_step_arg": 20, "time_step_s": 20,
                           "dt_bits_hex": dt_hex, "owns_star": owned == "1", "meta": {}}
        elif parts[0] == "META" and len(parts) == 4:
            _, id_text, field, value = parts
            call = _integer(id_text, "metadata call id")
            if call not in calls or field not in META_FIELDS or field in calls[call]["meta"]:
                raise ValueError("unexpected/duplicate shared call metadata")
            calls[call]["meta"][field] = _integer(value, field)
        elif parts[0] == "VAL" and len(parts) == 9:
            _, id_text, stage, i_text, k_text, j_text, field, dtype, hex_word = parts
            call = _integer(id_text, "value call id")
            i, k, j = (_integer(value, label) for value, label in
                       ((i_text, "i"), (k_text, "k"), (j_text, "j")))
            expected_fields = POST_FIELDS if stage == "RK3_POST" else ("TENDENCY",) if stage in AXES else ()
            if (call not in calls or not calls[call]["owns_star"] or
                    (i, k, j) not in STAR or field not in expected_fields or dtype != "f32" or
                    not _HEX.fullmatch(hex_word)):
                raise ValueError("unexpected shared value row")
            bits = int(hex_word, 16)
            if not np.isfinite(_value(bits)):
                raise ValueError("nonfinite shared value")
            key = (call, stage, i, k, j, field)
            if key in records:
                raise ValueError("duplicate shared value")
            records[key] = bits
            if not order or order[-1] != (call, stage):
                order.append((call, stage))
        else:
            raise ValueError("unrecognized shared-trace row")
    if len(calls) != 2 or sum(row["owns_star"] for row in calls.values()) != 1:
        raise ValueError("expected two tiles and one seven-cell owner")
    for call, row in calls.items():
        meta = row["meta"]
        if set(meta) != set(META_FIELDS) or (meta["IDS"], meta["IDE"], meta["JDS"], meta["JDE"]) != (1, 235, 1, 283):
            raise ValueError("missing/wrong native tile/domain metadata")
        inside = (220 >= meta["ITS"] and 222 <= min(meta["ITE"], meta["IDE"] - 1)
                  and 62 >= meta["JTS"] and 64 <= min(meta["JTE"], meta["JDE"] - 1)
                  and 5 >= meta["KTS"] and 7 <= meta["KTF"])
        if row["owns_star"] != inside:
            raise ValueError("seven-cell tile ownership differs from recorded bounds")
    owner = next(call for call, row in calls.items() if row["owns_star"])
    expected = {(owner, "RK3_POST", *coord, field) for coord in STAR for field in POST_FIELDS}
    expected.update((owner, stage, *coord, "TENDENCY") for stage in AXES for coord in STAR)
    if set(records) != expected or order != [(owner, stage) for stage in ("RK3_POST", *AXES)]:
        raise ValueError("shared seven-cell stages/fields are incomplete or out of order")
    return {"calls": calls, "owner_call_id": owner, "records": records,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "row_count": len(records)}


_SHARED = (
    ("x_west", (220, 6, 63), "FX_WEST", "FX_EAST", "FX_LOW_WEST", "FX_LOW_EAST"),
    ("x_east", (222, 6, 63), "FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST"),
    ("y_south", (221, 6, 62), "FY_SOUTH", "FY_NORTH", "FY_LOW_SOUTH", "FY_LOW_NORTH"),
    ("y_north", (221, 6, 64), "FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH"),
    ("z_bottom", (221, 5, 63), "FZ_BOTTOM", "FZ_TOP", "FZ_LOW_BOTTOM", "FZ_LOW_TOP"),
    ("z_top", (221, 7, 63), "FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM"),
)


def analyze_shared_trace(shared: dict, *, flux_path: Path, upstream_path: Path, run_id: str) -> dict:
    records = shared["records"]
    owner = shared["owner_call_id"]

    def bits(stage: str, coord: tuple[int, int, int], field: str) -> int:
        return records[(owner, stage, *coord, field)]

    def value(stage: str, coord: tuple[int, int, int], field: str) -> np.float32:
        return _value(bits(stage, coord, field))

    flux = read_qnc_flux_trace(flux_path).select_qnc_scalar_group()
    upstream = read_upstream_nc_trace(upstream_path)
    joined_target = {}
    for field in (*POST_FIELDS[:-1],):
        if field == "MSFTY":
            continue  # the PR457 V2 target trace did not record this metric
        prior = flux.at(3, "RK3_PD_POST_LIMIT_FACES", field)
        joined_target[field] = bits("RK3_POST", TARGET, field) == prior.bits
    for stage in AXES:
        joined_target[stage] = bits(stage, TARGET, "TENDENCY") == flux.at(3, stage, "TENDENCY").bits
    joined_target["pre_divergence_TENDENCY"] = (
        bits("RK3_POST", TARGET, "TENDENCY") ==
        flux.at(3, "RK3_PD_PRE_LIMIT", "TENDENCY").bits
    )
    joined_target["dt_PR457_V2"] = (
        shared["calls"][owner]["dt_bits_hex"] ==
        flux.at(3, "RK3_PD_POST_LIMIT_FACES", "DT_STEP").raw_hex
    )
    joined_target["dt_upstream"] = (
        shared["calls"][owner]["dt_bits_hex"] ==
        upstream.at((221, 63, 6), 3, "RKSCALAR_PD_AFTER", "DT_RK").raw_hex
    )
    final = upstream.at((221, 63, 6), 3, "RKSCALAR_BEFORE", "ADVECT_TEND")
    joined_target["upstream_ADVECT_TEND"] = bits(AXES[-1], TARGET, "TENDENCY") == final.bits
    final_qnc = upstream.at((221, 63, 6), 3, "RKSCALAR_AFTER", "QNC")
    faces = {}
    for name, neighbor, target_face, neighbor_face, target_low, neighbor_low in _SHARED:
        correction = bits("RK3_POST", TARGET, target_face)
        low = bits("RK3_POST", TARGET, target_low)
        faces[name] = {
            "target_ikj": list(TARGET), "neighbor_ikj": list(neighbor),
            "correction": _summary(correction), "low_order": _summary(low),
            "neighbor_correction_bits_hex": f"{bits('RK3_POST', neighbor, neighbor_face):08X}",
            "neighbor_low_order_bits_hex": f"{bits('RK3_POST', neighbor, neighbor_low):08X}",
            "correction_bitwise_shared": correction == bits("RK3_POST", neighbor, neighbor_face),
            "low_order_bitwise_shared": low == bits("RK3_POST", neighbor, neighbor_low),
        }
    tendency = {}
    for coord in STAR:
        before = value("RK3_POST", coord, "TENDENCY")
        axes = []
        for axis, stage, upper, lower, low_upper, low_lower, metric in (
            ("Z", "RK3_AFTER_Z", "FZ_TOP", "FZ_BOTTOM", "FZ_LOW_TOP", "FZ_LOW_BOTTOM", "RDZW"),
            ("X", "RK3_AFTER_X", "FX_EAST", "FX_WEST", "FX_LOW_EAST", "FX_LOW_WEST", "RDX"),
            ("Y", "RK3_AFTER_Y", "FY_NORTH", "FY_SOUTH", "FY_LOW_NORTH", "FY_LOW_SOUTH", "RDY"),
        ):
            delta = _sub(_add(_sub(value("RK3_POST", coord, upper), value("RK3_POST", coord, lower)),
                              value("RK3_POST", coord, low_upper)), value("RK3_POST", coord, low_lower))
            inner = _mul(value("RK3_POST", coord, metric), delta)
            observed = value(stage, coord, "TENDENCY")
            if axis == "Z":
                separate = _sub(before, inner)
                outer_fma = _fma(-value("RK3_POST", coord, metric), delta, before)
            else:
                msftx = value("RK3_POST", coord, "MSFTX")
                separate = _sub(before, _mul(msftx, inner))
                outer_fma = _fma(-msftx, inner, before)
            axes.append({"axis": axis, "observed": _summary(_bits(observed)),
                         "source_grouped_separate": _summary(_bits(separate)),
                         "source_grouped_outer_fma": _summary(_bits(outer_fma)),
                         "separate_match": _bits(separate) == _bits(observed),
                         "outer_fma_match": _bits(outer_fma) == _bits(observed)})
            before = observed
        tendency["i%d_k%d_j%d" % coord] = axes
    replay_ok = (all(joined_target.values())
                 and all(row["correction_bitwise_shared"] and row["low_order_bitwise_shared"] for row in faces.values())
                 and all(axis["separate_match"] or axis["outer_fma_match"]
                         for axes in tendency.values() for axis in axes))
    return {
        "schema": "kdm6.native_qnc_shared_face_replay.v1",
        "run_id": run_id, "native_target_ijk_1based": [221, 63, 6],
        "shared_trace_sha256": shared["sha256"], "shared_trace_rows": shared["row_count"],
        "call_headers": shared["calls"], "owner_call_id": owner,
        "same_run_pr457_target_join": joined_target,
        "target_final_rk3_qnc": _summary(int(final_qnc.bits)),
        "six_internal_faces": faces, "seven_cell_directional_tendency": tendency,
        "all_captured_checks_pass": replay_ok,
        "limits": {
            "perimeter_faces_not_closed": 30,
            "domain_number_conservation_certified": False,
            "physical_number_units_certified": False,
            "executed_fma_instruction_certified": False,
            "model_itimestep_source": "same-run upstream trace and final checkpoint; CALL model_step_arg is the Fortran time_step argument (20 seconds)",
        },
    }
