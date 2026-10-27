"""Strict reader for four native QC/NC/QI/NI stage witnesses.

The V1 stream is value-only. It does not provide a process tendency ledger or
certify raw number units, a derivative, or a full-domain physical budget.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

import numpy as np

from harness.analyze_upstream_nc_trace import GENERIC_FIELDS, PD_FIELDS
from harness.native_qnc_representative_trace_overlay import MAGIC, TARGETS_IJK


HEADER = "# VAL\tstep\trk_step\tstage\ti\tk\tj\tfield\tdtype\traw_hex"
MOMENTS = ("QNC", "QC", "QI", "NI")
STAGES = {
    "RKSCALAR_BEFORE": (1, 2, 3),
    "RKSCALAR_AFTER": (1, 2, 3),
    "RKSCALAR_PD_BEFORE": (3,),
    "RKSCALAR_PD_AFTER": (3,),
    "POST_SCALAR_BDY": (3,),
    "PRE_MICROPHYSICS": (0,),
    "POST_MICROPHYSICS": (0,),
    "POST_FINISH": (0,),
}
_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_HEX32 = re.compile(r"[0-9A-F]{8}\Z")


@dataclass(frozen=True)
class RepresentativeTrace:
    values: dict[tuple[int, str, int, int, int, str], int | bool]
    sha256: str
    byte_count: int

    def bits(self, rk: int, stage: str, i: int, j: int, k: int, field: str) -> int | bool:
        return self.values[(rk, stage, i, k, j, field)]

    def f32(self, rk: int, stage: str, i: int, j: int, k: int, field: str) -> np.float32:
        bits = self.bits(rk, stage, i, j, k, field)
        if type(bits) is not int:
            raise TypeError(f"{field} at {stage} is not f32")
        return np.asarray([bits], dtype=np.uint32).view(np.float32)[0]


def read_representative_trace(path: str | Path) -> RepresentativeTrace:
    raw = Path(path).read_bytes()
    lines = raw.decode("ascii").splitlines()
    if lines[:2] != [MAGIC, HEADER]:
        raise ValueError("representative trace magic/header differs")
    values = {}
    groups: dict[tuple[int, str, int, int, int], set[str]] = {}
    targets = set(TARGETS_IJK)
    for line_no, line in enumerate(lines[2:], start=3):
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError(f"line {line_no}: expected 10-column VAL record")
        _, step_s, rk_s, stage, i_s, k_s, j_s, field, dtype, word = parts
        if any(not _UINT.fullmatch(token) for token in (step_s, rk_s, i_s, k_s, j_s)):
            raise ValueError(f"line {line_no}: noncanonical integer coordinate")
        step, rk, i, k, j = map(int, (step_s, rk_s, i_s, k_s, j_s))
        if step != 3 or stage not in STAGES or rk not in STAGES[stage] or (i, j, k) not in targets:
            raise ValueError(f"line {line_no}: unexpected step/stage/target")
        if stage.startswith("RKSCALAR_PD_"):
            expected = MOMENTS + PD_FIELDS[1:]
        elif stage.startswith("RKSCALAR_"):
            expected = MOMENTS + GENERIC_FIELDS[1:]
        else:
            expected = MOMENTS
        if field not in expected:
            raise ValueError(f"line {line_no}: unexpected {stage}/{field}")
        if field == "TENDEC":
            if dtype != "bool" or word not in ("00", "01"):
                raise ValueError(f"line {line_no}: TENDEC requires canonical bool")
            bits: int | bool = word == "01"
        else:
            if dtype != "f32" or not _HEX32.fullmatch(word):
                raise ValueError(f"line {line_no}: {field} requires canonical f32 word")
            bits = int(word, 16)
            if not np.isfinite(np.asarray([bits], dtype=np.uint32).view(np.float32)[0]):
                raise ValueError(f"line {line_no}: nonfinite f32 value")
        key = (rk, stage, i, k, j, field)
        if key in values:
            raise ValueError(f"line {line_no}: duplicate representative trace value")
        values[key] = bits
        groups.setdefault((rk, stage, i, k, j), set()).add(field)
    if not values:
        raise ValueError("representative trace has no values")
    for rk, stage in ((1, "RKSCALAR_BEFORE"), (1, "RKSCALAR_AFTER"),
                      (2, "RKSCALAR_BEFORE"), (2, "RKSCALAR_AFTER"),
                      (3, "RKSCALAR_PD_BEFORE"), (3, "RKSCALAR_PD_AFTER"),
                      (3, "RKSCALAR_BEFORE"), (3, "RKSCALAR_AFTER"),
                      (3, "POST_SCALAR_BDY"),
                      (0, "PRE_MICROPHYSICS"), (0, "POST_MICROPHYSICS"),
                      (0, "POST_FINISH")):
        if stage.startswith("RKSCALAR_PD_"):
            expected = set(MOMENTS + PD_FIELDS[1:])
        elif stage.startswith("RKSCALAR_"):
            expected = set(MOMENTS + GENERIC_FIELDS[1:])
        else:
            expected = set(MOMENTS)
        for i, j, k in TARGETS_IJK:
            group = (rk, stage, i, k, j)
            if groups.get(group) != expected:
                raise ValueError(f"representative trace field inventory differs at {group}")
    return RepresentativeTrace(values, hashlib.sha256(raw).hexdigest(), len(raw))
