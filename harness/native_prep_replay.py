"""Load a saved native prep-stage capture and replay its f32 host coordinate map.

The loader joins one selected MP137 trace column to its time-matched native
restart checkpoint. It does not launch or emulate a host timestep. The returned
``X`` inputs are widened f32 values for the f64 differentiable prep operator;
``f32_replay`` independently checks the captured host prep values and phase.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import ctypes
import ctypes.util
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from harness.native_replay_compare import _decoded_char_frame, _read_frame
from harness.native_trace_records import read_native_trace
from harness.run_ss_case import _namelist_assignments
from harness.verify_native_finish_ad import TraceCase, load_case


@dataclass(frozen=True)
class NativePrepCase:
    """Captured microphysics state plus native column geometry for prep AD."""

    captured: TraceCase
    X: tuple[np.ndarray, np.ndarray, float, np.ndarray]
    geometry: dict[str, Any]
    config: dict[str, Any]
    f32_replay: dict[str, Any]
    phase_provenance: dict[str, Any]
    xland: float


def _f32(value: Any) -> np.float32:
    return np.float32(value)


def _raw32(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=np.float32).view(np.uint32)


def _same32(actual: Any, expected: Any) -> bool:
    return bool(np.array_equal(_raw32(actual), _raw32(expected)))


def _first(assignments: dict[str, list[str]], key: str, default: str | None = None) -> str:
    values = assignments.get(key)
    if values:
        return values[0].strip().strip("'\"")
    if default is None:
        raise ValueError(f"namelist is missing required key {key!r}")
    return default


def _float_value(assignments: dict[str, list[str]], key: str, default: str | None = None) -> float:
    return float(_first(assignments, key, default).replace('D', 'E').replace('d', 'e'))


def _require_number(assignments: dict[str, list[str]], key: str, expected: float,
                    default: str | None = None) -> None:
    actual = _float_value(assignments, key, default)
    if not np.isfinite(actual) or actual != expected:
        raise ValueError(f'{key}={actual} differs from required value {expected}')


def _logical_value(assignments: dict[str, list[str]], key: str) -> bool:
    raw = _first(assignments, key).strip().lower()
    import re
    match = re.fullmatch(r"(?:(\d+)\s*\*\s*)?(?:\.(true|false)\.|(true|false)|([tf]))", raw)
    if not match:
        raise ValueError(f'{key} is not a supported Fortran logical value: {raw}')
    count = int(match.group(1) or '1')
    if count <= 0:
        raise ValueError(f'{key} has a nonpositive logical repeat count')
    token = match.group(2) or match.group(3) or match.group(4)
    return token in ('true', 't')


def _expected_checkpoint_time(assignments: dict[str, list[str]], step: int, dt: float) -> str:
    """Derive the step endpoint from the actual namelist start time and dt."""
    start_date = assignments.get('start_date')
    if start_date:
        stamp = start_date[0].strip().strip("'\"")
        start = datetime.strptime(stamp, '%Y-%m-%d_%H:%M:%S')
    else:
        parts = [int(_first(assignments, key)) for key in
                 ('start_year', 'start_month', 'start_day', 'start_hour', 'start_minute', 'start_second')]
        start = datetime(*parts)
    def rational(key, default=None):
        return Fraction(_first(assignments, key, default).replace('D', 'E').replace('d', 'e'))
    denominator = rational('time_step_fract_den', '1')
    if denominator <= 0:
        raise ValueError('TIME_STEP_FRACT_DEN must be positive')
    seconds = (rational('time_step') * step +
               rational('time_step_fract_num', '0') * step / denominator)
    if seconds.denominator != 1:
        raise ValueError('checkpoint Times has second precision; fractional-second endpoints are unsupported')
    result = start + timedelta(seconds=int(seconds))
    if result.microsecond != 0:
        raise ValueError('fractional-second checkpoint endpoint cannot be represented by WRF Times')
    return result.strftime('%Y-%m-%d_%H:%M:%S')


def _libm_function(name: str, arity: int):
    library = ctypes.util.find_library('m')
    if library is None:
        library = '/usr/lib/libSystem.B.dylib'
    lib = ctypes.CDLL(library)
    function = getattr(lib, name)
    function.restype = ctypes.c_float
    function.argtypes = [ctypes.c_float] * arity
    return function


def _fma32(function, a: float, b: float, c: float) -> np.float32:
    return _f32(function(ctypes.c_float(float(_f32(a))),
                        ctypes.c_float(float(_f32(b))),
                        ctypes.c_float(float(_f32(c)))))


def _unary_or_binary32(function, *values: float) -> np.float32:
    return _f32(function(*(ctypes.c_float(float(_f32(value))) for value in values)))


def _selected_column(dataset, name: str, i0: int, j0: int, *, levels: int,
                     interface: bool = False) -> np.ndarray:
    variable = dataset.variables[name]
    expected_dims = (('bottom_top_stag', 'south_north', 'west_east') if interface else
                     ('bottom_top', 'south_north', 'west_east'))
    if tuple(variable.dimensions) != ('Time', *expected_dims):
        raise ValueError(f'{name} dimensions {variable.dimensions} do not match WRF {expected_dims}')
    value = np.asarray(_read_frame(variable, 0), dtype=np.float32)
    expected_levels = levels + 1 if interface else levels
    if value.shape != ((expected_levels, 282, 234)):
        raise ValueError(f'{name} frame shape {value.shape} differs from native (k,j,i) grid')
    return np.asarray(value[:, j0, i0], dtype=np.float32)


def load_native_prep_case(trace, namelist, checkpoint, step, i, j, levels) -> NativePrepCase:
    """Bind one saved MP137 prep trace to its current native state/geometry.

    Args use the actual Fortran trace coordinates (1-based i/j/step/levels).
    The checkpoint must be the saved endpoint corresponding to ``start + step*dt``.
    Prep thermodynamics come from the trace's pre-finish ``T_NEW_PRE`` and MP
    input ``Q``; geometry comes from the matching saved checkpoint, whose
    post-finish pressure is intentionally treated as a different phase.
    """
    trace_path, namelist_path, checkpoint_path = map(Path, (trace, namelist, checkpoint))
    if any(type(value) is not int or value <= 0 for value in (step, i, j, levels)):
        raise ValueError('step, i, j and levels must be positive integers')
    # The caller supplies the executed namelist.output explicitly. Never read
    # an implicit sibling file outside the verifier's pinned input set.
    assignments = _namelist_assignments(namelist_path.read_text())
    _require_number(assignments, 'mp_physics', 137)
    _require_number(assignments, 'use_theta_m', 1)
    _require_number(assignments, 'no_mp_heating', 0)
    _require_number(assignments, 'use_q_diabatic', 0)
    _require_number(assignments, 'mp_zero_out_all', 0, default='0')
    _require_number(assignments, 'hypsometric_opt', 2)
    if not _logical_value(assignments, 'non_hydrostatic'):
        raise ValueError('native prep replay requires non_hydrostatic=true')
    expected_levels = int(_float_value(assignments, 'e_vert')) - 1
    if levels != expected_levels:
        raise ValueError(f'levels={levels}; full native mass column requires {expected_levels}')
    e_we = int(_float_value(assignments, 'e_we')) - 1
    e_sn = int(_float_value(assignments, 'e_sn')) - 1
    if not (1 < i < e_we and 1 < j < e_sn):
        raise ValueError('prep replay requires an interior native column')
    frac_num = _float_value(assignments, 'time_step_fract_num', '0')
    frac_den = _float_value(assignments, 'time_step_fract_den', '1')
    if frac_den <= 0:
        raise ValueError('TIME_STEP_FRACT_DEN must be positive')
    dt = _float_value(assignments, 'time_step') + frac_num / frac_den
    expected_time = _expected_checkpoint_time(assignments, step, dt)

    # Reuse the captured state/forcing and finish/Z validation without importing
    # torch; verify_native_finish_ad loads it lazily only when AD calls are used.
    captured = load_case(trace_path, namelist_path, step=step, i=i, j=j, levels=levels)
    rows = read_native_trace(trace_path)
    prep = [rows[('FINISH_PRE', step, i, k, j)] for k in range(1, levels + 1)]
    mp_inputs = [rows[('MP_INPUT', step, i, k, j)] for k in range(1, levels + 1)]
    t_pert = np.asarray([record.value('T_NEW_PRE') for record in prep], dtype=np.float32)
    qv = np.asarray([record.value('Q') for record in mp_inputs], dtype=np.float32)

    try:
        import netCDF4
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError('netCDF4 is required to load the saved native prep checkpoint') from exc

    i0, j0 = i - 1, j - 1
    with netCDF4.Dataset(checkpoint_path) as ds:
        ds.set_auto_maskandscale(False)
        if len(ds.dimensions.get('west_east', ())) != e_we:
            raise ValueError('checkpoint west_east dimension differs from namelist domain')
        if len(ds.dimensions.get('south_north', ())) != e_sn:
            raise ValueError('checkpoint south_north dimension differs from namelist domain')
        if len(ds.dimensions.get('bottom_top', ())) != levels:
            raise ValueError('checkpoint bottom_top dimension differs from namelist')
        if len(ds.dimensions.get('bottom_top_stag', ())) != levels + 1:
            raise ValueError('checkpoint interface count differs from native levels')
        if 'Times' not in ds.variables:
            raise ValueError('checkpoint has no Times variable')
        times_var = ds.variables['Times']
        if 'Time' not in tuple(times_var.dimensions) or np.dtype(times_var.dtype).kind not in ('S', 'U'):
            raise ValueError('checkpoint Times must be a Time-indexed character variable')
        times = _decoded_char_frame(np.asarray(_read_frame(times_var, 0)))
        if times != expected_time:
            raise ValueError(f'checkpoint Times={times}, expected {expected_time} from start+step*dt')

        for name in ('PH_2', 'PHB', 'ALB', 'PB', 'AL', 'P', 'QVAPOR', 'THM_2',
                     'MU_2', 'MU_1', 'MUB', 'XLAND', 'C3F', 'C4F', 'C3H', 'C4H', 'P_TOP'):
            variable = ds.variables[name]
            dtype = np.dtype(variable.dtype)
            if dtype.kind != 'f' or dtype.itemsize != 4:
                raise ValueError(f'{name} must be stored as native binary32, without dtype conversion')
            if any(attr in variable.ncattrs() for attr in ('scale_factor', 'add_offset')):
                raise ValueError(f'{name} packed scale/offset is unsupported in raw-bit replay')

        ph = _selected_column(ds, 'PH_2', i0, j0, levels=levels, interface=True)
        phb = _selected_column(ds, 'PHB', i0, j0, levels=levels, interface=True)
        alb = _selected_column(ds, 'ALB', i0, j0, levels=levels)
        pb = _selected_column(ds, 'PB', i0, j0, levels=levels)
        al_saved = _selected_column(ds, 'AL', i0, j0, levels=levels)
        p_saved = _selected_column(ds, 'P', i0, j0, levels=levels)
        qv_saved = _selected_column(ds, 'QVAPOR', i0, j0, levels=levels)
        thm_saved = _selected_column(ds, 'THM_2', i0, j0, levels=levels)
        mu2 = _f32(ds.variables['MU_2'][0, j0, i0])
        mu1 = _f32(ds.variables['MU_1'][0, j0, i0])
        mub = _f32(ds.variables['MUB'][0, j0, i0])
        xland = _f32(ds.variables['XLAND'][0, j0, i0])
        c3f = np.asarray(_read_frame(ds.variables['C3F'], 0), dtype=np.float32)
        c4f = np.asarray(_read_frame(ds.variables['C4F'], 0), dtype=np.float32)
        c3h = np.asarray(_read_frame(ds.variables['C3H'], 0), dtype=np.float32)
        c4h = np.asarray(_read_frame(ds.variables['C4H'], 0), dtype=np.float32)
        if c3f.shape != (levels + 1,) or c4f.shape != (levels + 1,):
            raise ValueError('checkpoint full-level pressure coefficients must have L+1 entries')
        if c3h.shape != (levels,) or c4h.shape != (levels,):
            raise ValueError('checkpoint half-level pressure coefficients must have L entries')
        ptop = _f32(ds.variables['P_TOP'][0])

    # Runtime constants are the captured host binary32 values.
    t0 = _f32(prep[0].value('T0'))
    alpha = _f32(prep[0].value('ALPHA'))
    rd, rv, g = _f32(287.), _f32(461.6), _f32(9.81)
    p0 = _f32(100000.)
    cp = _f32(_f32(7.) * rd / _f32(2.))
    gamma = _f32(cp / _f32(cp - rd))
    kappa = _f32(rd / cp)
    if not _same32(alpha, _f32(rv / rd)):
        raise ValueError('trace alpha differs from the active host Rv/Rd binary32 ratio')

    libm_fma = _libm_function('fmaf', 3)
    libm_log = _libm_function('logf', 1)
    libm_pow = _libm_function('powf', 2)
    muts = _f32(mub + mu2)
    al_replay = np.empty(levels, dtype=np.float32)
    den_replay = np.empty(levels, dtype=np.float32)
    delz_replay = np.empty(levels, dtype=np.float32)
    theta_replay = np.empty(levels, dtype=np.float32)
    p_replay = np.empty(levels, dtype=np.float32)
    pii_replay = np.empty(levels, dtype=np.float32)
    post_p_replay = np.empty(levels, dtype=np.float32)
    for k in range(levels):
        pfu = _f32(_fma32(libm_fma, c3f[k + 1], muts, c4f[k + 1]) + ptop)
        pfd = _f32(_fma32(libm_fma, c3f[k], muts, c4f[k]) + ptop)
        phm = _f32(_fma32(libm_fma, c3h[k], muts, c4h[k]) + ptop)
        dphi = _f32(_f32(_f32(ph[k + 1] - ph[k]) + phb[k + 1]) - phb[k])
        al_replay[k] = _f32(_f32(_f32(dphi / phm) /
                                  _unary_or_binary32(libm_log, _f32(pfd / pfu))) - alb[k])
        den_replay[k] = _f32(_f32(1.) / _f32(al_replay[k] + alb[k]))
        zlo = _f32(_f32(ph[k] + phb[k]) / g)
        zhi = _f32(_f32(ph[k + 1] + phb[k + 1]) / g)
        delz_replay[k] = _f32(zhi - zlo)
        denom = _fma32(libm_fma, alpha, qv[k], _f32(1.))
        theta_replay[k] = _f32(_f32(t_pert[k] + t0) / denom)
        temp = _f32(_f32(rd * _f32(t_pert[k] + t0)) /
                    _f32(p0 * _f32(al_replay[k] + alb[k])))
        power = _unary_or_binary32(libm_pow, temp, gamma)
        pressure_pert = _f32(_f32(power * p0) - pb[k])
        pressure_full = _f32(pressure_pert + pb[k])
        p_replay[k] = pressure_full
        pii_replay[k] = _unary_or_binary32(libm_pow, _f32(pressure_full / p0), kappa)

        t_after = rows[('FINISH_POST', step, i, k + 1, j)].value('T_NEW_AFTER')
        post_temp = _f32(_f32(rd * _f32(t_after + t0)) /
                         _f32(p0 * _f32(al_saved[k] + alb[k])))
        post_power = _unary_or_binary32(libm_pow, post_temp, gamma)
        post_pert = _f32(_f32(post_power * p0) - pb[k])
        post_p_replay[k] = _f32(post_pert + pb[k])

    expected = {
        'TH': np.asarray([r.value('TH') for r in mp_inputs], dtype=np.float32),
        'DEN': np.asarray([r.value('DEN') for r in mp_inputs], dtype=np.float32),
        'PII': np.asarray([r.value('PII') for r in mp_inputs], dtype=np.float32),
        'P': np.asarray([r.value('P') for r in mp_inputs], dtype=np.float32),
        'DELZ': np.asarray([r.value('DELZ') for r in mp_inputs], dtype=np.float32),
    }
    replayed = {'TH': theta_replay, 'DEN': den_replay, 'PII': pii_replay,
                'P': p_replay, 'DELZ': delz_replay}
    prep_checks = {}
    for field in expected:
        match = _raw32(replayed[field]) == _raw32(expected[field])
        prep_checks[field] = {
            'raw_bit_matches': int(np.count_nonzero(match)),
            'compared': levels,
            'mismatch_levels_1_based': (np.flatnonzero(~match) + 1).tolist(),
            'max_abs_difference': float(np.max(np.abs(replayed[field].astype(np.float64) - expected[field].astype(np.float64)))),
        }
    if any(item['raw_bit_matches'] != levels for item in prep_checks.values()):
        raise ValueError(f'f32 prep replay did not match all captured fields: {prep_checks}')

    cp_pressure_full = np.asarray([_f32(a + b) for a, b in zip(p_saved, pb)], dtype=np.float32)
    post_match = _raw32(post_p_replay) == _raw32(cp_pressure_full)
    al_match = _raw32(al_replay) == _raw32(al_saved)
    post_t = np.asarray([rows[('FINISH_POST', step, i, k, j)].value('T_NEW_AFTER')
                         for k in range(1, levels + 1)], dtype=np.float32)
    post_q = np.asarray([rows[('FINISH_PRE', step, i, k, j)].value('QV_PLUS')
                         for k in range(1, levels + 1)], dtype=np.float32)
    checkpoint_t_match = _raw32(post_t) == _raw32(thm_saved)
    checkpoint_q_match = _raw32(post_q) == _raw32(qv_saved)
    if not np.all(al_match):
        raise ValueError(f'checkpoint AL geometry closure failed at levels {(np.flatnonzero(~al_match)+1).tolist()}')
    if not np.all(post_match):
        raise ValueError(f'post-EOS pressure closure failed at levels {(np.flatnonzero(~post_match)+1).tolist()}')
    if not np.all(checkpoint_t_match) or not np.all(checkpoint_q_match):
        raise ValueError('FINISH_POST T/Q outputs do not match checkpoint THM_2/QVAPOR raw bits')
    wrong_mu1 = _f32(mub + mu1)
    wrong_al = np.empty(levels, dtype=np.float32)
    for k in range(levels):
        pfu = _f32(_fma32(libm_fma, c3f[k + 1], wrong_mu1, c4f[k + 1]) + ptop)
        pfd = _f32(_fma32(libm_fma, c3f[k], wrong_mu1, c4f[k]) + ptop)
        phm = _f32(_fma32(libm_fma, c3h[k], wrong_mu1, c4h[k]) + ptop)
        dphi = _f32(_f32(_f32(ph[k + 1] - ph[k]) + phb[k + 1]) - phb[k])
        wrong_al[k] = _f32(_f32(_f32(dphi / phm) /
                                 _unary_or_binary32(libm_log, _f32(pfd / pfu))) - alb[k])
    wrong_den = np.asarray([_f32(_f32(1.) / _f32(a + b)) for a, b in zip(wrong_al, alb)], dtype=np.float32)

    geometry = {
        'phb': phb.astype(np.float64), 'c3h': c3h.astype(np.float64),
        'c4h': c4h.astype(np.float64), 'c3f': c3f.astype(np.float64),
        'c4f': c4f.astype(np.float64),
    }
    config = {
        'ptop': float(ptop), 'rd': float(rd), 'p0': float(p0), 't0': float(t0),
        'alpha': float(alpha), 'gamma': float(gamma), 'kappa': float(kappa), 'g': float(g),
    }
    x = (t_pert.astype(np.float64), qv.astype(np.float64), float(muts), ph.astype(np.float64))
    f32_replay = {
        'prep_outputs': prep_checks,
        'replayed_f32': {name: values.tolist() for name, values in replayed.items()},
        'captured_f32': {name: values.tolist() for name, values in expected.items()},
        'checkpoint_AL_raw_bit_matches': int(np.count_nonzero(al_match)),
        'checkpoint_DEN_raw_bit_matches': int(np.count_nonzero(_raw32(den_replay) == _raw32(expected['DEN']))),
        'post_eos_pressure': {
            'raw_bit_matches_checkpoint_P_plus_PB': int(np.count_nonzero(post_match)),
            'compared': levels,
            'mismatch_levels_1_based': (np.flatnonzero(~post_match) + 1).tolist(),
            'max_abs_difference_Pa': float(np.max(np.abs(post_p_replay.astype(np.float64) - cp_pressure_full.astype(np.float64)))),
            'FINISH_POST_T_NEW_AFTER_matches_checkpoint_THM_2': int(np.count_nonzero(checkpoint_t_match)),
            'FINISH_PRE_QV_PLUS_matches_checkpoint_QVAPOR': int(np.count_nonzero(checkpoint_q_match)),
        },
        'pre_post_pressure_phase': {
            'MP_INPUT_P_vs_checkpoint_P_plus_PB_raw_matches': int(np.count_nonzero(_raw32(expected['P']) == _raw32(cp_pressure_full))),
            'mismatch_levels_1_based': (np.flatnonzero(_raw32(expected['P']) != _raw32(cp_pressure_full)) + 1).tolist(),
            'max_abs_difference_Pa': float(np.max(np.abs(expected['P'].astype(np.float64) - cp_pressure_full.astype(np.float64)))),
        },
    }
    phase = {
        'checkpoint_path': str(checkpoint_path), 'checkpoint_time': expected_time,
        'start_time_from_namelist': _expected_checkpoint_time(assignments, 0, dt),
        'step_endpoint_formula': 'namelist start time + ITIMESTEP * (TIME_STEP + TIME_STEP_FRACT_NUM/TIME_STEP_FRACT_DEN)',
        'checkpoint_mu2': float(mu2), 'checkpoint_mu1': float(mu1), 'checkpoint_mub': float(mub),
        'muts_reconstructed_from_checkpoint': float(muts), 'muts_source_formula': 'MUB + MU_2 (small_step_em first-RK/end-state phase)',
        'namelist_options': {
            'mp_physics': _float_value(assignments, 'mp_physics'),
            'use_theta_m': _float_value(assignments, 'use_theta_m'),
            'no_mp_heating': _float_value(assignments, 'no_mp_heating'),
            'use_q_diabatic': _float_value(assignments, 'use_q_diabatic'),
            'mp_zero_out': _float_value(assignments, 'mp_zero_out'),
            'mp_zero_out_all': _float_value(assignments, 'mp_zero_out_all', '0'),
            'hypsometric_opt': _float_value(assignments, 'hypsometric_opt'),
            'non_hydrostatic': _logical_value(assignments, 'non_hydrostatic'),
        },
        'checkpoint_alb': alb.astype(np.float64).tolist(),
        'checkpoint_pb': pb.astype(np.float64).tolist(),
        'checkpoint_al': al_saved.astype(np.float64).tolist(),
        'wrong_mu1_phase_al_matches_checkpoint': int(np.count_nonzero(_raw32(wrong_al) == _raw32(al_saved))),
        'wrong_mu1_phase_den_matches_mpinput': int(np.count_nonzero(_raw32(wrong_den) == _raw32(expected['DEN']))),
        'xland': float(xland), 'native_index': [i, j],
        'ph2_phb_note': 'checkpoint PH_2/PHB are used as geometry; nonhydrostatic calc_p_rho_phi source reads but does not assign them; no separate pre/post PH trace was captured.',
    }
    return NativePrepCase(captured, x, geometry, config, f32_replay, phase, float(xland))
