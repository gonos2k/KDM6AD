#!/usr/bin/env python3
"""One predeclared native slice; no L1B BT, M/H, optimizer or archive search.

The threshold selects a model-state target, not an observed cloud phase or a
significant process response. An empty selection is a valid terminal result.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import netCDF4
import numpy as np

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    spec = importlib.util.spec_from_file_location('pr412_existing_v4', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    plan_path = PACKET / 'SELECTION_PLAN.json'
    plan_sha = sha(plan_path)
    selector_sha = sha(__file__)
    plan = json.loads(plan_path.read_text())
    if selector_sha != plan['selector_sha256']:
        raise ValueError('selector differs from frozen plan')
    for item in plan['source_bindings']:
        if sha(item['path']) != item['sha256']:
            raise ValueError('source binding changed: '+item['path'])
    result_path = PACKET / 'SELECTION_RESULT.json'
    private_path = Path(plan['private_slice_npz'])
    if result_path.exists() or private_path.exists():
        raise FileExistsError('one-time selection outputs already exist')
    v4 = load(plan['v4_intake_path'])
    case = v4.validate_case(json.loads(Path(plan['case_path']).read_text()))
    prior = json.loads(Path(plan['prior_intake_path']).read_text())['native_run']
    native = case['native']
    if (Path(plan['forecast_path']).resolve() != Path(prior['forecast_path']).resolve()
            or plan['background_valid_time'] != prior['background_valid_time']
            or plan['background_valid_time'] != native['background_valid_time']
            or plan['center_j_i'] != [prior['selected_column']['j'], prior['selected_column']['i']]
            or plan['center_j_i'] != [native['column']['j'], native['column']['i']]):
        raise ValueError('planned slice identity differs from retained native binding')
    gate = v4._completion_gate(case)
    forecast = Path(plan['forecast_path'])
    if forecast.resolve().parent != Path(gate['run_dir']).resolve():
        raise ValueError('forecast is outside the exact completed run')
    stat = forecast.stat()
    if stat.st_size != plan['forecast_size_bytes'] or stat.st_mtime_ns != plan['forecast_mtime_ns']:
        raise ValueError('retained forecast stat changed')
    j0, j1 = plan['j_inclusive']
    i0, i1 = plan['i_inclusive']
    js, ins = slice(j0, j1+1), slice(i0, i1+1)
    arrays = {}
    with netCDF4.Dataset(forecast) as ds:
        times = v4._read_wrf_times(ds)
        v4.assert_saved_times_within_production_window(times, gate['effective_start_time'], gate['effective_stop_time'])
        if (len(ds.dimensions['bottom_top']) != 39
                or len(ds.dimensions['bottom_top_stag']) != 40
                or int(getattr(ds, 'USE_THETA_M', 1)) != 1):
            raise ValueError('unsupported native grid or thermal coordinate')
        ti = times.index(plan['background_valid_time'])
        for name in plan['native_fields_3d']:
            arrays[name] = np.ma.asarray(ds[name][ti, :, js, ins], dtype=np.float64).filled(np.nan)
        for name in plan['native_fields_2d']:
            arrays[name] = np.ma.asarray(ds[name][ti, js, ins], dtype=np.float64).filled(np.nan)
        center_j, center_i = plan['center_j_i']
        center = [float(ds[name][ti, center_j, center_i]) for name in ('XLAT', 'XLONG')]
    if center != plan['center_lat_lon']:
        raise ValueError('original native center moved')
    p = arrays['P'] + arrays['PB']
    pii = np.power(p / 100000., 2./7.)
    th = (arrays['THM'] + 300.) / (1. + (461.6/287.) * arrays['QVAPOR'])
    temperature = th * pii
    valid = np.ones((j1-j0+1, i1-i0+1), dtype=bool)
    for a in arrays.values():
        valid &= np.isfinite(a).all(axis=0) if a.ndim == 3 else np.isfinite(a)
    for name in plan['nonnegative_fields']:
        valid &= np.all(arrays[name] >= 0., axis=0)
    for derived in (p, pii, th, temperature):
        valid &= np.isfinite(derived).all(axis=0)
    valid &= np.all((p > 0.) & (temperature > 0.), axis=0)
    valid &= np.all(np.diff(p, axis=0) < 0., axis=0)
    valid &= np.all(np.diff(arrays['PH'] + arrays['PHB'], axis=0) > 0., axis=0)
    # QIB is the graupel-volume proxy, not a particle number or water mass.
    for mass, number in [('QCLOUD', 'QNCLOUD'), ('QRAIN', 'QNRAIN'), ('QICE', 'QNICE'), ('QGRAUP', 'QIB')]:
        valid &= np.all((arrays[mass] <= 0.) | (arrays[number] > 0.), axis=0)
    ocean = (arrays['XLAND'] == 2.) & (arrays['SEAICE'] == 0.)
    cloud = arrays['QCLOUD'] >= plan['qc_threshold_kg_kg_dry']
    warm = np.any(cloud & (temperature >= plan['cloud_temperature_min_K']), axis=0)
    frozen = np.all(np.maximum.reduce([arrays[n] for n in ('QICE', 'QSNOW', 'QGRAUP')]) <= plan['frozen_threshold_kg_kg_dry'], axis=0)
    eligible = valid & ocean & warm & frozen
    lat, lon = np.deg2rad(arrays['XLAT']), np.deg2rad(arrays['XLONG'])
    lat0, lon0 = np.deg2rad(center)
    a = np.sin((lat-lat0)/2.)**2 + np.cos(lat)*np.cos(lat0)*np.sin((lon-lon0)/2.)**2
    distance = 6371000.*2.*np.arcsin(np.sqrt(np.clip(a, 0., 1.)))
    candidates = sorted((float(distance[j,i]), j+j0, i+i0) for j,i in np.argwhere(eligible))
    selected = None
    if candidates:
        d, j, i = candidates[0]
        jj, ii = j-j0, i-i0
        warm_layers = cloud[:,jj,ii] & (temperature[:,jj,ii] >= plan['cloud_temperature_min_K'])
        selected = {'j':j, 'i':i, 'latitude_deg':float(arrays['XLAT'][jj,ii]),
                    'longitude_deg':float(arrays['XLONG'][jj,ii]), 'distance_to_original_native_center_m':d,
                    'qc_max_kg_kg_dry':float(arrays['QCLOUD'][:,jj,ii].max()),
                    'qc_threshold_layers':int(cloud[:,jj,ii].sum()),
                    'warm_qc_threshold_layers':int(warm_layers.sum()),
                    'temperature_min_on_warm_qc_threshold_K':float(temperature[:,jj,ii][warm_layers].min()),
                    'temperature_min_on_qc_threshold_K':float(temperature[:,jj,ii][cloud[:,jj,ii]].min())}
    arrays.update(derived_temperature_K=temperature, valid_mask=valid, ocean_mask=ocean,
                  warm_cloud_mask=warm, frozen_absence_mask=frozen, eligible_mask=eligible,
                  distance_to_original_native_center_m=distance)
    with private_path.open('xb') as stream:
        private_path.chmod(0o600)
        np.savez_compressed(stream, **arrays)
    after = forecast.stat()
    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise ValueError('forecast changed during bounded read')
    if sha(plan_path) != plan_sha or sha(__file__) != selector_sha:
        raise ValueError('selection plan or selector changed during bounded read')
    if any(sha(item['path']) != item['sha256'] for item in plan['source_bindings']):
        raise ValueError('bound source changed during bounded read')
    output = {'schema':'pr412_native_process_selection_v1',
              'status':'NATIVE_CANDIDATE_SELECTED' if selected else 'NO_ELIGIBLE_NATIVE_COLUMN_IN_PREDECLARED_SLICE',
              'plan_sha256':plan_sha, 'selector_sha256':selector_sha, 'selected':selected,
              'counts':{'inspected':int(valid.size), 'finite_screened':int(valid.sum()),
                        'open_ocean':int(ocean.sum()), 'warm_natural_cloud':int(warm.sum()),
                        'frozen_absence':int(frozen.sum()), 'eligible':len(candidates)},
              'private_slice_path':str(private_path), 'private_slice_sha256':sha(private_path),
              'array_inventory':{n:{'shape':list(v.shape), 'dtype':str(v.dtype), 'sha256':hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()} for n,v in arrays.items()},
              'saved_times_metadata':v4.saved_times_metadata(times), 'producer_gate':gate,
              'forecast_full_file_rehashed':False, 'forecast_stat_stable':True,
              'native_integrations':0, 'M_H_optimizer_calls':0, 'BT_or_residuals_read_for_selection':False,
              'no_selection_expansion_or_next_candidate_retry':True, 'science_accepted':False}
    with result_path.open('x') as stream:
        stream.write(json.dumps(output, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status':output['status'], 'counts':output['counts'], 'selected':selected}))


if __name__ == '__main__':
    main()
