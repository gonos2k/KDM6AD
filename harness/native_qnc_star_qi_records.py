"""Strict raw-bit readers for the seven-cell RK3 and QI donor probes."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

import numpy as np

from harness.analyze_upstream_nc_trace import GENERIC_FIELDS, PD_FIELDS
from harness.native_qnc_advect_qi_trace_records import (
    QC_IKJ,
    QC_STAGES,
    QI_FIELDS,
    QI_IKJ,
    QI_STAGES,
    NativeValueTrace,
)
from harness.native_qnc_representative_trace_records import MOMENTS, STAGES as BASE_STAGES


STAR_MAGIC = "# KDM6AD_QNC_STAR_TRACE_V1"
WRITER_MAGIC = "# KDM6AD_QNC_STAR_QI_MOMENTS_V1"
STAR_HEADERS = (STAR_MAGIC, "# CALL id rk model_step_arg time_step_s dt_bits owned",
                "# META id field integer_value", "# VAL id stage i k j field dtype raw_hex")
WRITER_HEADER = "# VAL\tstep\trk_step\tstage\ti\tk\tj\tfield\tdtype\traw_hex"
STAR_IKJ = ((113, 12, 70), (112, 12, 70), (114, 12, 70),
            (113, 12, 69), (113, 12, 71), (113, 11, 70), (113, 13, 70))
WRITER_IJK = ((153, 111, 4), (113, 70, 12), (155, 120, 15), (1, 168, 33),
              (112, 70, 12), (114, 70, 12), (113, 69, 12), (113, 71, 12),
              (113, 70, 11), (113, 70, 13))
FACES = ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP",
         "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
         "FZ_LOW_BOTTOM", "FZ_LOW_TOP")
POST_FIELDS = FACES + ("MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "TENDENCY")
AXES = ("RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y")
META_FIELDS = ("ITS", "ITE", "JTS", "JTE", "KTS", "KTE", "KTF", "IDS", "IDE",
               "JDS", "JDE", "IMS", "IME", "JMS", "JME")
DONOR_F32 = ("DONOR_QI", "X_WIND")
DONOR_I32 = ("DONOR_I", "DONOR_J", "SPEC_ZONE", "IDS", "IDE", "JDS", "JDE",
             "TILE_ITS", "TILE_ITE", "TILE_JTS", "TILE_JTE")
DONOR_BOOL = ("PERIODIC_X", "X_START_ELIGIBLE", "X_WIND_NEGATIVE")
_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SIGNED = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_HEX32 = re.compile(r"[0-9A-F]{8}\Z")


def _f32(bits: int) -> np.float32:
    return np.asarray([bits], dtype=np.uint32).view(np.float32)[0]


def _integer(value: str, label: str) -> int:
    if not _SIGNED.fullmatch(value):
        raise ValueError(f"{label} must be a canonical integer")
    return int(value)


def read_qnc_star_trace(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("QNC star trace must be ASCII") from exc
    if tuple(lines[:4]) != STAR_HEADERS:
        raise ValueError("QNC star trace version/header differs")
    calls: dict[int, dict] = {}
    records: dict[tuple[int, str, int, int, int, str], int] = {}
    order = []
    for line in lines[4:]:
        parts = line.split()
        if not parts:
            raise ValueError("blank QNC star trace line")
        if parts[0] == "CALL" and len(parts) == 7:
            _, id_s, rk, step_arg, seconds, dt_hex, owned = parts
            call = _integer(id_s, "call id")
            if call != len(calls) + 1 or call in calls:
                raise ValueError("QNC star call ids are not unique and sequential")
            if (rk, step_arg, seconds, dt_hex) != ("3", "20", "20", "41A00000") or owned not in ("0", "1"):
                raise ValueError("QNC star call metadata differs from the one-step RK3 case")
            calls[call] = {"rk_step": 3, "dt_bits_hex": dt_hex,
                           "owns_star": owned == "1", "meta": {}}
        elif parts[0] == "META" and len(parts) == 4:
            _, id_s, field, value_s = parts
            call = _integer(id_s, "metadata call id")
            if call not in calls or field not in META_FIELDS or field in calls[call]["meta"]:
                raise ValueError("unexpected or repeated QNC star call metadata")
            calls[call]["meta"][field] = _integer(value_s, field)
        elif parts[0] == "VAL" and len(parts) == 9:
            _, id_s, stage, i_s, k_s, j_s, field, dtype, word = parts
            call = _integer(id_s, "value call id")
            i, k, j = (_integer(value, label) for value, label in
                       ((i_s, "i"), (k_s, "k"), (j_s, "j")))
            allowed = POST_FIELDS if stage == "RK3_POST" else ("TENDENCY",) if stage in AXES else ()
            if (call not in calls or not calls[call]["owns_star"] or
                    (i, k, j) not in STAR_IKJ or field not in allowed or dtype != "f32" or
                    not _HEX32.fullmatch(word)):
                raise ValueError("unexpected QNC star value row")
            bits = int(word, 16)
            if not np.isfinite(_f32(bits)):
                raise ValueError("nonfinite QNC star value")
            key = (call, stage, i, k, j, field)
            if key in records:
                raise ValueError("duplicate QNC star value")
            records[key] = bits
            if not order or order[-1] != (call, stage):
                order.append((call, stage))
        else:
            raise ValueError("unrecognized QNC star trace row")
    if len(calls) != 2 or sum(row["owns_star"] for row in calls.values()) != 1:
        raise ValueError("expected two calls and exactly one complete star owner")
    for row in calls.values():
        meta = row["meta"]
        if set(meta) != set(META_FIELDS) or (meta["IDS"], meta["IDE"], meta["JDS"], meta["JDE"]) != (1, 235, 1, 283):
            raise ValueError("QNC star domain/tile metadata differs")
        inside = (112 >= meta["ITS"] and 114 <= min(meta["ITE"], meta["IDE"] - 1)
                  and 69 >= meta["JTS"] and 71 <= min(meta["JTE"], meta["JDE"] - 1)
                  and 11 >= meta["KTS"] and 13 <= meta["KTF"] and 14 <= meta["KTE"])
        if row["owns_star"] != inside:
            raise ValueError("QNC star owner does not match recorded tile/vertical bounds")
    owner = next(call for call, row in calls.items() if row["owns_star"])
    expected = {(owner, "RK3_POST", *coord, field) for coord in STAR_IKJ for field in POST_FIELDS}
    expected.update((owner, stage, *coord, "TENDENCY") for stage in AXES for coord in STAR_IKJ)
    if set(records) != expected or order != [(owner, stage) for stage in ("RK3_POST", *AXES)]:
        raise ValueError("QNC star stage/field inventory or order differs")
    return {"calls": calls, "owner_call_id": owner, "records": records,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "typed_records": len(records)}


def read_star_qi_writer_trace(path: str | Path) -> NativeValueTrace:
    raw = Path(path).read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("QNC-star/QI writer trace must be ASCII") from exc
    if lines[:2] != [WRITER_MAGIC, WRITER_HEADER]:
        raise ValueError("QNC-star/QI writer trace version/header differs")
    values: dict[tuple[int, str, int, int, int, str], int | bool] = {}
    dtypes = {}
    for line_number, line in enumerate(lines[2:], start=3):
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError(f"line {line_number}: expected writer VAL record")
        _, step_s, rk_s, stage, i_s, k_s, j_s, field, dtype, word = parts
        if any(not _UINT.fullmatch(token) for token in (step_s, rk_s, i_s, k_s, j_s)):
            raise ValueError(f"line {line_number}: noncanonical writer coordinate")
        step, rk, i, k, j = map(int, (step_s, rk_s, i_s, k_s, j_s))
        if step != 3:
            raise ValueError(f"line {line_number}: wrong model step")
        if dtype == "bool":
            if word not in ("00", "01"):
                raise ValueError(f"line {line_number}: noncanonical bool")
            bits: int | bool = word == "01"
        elif dtype in ("f32", "i32"):
            if not _HEX32.fullmatch(word):
                raise ValueError(f"line {line_number}: noncanonical {dtype} word")
            bits = int(word, 16)
            if dtype == "f32" and not np.isfinite(_f32(bits)):
                raise ValueError(f"line {line_number}: nonfinite f32")
        else:
            raise ValueError(f"line {line_number}: unexpected writer dtype")
        key = (rk, stage, i, k, j, field)
        if key in values:
            raise ValueError(f"line {line_number}: duplicate writer value")
        values[key], dtypes[key] = bits, dtype
    expected: dict[tuple[int, str, int, int, int, str], str] = {}
    for stage, steps in BASE_STAGES.items():
        fields = (MOMENTS + PD_FIELDS[1:] if stage.startswith("RKSCALAR_PD_") else
                  MOMENTS + GENERIC_FIELDS[1:] if stage.startswith("RKSCALAR_") else MOMENTS)
        for rk in steps:
            for i, j, k in WRITER_IJK:
                for field in fields:
                    expected[(rk, stage, i, k, j, field)] = "bool" if field == "TENDEC" else "f32"
    for stage in QI_STAGES:
        for field in QI_FIELDS:
            expected[(3, stage, *QI_IKJ, field)] = (
                "bool" if field in ("SPECIFIED", "HAVE_BCS_MOIST") else "f32")
    for stage in QC_STAGES:
        for field in MOMENTS:
            expected[(1, stage, *QC_IKJ, field)] = "f32"
    for field in MOMENTS + DONOR_F32:
        expected[(3, "QI_BDY_INPUT", *QI_IKJ, field)] = "f32"
    for field in DONOR_I32:
        expected[(3, "QI_BDY_INPUT", *QI_IKJ, field)] = "i32"
    for field in DONOR_BOOL:
        expected[(3, "QI_BDY_INPUT", *QI_IKJ, field)] = "bool"
    if dtypes != expected:
        raise ValueError("QNC-star/QI writer stage/target/type inventory differs")
    return NativeValueTrace(values, hashlib.sha256(raw).hexdigest(), len(raw))
