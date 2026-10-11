#!/usr/bin/env python3
"""Bind the pre-residual selected natural native column to its actual AMI pixel.

This is a one-case producer using the PR403 wire format, not a historical
PR403 execution. Existing LA decoding, geolocation and PR404 mask helpers are
reused. No observation, date, quality, native state or analysis gate is invented.
"""
import importlib.util
import json
import hashlib
from pathlib import Path
import sys

import netCDF4
import numpy as np

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(ROOT / 'oracle'))
from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table, unpack_ami_word  # noqa: E402
from kdm6.obs.gk2a_l1b_la import read_la_slot  # noqa: E402

PRIVATE = Path('/Users/yhlee/KDM6AD-k/host/research_evidence/pr412_native_process_20261012/inputs')
ORIGINAL = ROOT / 'harness/evidence/pr411_v4_actual_integration_2026-10-12'
CAL = ROOT / 'oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json'
V4 = ROOT / 'harness/evidence/pr407_native_saved_time_bound_2026-10-11'
MASK = ROOT / 'harness/evidence/pr404_l1b_source_mask_2026-10-11/heldout_l1b_v3.py'
DATE, SLOT = '20250719', '202507190556'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def publish(path, value, private=False):
    with path.open('x') as stream:
        if private:
            path.chmod(0o600)
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    if not __debug__:
        raise RuntimeError('this exact research producer requires unoptimized Python checks')
    binding_plan = json.loads((PACKET / 'BINDING_PLAN.json').read_text())
    assert sha(__file__) == binding_plan['producer_sha256']
    assert sha(PACKET / 'SELECTION_RECOVERED_RESULT.json') == binding_plan['selection_result_sha256']
    selected_result = json.loads((PACKET / 'SELECTION_RECOVERED_RESULT.json').read_text())
    assert selected_result['status'] == 'NATIVE_CANDIDATE_SELECTED'
    selected = selected_result['selected']
    assert sha(ORIGINAL / 'RESTORE_RESULT.json') == binding_plan['original_files_receipt_sha256']
    restored = json.loads((ORIGINAL / 'RESTORE_RESULT.json').read_text())
    plan = json.loads((ORIGINAL / 'RESTORE_PLAN.json').read_text())
    original_path = Path(plan['original_metadata_path'])
    assert sha(original_path) == plan['original_metadata_sha256']
    original_sources = json.loads(original_path.read_text())['ami_metadata']['source_files']
    assert restored['status'] == 'ALL_NINE_ORIGINAL_HASHES_RESTORED'
    assert restored['plan_sha256'] == sha(ORIGINAL / 'RESTORE_PLAN.json')
    assert sha(CAL) == plan['original_calibration_sha256']
    files = [Path(row['path']) for row in restored['files']]
    assert len(files) == len(original_sources) == 9
    assert [(r['name'], r['expected_sha256']) for r in restored['files']] == [
        (r['source_id'], r['sha256']) for r in original_sources]
    assert [p.name for p in files] == [f'gk2a_ami_le1b_{c}_la020ge_{SLOT}.nc' for c in CLEAN_IR_CHANNELS]
    assert all(sha(p) == item['expected_sha256'] for p, item in zip(files, restored['files']))
    producer_sha = sha(__file__)
    reader_sources = {name: sha(ROOT / name) for name in (
        'oracle/kdm6/obs/gk2a_l1b_la.py', 'oracle/kdm6/obs/gk2a_l1b.py',
        'oracle/kdm6/obs/gk2a_l1b_fd.py', 'oracle/kdm6/obs/obs_ingest.py')}
    helpers = module(MASK, 'pr412_current_l1b_patch_helpers')
    reader = read_la_slot(files, load_cal_table(CAL), stride=1)
    payload = reader.payload
    lat, lon, bt, quality = [value.numpy() for value in
                            (payload.lat, payload.lon, payload.bt, payload.obs_quality)]
    finite = np.isfinite(lat) & np.isfinite(lon)
    indices = np.flatnonzero(finite)
    assert indices.size > 0
    distances = helpers.haversine_m(lat[finite], lon[finite],
        target_lat=selected['latitude_deg'], target_lon=selected['longitude_deg'])
    idx = int(indices[np.argmin(distances)])
    distance = float(np.min(distances))
    row, col = int(reader.pixel_rows[idx]), int(reader.pixel_cols[idx])
    # Location is fixed geographically before quality or BT are considered.
    assert distance <= 2500
    assert np.all(quality[idx, 2:] == 0)
    assert np.isfinite(bt[idx, 2:]).all()
    point = {'row': row, 'column': col, 'latitude_deg': float(lat[idx]),
             'longitude_deg': float(lon[idx]), 'distance_to_fixed_point_m': distance,
             'bt_K_by_channel': {c: float(bt[idx, j]) for j, c in enumerate(CLEAN_IR_CHANNELS)},
             'reader_dqf_by_channel': {c: int(quality[idx, j]) for j, c in enumerate(CLEAN_IR_CHANNELS)}}
    lookup = {(int(r), int(c)): i for i, (r, c) in enumerate(zip(reader.pixel_rows, reader.pixel_cols))}
    arrays = {DATE+'_patch_latitude_deg': np.full((5, 5), np.nan),
              DATE+'_patch_longitude_deg': np.full((5, 5), np.nan),
              DATE+'_patch_bt_K': np.full((5, 5, 9), np.nan),
              DATE+'_patch_reader_dqf': np.full((5, 5, 9), -1, dtype=np.int16)}
    for rr in range(5):
        for cc in range(5):
            k = lookup.get((row-2+rr, col-2+cc))
            if k is not None:
                arrays[DATE+'_patch_latitude_deg'][rr, cc] = lat[k]
                arrays[DATE+'_patch_longitude_deg'][rr, cc] = lon[k]
                arrays[DATE+'_patch_bt_K'][rr, cc] = bt[k]
                arrays[DATE+'_patch_reader_dqf'][rr, cc] = quality[k]
    raw, missing, padding, raw_dqf = [], [], [], []
    for path in files:
        with netCDF4.Dataset(path) as ds:
            var = ds['image_pixel_values']
            w, m, p = helpers.source_patch_canvas(var, row, col)
            _, q = unpack_ami_word(w, int(var.number_of_valid_bits_per_pixel))
            raw.append(w); missing.append(m); padding.append(p); raw_dqf.append(q)
    for key, values in (('raw_words', raw), ('source_missing_mask', missing),
                        ('padding_mask', padding), ('raw_embedded_dqf', raw_dqf)):
        arrays[DATE+'_'+key] = np.stack(values, axis=-1)
    npz = PRIVATE / 'SELECTED_L1B_PATCH.npz'
    with npz.open('xb') as stream:
        npz.chmod(0o600)
        np.savez_compressed(stream, **arrays)
    producer = {'name': 'pr412_selected_native_l1b_binding_v1', 'source_sha256': producer_sha,
                'wire_schema_only': 'PR403 v1 format required by unchanged V4; not a historical PR403 run',
                'new_dates': 0, 'selection_result_sha256': sha(PACKET / 'SELECTION_RECOVERED_RESULT.json'), 'binding_plan_sha256': sha(PACKET / 'BINDING_PLAN.json'), 'restoration_receipt_sha256': sha(ORIGINAL / 'RESTORE_RESULT.json'),
                'current_mask_helper_sha256': sha(MASK), 'reader_sources_sha256': reader_sources,
                'paired_calibration_sha256': sha(CAL),
                'original_metadata_sha256': plan['original_metadata_sha256']}
    scene = {'date': DATE, 'status': 'POINT_WITHIN_RADIUS', 'selected_nominal_slot_obt': SLOT,
             'nearest_pixel': point, 'nearest_pixel_within_2p5km': True,
             'time_interpretation': 'Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; payload valid_time_utc remains unset.'}
    metadata_path = PRIVATE / 'DECODE_RECEIPT.json'
    publish(metadata_path, {'producer': producer, 'scenes': [{**scene, 'reader_metadata': reader.metadata}],
            'private_npz_path': str(npz), 'private_npz_sha256': sha(npz),
            'source_files': restored['files'], 'no_other_observation_or_phase_inputs': True}, private=True)
    wire = PACKET / 'L1B_WIRE_RESULT.json'
    publish(wire, {'schema': 'pr403_gk2a_l1b_heldout_result_v1', 'status': 'DECODED_GK2A_L1B_SCENES_ONLY',
            'producer': producer, 'private_decode_receipt_path': str(metadata_path),
            'private_payload_path': str(npz), 'private_payload_sha256': sha(npz), 'scenes': [scene]})
    assert sha(__file__) == producer_sha
    assert all(sha(ROOT / name) == digest for name, digest in reader_sources.items())
    assert all(sha(p) == item['expected_sha256'] for p, item in zip(files, restored['files']))
    case = json.loads((V4 / 'cases/CORE_REPLAY19_V4_CASE.json').read_text())
    case['case_id'] = 'PR412_JUL19_NATURAL_LIQUID_COLUMN'
    case['native']['column'].update(j=selected['j'], i=selected['i'],
        expected_latitude_deg=selected['latitude_deg'], expected_longitude_deg=selected['longitude_deg'])
    case['observation'].update(source_result_path=str(wire), source_result_sha256=sha(wire),
        source_payload_path=str(npz), source_payload_sha256=sha(npz),
        source_metadata_path=str(metadata_path), source_metadata_sha256=sha(metadata_path), nearest_pixel=point)
    case['output'] = {'manifest_path': str(PACKET / 'INTAKE.json'),
                      'private_npz_path': str(PRIVATE / 'SELECTED_CORE_BOUND_V4.npz')}
    case_path = PACKET / 'CASE.json'
    publish(case_path, case)
    intake = module(V4 / 'intake_native_case_v4.py', 'pr412_unchanged_v4_intake')
    bound = intake.load_case(case_path)
    assert bound['manifest']['observation']['binding_status'] == 'BOUND_GK2A_L1B_SCENE'
    intake.load_bound_intake(PACKET / 'INTAKE.json', PRIVATE / 'SELECTED_CORE_BOUND_V4.npz')
    print(json.dumps({'case_id': case['case_id'], 'status': 'BOUND_READY_FOR_REAL_V4',
                      'new_native_M_RTTOV_optimizer_calls': 0}))


if __name__ == '__main__':
    main()
