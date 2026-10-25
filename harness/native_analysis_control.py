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


@dataclass(frozen=True)
class PreparedEffectiveAnalysis:
    """Effective float32 T/QV state and sparse native wire deltas."""

    delta_theta_m: np.ndarray
    delta_qv: np.ndarray
    effective_theta_m: np.ndarray
    effective_qv: np.ndarray
    changed_mask: np.ndarray
    updates: tuple[AnalysisUpdate, ...]
    counts: dict[str, int]
    all_noop: bool


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


def prepare_effective_analysis(background_theta_m, background_qv,
                               requested_delta_theta_m, requested_delta_qv,
                               unchanged_mask, *, bounds) -> PreparedEffectiveAnalysis:
    """Cast and apply a full native ``(i,k,j)`` analysis increment in float32.

    Bounds must describe the exact one-based array domain. Nonzero deltas that
    underflow or overflow float32 are rejected. Zero components preserve their
    original bits; wire deltas include only components that change state bits.
    """
    bounds = _bounds(bounds)

    def real_array(value, name, *, dtype=None):
        if np.ma.isMaskedArray(value) and np.ma.getmaskarray(value).any():
            raise ValueError(f"{name} contains masked values")
        array = np.asarray(value)
        if array.dtype.kind != 'f' or (dtype is not None and array.dtype != np.dtype(dtype)):
            raise ValueError(f"{name} must be a real floating-point array")
        if not np.isfinite(array).all():
            raise ValueError(f"{name} must be finite")
        return array

    old_t = real_array(background_theta_m, 'background_theta_m', dtype=np.float32)
    old_q = real_array(background_qv, 'background_qv', dtype=np.float32)
    request_t = real_array(requested_delta_theta_m, 'requested_delta_theta_m')
    request_q = real_array(requested_delta_qv, 'requested_delta_qv')
    shape = (bounds[1] - bounds[0] + 1,
             bounds[3] - bounds[2] + 1,
             bounds[5] - bounds[4] + 1)
    if bounds[0] != 1 or bounds[2] != 1 or bounds[4] != 1:
        raise ValueError('analysis bounds must be the one-based full native array domain')
    if old_t.ndim != 3:
        raise ValueError('background arrays must have three native (i,k,j) dimensions')
    if old_t.shape != shape:
        raise ValueError('bounds must equal the full native array domain shape')
    if old_q.shape != old_t.shape or request_t.shape != old_t.shape or request_q.shape != old_t.shape:
        raise ValueError('background and requested delta arrays must have identical native shape')
    if np.any(old_q < np.float32(0.0)):
        raise ValueError('background_qv must be nonnegative')
    with np.errstate(over='ignore', invalid='ignore'):
        old_total = np.add(old_t, np.float32(300.0), dtype=np.float32)
    if not np.isfinite(old_total).all() or np.any(old_total <= np.float32(0.0)):
        raise ValueError('background theta_m plus 300 K must be positive finite')

    if not isinstance(unchanged_mask, np.ndarray) or unchanged_mask.dtype != np.dtype(bool):
        raise ValueError('unchanged_mask must be a Boolean native-layout array')
    if unchanged_mask.shape != old_t.shape:
        raise ValueError('unchanged_mask must match the native (i,k,j) shape')
    requested_t = request_t != 0.0
    requested_q = request_q != 0.0
    requested_points = requested_t | requested_q
    if not np.array_equal(unchanged_mask, ~requested_points):
        raise ValueError('unchanged_mask must exactly identify zero requested delta pairs')

    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        delta_t = np.asarray(request_t, dtype=np.float32)
        delta_q = np.asarray(request_q, dtype=np.float32)
    overflow = (requested_t & ~np.isfinite(delta_t)) | (requested_q & ~np.isfinite(delta_q))
    if overflow.any():
        raise ValueError(f'requested analysis delta overflows binary32 in {int(overflow.sum())} components')
    underflow = (requested_t & (delta_t == 0.0)) | (requested_q & (delta_q == 0.0))
    if underflow.any():
        raise ValueError(f'requested nonzero analysis delta underflows binary32 in {int(underflow.sum())} components')

    new_t = np.array(old_t, dtype=np.float32, order='C', copy=True)
    new_q = np.array(old_q, dtype=np.float32, order='C', copy=True)
    nonzero_t, nonzero_q = delta_t != 0.0, delta_q != 0.0
    with np.errstate(over='ignore', invalid='ignore'):
        new_t[nonzero_t] = np.add(old_t[nonzero_t], delta_t[nonzero_t], dtype=np.float32)
        new_q[nonzero_q] = np.add(old_q[nonzero_q], delta_q[nonzero_q], dtype=np.float32)
        total_theta = np.add(new_t, np.float32(300.0), dtype=np.float32)
    if (not np.isfinite(new_t).all() or not np.isfinite(new_q).all()
            or not np.isfinite(total_theta).all()):
        raise ValueError('effective analysis state must be finite as binary32')
    if np.any(new_q < np.float32(0.0)):
        raise ValueError('effective analysis qv must be nonnegative')
    if np.any(total_theta <= np.float32(0.0)):
        raise ValueError('effective theta_m plus 300 K must be positive')

    old_t_bits = np.ascontiguousarray(old_t).view(np.uint32)
    old_q_bits = np.ascontiguousarray(old_q).view(np.uint32)
    changed_t = new_t.view(np.uint32) != old_t_bits
    changed_q = new_q.view(np.uint32) != old_q_bits
    changed = changed_t | changed_q
    wire_t = np.zeros(old_t.shape, dtype=np.float32)
    wire_q = np.zeros(old_q.shape, dtype=np.float32)
    wire_t[changed_t] = delta_t[changed_t]
    wire_q[changed_q] = delta_q[changed_q]
    coordinates = np.argwhere(changed)
    updates = tuple(
        AnalysisUpdate(int(i) + 1, int(k) + 1, int(j) + 1,
                       float(wire_t[i, k, j]), float(wire_q[i, k, j]))
        for i, k, j in coordinates
    )
    requested_count, applied_count = int(requested_points.sum()), int(coordinates.shape[0])
    counts = {
        'requested_points': requested_count,
        'noop_points': requested_count - applied_count,
        'applied_points': applied_count,
        'empty_points': int(old_t.size - requested_count),
        'requested_nonzero_components': int(requested_t.sum() + requested_q.sum()),
        'applied_components': int(changed_t.sum() + changed_q.sum()),
        'zero_effect_components': int((requested_t & ~changed_t).sum() + (requested_q & ~changed_q).sum()),
    }
    return PreparedEffectiveAnalysis(wire_t, wire_q, new_t, new_q, changed.copy(),
                                     updates, counts, applied_count == 0)


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
