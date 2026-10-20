"""Value-only control of a live native host at completed-timestep boundaries.

A heating control changes the retained H_DIABATIC *rate memory* (K/s in the
audited USE_THETA_M=1 host coordinate), not a
reconstructed temperature. Its actual memory departure is recorded in binary32;
the native RK/dynamics consumes it once and determines the physical state
response. No equality delta_theta=dt*delta_rate, balance convergence, or host
JVP/VJP is implied. Empty updates perform no floating-point operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile
from typing import Sequence

import numpy as np


_STAMP = '%Y-%m-%d_%H:%M:%S'
_I32_MAX = 2**31 - 1
_MAX_UPDATES = 1_000_000
_INTEGER_PAIR = re.compile(r'[0-9]{10} [0-9]{10}\Z')
_BOUNDS = re.compile(r'[0-9]{10}(?: [0-9]{10}){5}\Z')
_ACK_ROW = re.compile(r'H_DIABATIC ([0-9]{10}) ([0-9]{10}) ([0-9]{10}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})\Z')


def _integer(value, name, *, minimum=0):
    if type(value) is not int or not minimum <= value <= _I32_MAX:
        raise ValueError(f'{name} must be an int32 integer >= {minimum}')
    return value


def _bounds(values):
    if len(values) != 6:
        raise ValueError('bounds need i_min/max, k_min/max, j_min/max')
    values = tuple(_integer(x, 'bound', minimum=1) for x in values)
    if any(values[n] > values[n + 1] for n in (0, 2, 4)):
        raise ValueError('bounds are reversed')
    return values


def _f32_bits(value):
    return int(np.asarray([value], np.float32).view(np.uint32)[0])


def _from_bits(value):
    return np.asarray([value], np.uint32).view(np.float32)[0]


@dataclass(frozen=True)
class HeatingUpdate:
    i: int
    k: int
    j: int
    delta: float

    def checked(self, bounds):
        for name in ('i', 'k', 'j'):
            _integer(getattr(self, name), name, minimum=1)
        if isinstance(self.delta, (bool, np.bool_)) or not isinstance(self.delta, (int, float, np.floating)):
            raise ValueError('heating rate delta must be a finite real binary32 value')
        with np.errstate(over='ignore', under='ignore'):
            delta = np.float32(self.delta)
        if not np.isfinite(delta) or delta == 0:
            raise ValueError('nonempty updates require finite nonzero binary32 delta; use no updates for identity')
        for value, lower, upper in zip((self.i, self.k, self.j), bounds[::2], bounds[1::2]):
            if not lower <= value <= upper:
                raise ValueError('heating update is outside the native physical domain')
        return delta


@dataclass(frozen=True)
class StepReady:
    step: int
    domain: int
    time: str
    bounds: tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class AppliedHeating:
    update: HeatingUpdate
    old_bits: int
    delta_bits: int
    new_bits: int


def encode_command(step: int, updates: Sequence[HeatingUpdate], bounds: Sequence[int]) -> bytes:
    _integer(step, 'step')
    bounds = _bounds(bounds)
    updates = tuple(updates)
    if len(updates) > _MAX_UPDATES:
        raise ValueError('too many heating controls')
    lines = ['KDM6AD_STEP_V1', f'{step:010d} {len(updates):010d}']
    seen = set()
    for update in updates:
        if not isinstance(update, HeatingUpdate):
            raise TypeError('expected HeatingUpdate')
        delta = update.checked(bounds)
        point = (update.i, update.k, update.j)
        if point in seen:
            raise ValueError('duplicate heating update point')
        seen.add(point)
        lines.append(f'H_DIABATIC {update.i:010d} {update.k:010d} {update.j:010d} {_f32_bits(delta):08X}')
    return ('\n'.join(lines) + '\n').encode('ascii')


def atomic_write_command(path: str | Path, data: bytes) -> None:
    """Publish only complete packet bytes; never overwrite a consumed command."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    descriptor, name = tempfile.mkstemp(prefix='.command-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if another publisher wins.
        # The staging inode is an owned packet, never model/input data.
        os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _lines(path):
    try:
        data = Path(path).read_bytes()
        if not data.endswith(b'\n') or b'\r' in data or b'\0' in data:
            raise ValueError('packet must be newline-terminated ASCII without CR/NUL')
        return data.decode('ascii').splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f'cannot read complete ASCII packet: {path}') from exc


def read_ready(path: str | Path, *, expected_step: int) -> StepReady:
    _integer(expected_step, 'expected_step')
    rows = _lines(path)
    if len(rows) != 4 or rows[0] != 'KDM6AD_READY_V1' or not _INTEGER_PAIR.fullmatch(rows[1]) or not _BOUNDS.fullmatch(rows[3]):
        raise ValueError('malformed native ready packet')
    step, domain = (_integer(int(x), 'ready integer') for x in rows[1].split(' '))
    if step != expected_step or domain != 1:
        raise ValueError('native ready step/domain differs from expected value')
    stamp = datetime.strptime(rows[2], _STAMP)
    if stamp.strftime(_STAMP) != rows[2]:
        raise ValueError('native ready timestamp must be exact UTC format')
    return StepReady(step, domain, rows[2], _bounds(tuple(map(int, rows[3].split(' ')))))


def read_applied(path: str | Path, *, expected_step: int,
                 updates: Sequence[HeatingUpdate]) -> tuple[AppliedHeating, ...]:
    _integer(expected_step, 'expected_step')
    rows, updates = _lines(path), tuple(updates)
    if len(updates) > _MAX_UPDATES:
        raise ValueError('too many updates')
    if len(rows) != len(updates) + 2 or rows[0] != 'KDM6AD_APPLIED_V1' or not _INTEGER_PAIR.fullmatch(rows[1]):
        raise ValueError('malformed applied heating packet')
    step, count = map(int, rows[1].split(' '))
    if step != expected_step or count != len(updates):
        raise ValueError('applied heating step/count differs from request')
    result = []
    seen = set()
    for line, update in zip(rows[2:], updates):
        match = _ACK_ROW.fullmatch(line)
        if match is None:
            raise ValueError('malformed applied heating row')
        i, k, j = map(int, match.groups()[:3])
        if (i, k, j) != (update.i, update.k, update.j) or (i, k, j) in seen:
            raise ValueError('applied heating coordinates differ from request')
        seen.add((i, k, j))
        old, delta, new = (int(x, 16) for x in match.groups()[3:])
        before, direction, after = map(_from_bits, (old, delta, new))
        if (not all(np.isfinite(x) for x in (before, direction, after))
                or direction == 0 or delta != _f32_bits(update.delta)):
            raise ValueError('applied heating values differ from finite nonzero request')
        with np.errstate(over='ignore'):
            expected = np.float32(before + direction)
        if not np.isfinite(expected) or new != _f32_bits(expected) or new == old:
            raise ValueError('applied memory increment does not match binary32 addition')
        result.append(AppliedHeating(update, old, delta, new))
    return tuple(result)
