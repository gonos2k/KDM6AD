#!/usr/bin/env python3
"""Recover JSON from the saved slice after the NumPy-index serialization failure.

No native meteorological arrays, L1B values, M/H or optimizer are opened/called.
Only the small forecast Times coordinate is rechecked to complete its metadata.
The original plan, executed selector and failed output are preserved unchanged.
"""
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

from select_native_column import load

PACKET = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    failure_path = PACKET / 'SELECTION_FAILURE.json'
    failure = json.loads(failure_path.read_text())
    plan_path = PACKET / 'SELECTION_PLAN.json'
    plan = json.loads(plan_path.read_text())
    if sha(plan_path) != failure['plan_sha256'] or sha(PACKET/'select_native_column.py') != failure['selector_sha256']:
        raise ValueError('historical executed selector/plan changed')
    private = Path(failure['private_slice_path'])
    if sha(private) != failure['private_slice_sha256']:
        raise ValueError('saved slice changed')
    with np.load(private, allow_pickle=False) as z:
        arrays = {n:z[n] for n in z.files}
    js, ins = np.argwhere(arrays['eligible_mask']).T
    candidates = sorted((float(arrays['distance_to_original_native_center_m'][j,i]),int(j)+plan['j_inclusive'][0],int(i)+plan['i_inclusive'][0]) for j,i in zip(js,ins))
    selected = None
    if candidates:
        d,j,i = candidates[0];jj=j-plan['j_inclusive'][0];ii=i-plan['i_inclusive'][0]
        qc = arrays['QCLOUD'][:,jj,ii]
        t = arrays['derived_temperature_K'][:,jj,ii]
        cloud = qc >= plan['qc_threshold_kg_kg_dry']
        warm = cloud & (t >= plan['cloud_temperature_min_K'])
        selected = {'j':j,'i':i,'latitude_deg':float(arrays['XLAT'][jj,ii]),'longitude_deg':float(arrays['XLONG'][jj,ii]),
                    'distance_to_original_native_center_m':d,'qc_max_kg_kg_dry':float(qc.max()),
                    'qc_threshold_layers':int(cloud.sum()),'warm_qc_threshold_layers':int(warm.sum()),
                    'temperature_min_on_qc_threshold_K':float(t[cloud].min()),
                    'temperature_min_on_warm_qc_threshold_K':float(t[warm].min())}
    v4 = load(plan['v4_intake_path'])
    case = v4.validate_case(json.loads(Path(plan['case_path']).read_text()))
    gate = v4._completion_gate(case)
    forecast = Path(plan['forecast_path'])
    stat = forecast.stat()
    if (stat.st_size,stat.st_mtime_ns)!=(plan['forecast_size_bytes'],plan['forecast_mtime_ns']):
        raise ValueError('forecast stat changed')
    with netCDF4.Dataset(forecast) as ds:
        times=v4._read_wrf_times(ds)
        v4.assert_saved_times_within_production_window(times,gate['effective_start_time'],gate['effective_stop_time'])
    masks={'finite_screened':'valid_mask','open_ocean':'ocean_mask','warm_natural_cloud':'warm_cloud_mask','frozen_absence':'frozen_absence_mask','eligible':'eligible_mask'}
    result={'schema':'pr412_native_process_selection_recovered_v1','status':'NATIVE_CANDIDATE_SELECTED' if selected else 'NO_ELIGIBLE_NATIVE_COLUMN_IN_PREDECLARED_SLICE',
            'selected':selected,'counts':{'inspected':int(arrays['eligible_mask'].size),**{k:int(arrays[v].sum()) for k,v in masks.items()}},
            'original_plan_sha256':sha(plan_path),'failure_receipt_sha256':sha(failure_path),'recovery_source_sha256':sha(__file__),
            'private_slice_path':str(private),'private_slice_sha256':sha(private),
            'array_inventory':{n:{'shape':list(v.shape),'dtype':str(v.dtype),'sha256':hashlib.sha256(np.ascontiguousarray(v).tobytes()).hexdigest()} for n,v in arrays.items()},
            'saved_times_metadata':v4.saved_times_metadata(times),'producer_gate':gate,
            'forecast_full_file_rehashed':False,'metadata_Times_rechecked_without_array_rescan':True,
            'native_array_scans':1,'selection_region_expansions':0,'M_H_optimizer_calls':0,'native_integrations':0,
            'BT_or_residuals_read_for_selection':False,'science_accepted':False}
    serialized=json.dumps(result,indent=2,allow_nan=False)+'\n'
    with (PACKET/'SELECTION_RECOVERED_RESULT.json').open('x') as stream:
        stream.write(serialized)
    print(json.dumps({'status':result['status'],'counts':result['counts'],'selected':selected}))


if __name__ == '__main__':
    main()
