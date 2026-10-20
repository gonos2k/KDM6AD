"""Strict value-only wire format for prognostic theta_m/QV analysis increments.

Deltas apply to current T_2 (perturbation moist potential temperature, K) and
QVAPOR (kg/kg dry air). They never write H_DIABATIC. Native physics computes
its own subsequent tendencies from the modified state. State/time/geometry
binding belongs to native_analysis_increment and the caller's pinned provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import numpy as np

from harness.native_step_control import _integer, _bounds, _f32_bits, _from_bits, _lines

_MAX_UPDATES = 3_000_000
_PAIR = re.compile(r'[0-9]{10} [0-9]{10}\Z')
_ROW = re.compile(r'THETA_M_QV ([0-9]{10}) ([0-9]{10}) ([0-9]{10})' + r' ([0-9A-F]{8})' * 6 + r'\Z')


def _delta(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.floating)):
        raise ValueError('analysis increment must be a finite real binary32 value')
    with np.errstate(over='ignore', under='ignore'):
        result = np.float32(value)
    if not np.isfinite(result):
        raise ValueError('analysis increment must be finite as binary32')
    if value != 0 and result == 0:
        raise ValueError('nonzero analysis increment underflows binary32')
    return result


@dataclass(frozen=True)
class AnalysisUpdate:
    i: int
    k: int
    j: int
    delta_theta_m: float
    delta_qv: float

    def checked(self, bounds):
        for name in ('i', 'k', 'j'):
            _integer(getattr(self, name), name, minimum=1)
        for value, lower, upper in zip((self.i, self.k, self.j), bounds[::2], bounds[1::2]):
            if not lower <= value <= upper:
                raise ValueError('analysis update is outside the native physical domain')
        dt, dq = _delta(self.delta_theta_m), _delta(self.delta_qv)
        if dt == 0 and dq == 0:
            raise ValueError('empty analysis point must be omitted for exact identity')
        return dt, dq


@dataclass(frozen=True)
class AppliedAnalysis:
    update: AnalysisUpdate
    old_t_bits: int
    old_q_bits: int
    delta_t_bits: int
    delta_q_bits: int
    new_t_bits: int
    new_q_bits: int


def apply_pair(old_t, old_q, delta_t, delta_q):
    """Independent binary32 prediction; zero components preserve original bits."""
    old_t, old_q = np.float32(old_t), np.float32(old_q)
    dt, dq = _delta(delta_t), _delta(delta_q)
    if not np.isfinite(old_t) or not np.isfinite(old_q) or old_q < 0:
        raise ValueError('invalid background thermodynamic state')
    if dt == 0 and dq == 0:
        raise ValueError('empty analysis point must be omitted')
    with np.errstate(over='ignore'):
        new_t = old_t if dt == 0 else np.float32(old_t + dt)
        new_q = old_q if dq == 0 else np.float32(old_q + dq)
        total_theta_m = np.float32(new_t + np.float32(300))
    if not np.isfinite(new_t) or not np.isfinite(new_q) or new_q < 0 or not np.isfinite(total_theta_m) or total_theta_m <= 0:
        raise ValueError('analysis update would produce invalid theta_m or QV')
    if _f32_bits(new_t) == _f32_bits(old_t) and _f32_bits(new_q) == _f32_bits(old_q):
        raise ValueError('analysis pair rounds to no applied change')
    return new_t, new_q


def encode_analysis_command(step: int, updates: Sequence[AnalysisUpdate], bounds) -> bytes:
    _integer(step, 'step')
    bounds, updates = _bounds(bounds), tuple(updates)
    if len(updates) > _MAX_UPDATES:
        raise ValueError('too many analysis points')
    lines = ['KDM6AD_TQ_V1', f'{step:010d} {len(updates):010d}']
    seen = set()
    for update in updates:
        if not isinstance(update, AnalysisUpdate):
            raise TypeError('expected AnalysisUpdate')
        dt, dq = update.checked(bounds)
        point = (update.i, update.k, update.j)
        if point in seen:
            raise ValueError('duplicate analysis point')
        seen.add(point)
        lines.append(f'THETA_M_QV {update.i:010d} {update.k:010d} {update.j:010d} {_f32_bits(dt):08X} {_f32_bits(dq):08X}')
    return ('\n'.join(lines) + '\n').encode('ascii')


def read_analysis_applied(path: str | Path, *, expected_step: int,
                          updates: Sequence[AnalysisUpdate]) -> tuple[AppliedAnalysis, ...]:
    _integer(expected_step, 'expected_step')
    lines, updates = _lines(path), tuple(updates)
    if (len(updates) > _MAX_UPDATES or len(lines) != len(updates) + 2
            or lines[0] != 'KDM6AD_TQ_APPLIED_V1' or not _PAIR.fullmatch(lines[1])):
        raise ValueError('malformed analysis acknowledgement')
    step, count = map(int, lines[1].split(' '))
    if step != expected_step or count != len(updates):
        raise ValueError('analysis acknowledgement step/count differs from request')
    result, seen = [], set()
    for line, update in zip(lines[2:], updates):
        if not isinstance(update, AnalysisUpdate):
            raise TypeError('expected AnalysisUpdate')
        match = _ROW.fullmatch(line)
        if match is None:
            raise ValueError('malformed analysis acknowledgement row')
        point = tuple(map(int, match.groups()[:3]))
        if point != (update.i, update.k, update.j) or point in seen:
            raise ValueError('analysis acknowledgement coordinates differ from request')
        seen.add(point)
        bt, bq, dt, dq, nt, nq = (int(x, 16) for x in match.groups()[3:])
        if dt != _f32_bits(_delta(update.delta_theta_m)) or dq != _f32_bits(_delta(update.delta_qv)):
            raise ValueError('analysis acknowledgement deltas differ from request')
        expected_t, expected_q = apply_pair(_from_bits(bt), _from_bits(bq), _from_bits(dt), _from_bits(dq))
        if nt != _f32_bits(expected_t) or nq != _f32_bits(expected_q):
            raise ValueError('analysis acknowledgement does not match paired binary32 application')
        result.append(AppliedAnalysis(update, bt, bq, dt, dq, nt, nq))
    return tuple(result)
