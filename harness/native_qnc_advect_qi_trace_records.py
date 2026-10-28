"""Typed readers for the opt-in RK2/RK3 QNC and moist-writer traces."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

import numpy as np

from harness.analyze_upstream_nc_trace import GENERIC_FIELDS, PD_FIELDS
from harness.native_qnc_representative_trace_overlay import TARGETS_IJK
from harness.native_qnc_representative_trace_records import MOMENTS, STAGES as BASE_STAGES


PRODUCER_MAGIC = "# KDM6AD_QNC_PRODUCER_TRACE_V1"
WRITER_MAGIC = "# KDM6AD_QI_WRITER_MOMENTS_V1"
PRODUCER_HEADER = "# VAL time_step_s rk_step stage i k j field dtype raw_hex"
WRITER_HEADER = "# VAL\tstep\trk_step\tstage\ti\tk\tj\tfield\tdtype\traw_hex"
QNC_IKJ = (113, 12, 70)
QI_IKJ = (1, 33, 168)
QC_IKJ = (155, 15, 120)
STAR_IKJ = ((113, 12, 70), (112, 12, 70), (114, 12, 70),
            (113, 12, 69), (113, 12, 71), (113, 11, 70), (113, 13, 70))
FACES = ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP",
         "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
         "FZ_LOW_BOTTOM", "FZ_LOW_TOP")
QI_FIELDS = MOMENTS + ("MOIST_OLD", "MOIST_TEND", "ADVECT_TEND", "H_TENDENCY",
                       "Z_TENDENCY", "MU_OLD", "MU_NEW", "MU_BASE", "C1H", "C2H",
                       "MSFTY", "DT_RK", "SPECIFIED", "HAVE_BCS_MOIST")
QI_STAGES = ("QI_TEND_BEFORE", "QI_TEND_AFTER", "QI_RK_BEFORE", "QI_RK_AFTER",
             "QI_BDY_AFTER")
QC_STAGES = ("QC_TEND_BEFORE", "QC_TEND_AFTER", "QC_RK_BEFORE", "QC_RK_AFTER",
             "QC_BDY_AFTER")
_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_HEX32 = re.compile(r"[0-9A-F]{8}\Z")
_BOOL = re.compile(r"(?:00|01)\Z")
Key = tuple[int, str, int, int, int, str]


@dataclass(frozen=True)
class NativeValueTrace:
    values: dict[Key, int | bool]
    sha256: str
    byte_count: int

    def bits(self, rk: int, stage: str, i: int, k: int, j: int, field: str) -> int | bool:
        return self.values[(rk, stage, i, k, j, field)]

    def word(self, rk: int, stage: str, i: int, k: int, j: int, field: str) -> str:
        bits = self.bits(rk, stage, i, k, j, field)
        return ("01" if bits else "00") if type(bits) is bool else f"{bits:08X}"

    def f32(self, rk: int, stage: str, i: int, k: int, j: int, field: str) -> np.float32:
        bits = self.bits(rk, stage, i, k, j, field)
        if type(bits) is not int:
            raise TypeError(f"{stage}/{field} is not f32")
        return np.asarray([bits], dtype=np.uint32).view(np.float32)[0]


def _parse(path: str | Path, magic: str, header: str) -> NativeValueTrace:
    raw = Path(path).read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("native trace must be ASCII") from exc
    if lines[:2] != [magic, header]:
        raise ValueError("native trace magic/header differs")
    values: dict[Key, int | bool] = {}
    for line_number, line in enumerate(lines[2:], start=3):
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError(f"line {line_number}: expected VAL record")
        _, step_s, rk_s, stage, i_s, k_s, j_s, field, dtype, word = parts
        if any(not _UINT.fullmatch(token) for token in (step_s, rk_s, i_s, k_s, j_s)):
            raise ValueError(f"line {line_number}: noncanonical integer coordinate")
        step, rk, i, k, j = map(int, (step_s, rk_s, i_s, k_s, j_s))
        if (magic == PRODUCER_MAGIC and step != 20) or (magic == WRITER_MAGIC and step != 3):
            raise ValueError(f"line {line_number}: wrong model step or dt")
        if dtype == "bool":
            if not _BOOL.fullmatch(word):
                raise ValueError(f"line {line_number}: noncanonical bool word")
            bits: int | bool = word == "01"
        elif dtype == "f32":
            if not _HEX32.fullmatch(word):
                raise ValueError(f"line {line_number}: noncanonical f32 word")
            bits = int(word, 16)
            if not np.isfinite(np.asarray([bits], dtype=np.uint32).view(np.float32)[0]):
                raise ValueError(f"line {line_number}: nonfinite f32")
        else:
            raise ValueError(f"line {line_number}: unsupported dtype")
        key = (rk, stage, i, k, j, field)
        if key in values:
            raise ValueError(f"line {line_number}: duplicate native trace value")
        values[key] = bits
    if not values:
        raise ValueError("native trace has no values")
    return NativeValueTrace(values, hashlib.sha256(raw).hexdigest(), len(raw))


def read_qnc_producer_trace(path: str | Path) -> NativeValueTrace:
    trace = _parse(path, PRODUCER_MAGIC, PRODUCER_HEADER)
    expected: dict[Key, type] = {}

    def add(rk: int, stage: str, coord: tuple[int, int, int], fields: tuple[str, ...]) -> None:
        for field in fields:
            expected[(rk, stage, *coord, field)] = bool if field == "LIMIT_HIT" else int

    add(2, "RK2_START", QNC_IKJ, ("TENDENCY",))
    for axis, metric in (("Y", "MRDY"), ("X", "MRDX"), ("Z", "RDZW")):
        add(2, f"RK2_AFTER_{axis}", QNC_IKJ,
            ("TENDENCY", f"F_{axis}_LOWER", f"F_{axis}_UPPER", metric))
    add(3, "RK3_PD_PRE_LIMIT", QNC_IKJ, ("TENDENCY", "PH_LOW", "FLUX_OUT") + FACES)
    for coord in STAR_IKJ:
        add(3, "RK3_PD_LIMIT_CELL", coord, ("PH_LOW", "FLUX_OUT", "SCALE", "LIMIT_HIT"))
    add(3, "RK3_PD_POST_LIMIT_FACES", QNC_IKJ,
        FACES + ("MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "DT_STEP"))
    for axis in ("Z", "X", "Y"):
        add(3, f"RK3_AFTER_{axis}", QNC_IKJ, ("TENDENCY",))
    if trace.values.keys() != expected.keys() or any(type(trace.values[key]) is not dtype
                                                     for key, dtype in expected.items()):
        raise ValueError("QNC producer trace field/stage/target inventory differs")
    return trace


def read_qi_writer_trace(path: str | Path) -> NativeValueTrace:
    trace = _parse(path, WRITER_MAGIC, WRITER_HEADER)
    expected: dict[Key, type] = {}
    for stage, steps in BASE_STAGES.items():
        fields = (MOMENTS + PD_FIELDS[1:] if stage.startswith("RKSCALAR_PD_") else
                  MOMENTS + GENERIC_FIELDS[1:] if stage.startswith("RKSCALAR_") else MOMENTS)
        for rk in steps:
            for i, j, k in TARGETS_IJK:
                for field in fields:
                    expected[(rk, stage, i, k, j, field)] = bool if field == "TENDEC" else int
    for stage in QI_STAGES:
        for field in QI_FIELDS:
            expected[(3, stage, *QI_IKJ, field)] = (
                bool if field in ("SPECIFIED", "HAVE_BCS_MOIST") else int)
    for stage in QC_STAGES:
        for field in MOMENTS:
            expected[(1, stage, *QC_IKJ, field)] = int
    if trace.values.keys() != expected.keys() or any(type(trace.values[key]) is not dtype
                                                     for key, dtype in expected.items()):
        raise ValueError("QI writer trace field/stage/target inventory differs")
    return trace
