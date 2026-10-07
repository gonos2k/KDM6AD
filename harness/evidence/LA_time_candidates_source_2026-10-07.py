#!/usr/bin/env python3
"""Pinned external time properties on an actual header; no UTC certification."""
import argparse
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import netCDF4

SATPY_READER_SHA = 'c6fd8f4e812906f05f0361ad0377336d045dbf013c5405799bd5a8475119794a'
SATPY_COMMIT = '70e3d3b728ed630c2d7e0df5512ee5d243c48581'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--satpy-source', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output already exists')
    if sha(args.satpy_source) != SATPY_READER_SHA:
        raise ValueError('Satpy reader bytes do not match the pinned source')
    source = args.satpy_source.read_text()
    reader = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.ClassDef) and n.name == 'AMIL1bNetCDF')
    functions = [n for n in reader.body
                 if isinstance(n, ast.FunctionDef) and n.name in ('start_time', 'end_time')]
    if len(functions) != 2:
        raise ValueError('pinned time properties not found')
    namespace = {'dt': dt}
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<pinned Satpy properties>', 'exec'), namespace)
    input_sha = sha(args.input)
    with netCDF4.Dataset(args.input) as dataset:
        keys = ('observation_start_time', 'observation_end_time', 'time_synchro_utc',
                'time_synchro_obt', 'scene_acquisition_time', 'mission_reference_time')
        raw = {key: dataset.getncattr(key) for key in keys}
    handle = SimpleNamespace(nc=SimpleNamespace(attrs=raw))
    start, end = (namespace[name].fget(handle) for name in ('start_time', 'end_time'))
    if start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError('unexpected timezone in pinned external properties')
    if start.strftime('%Y%m%d_%H%M%S') != raw['scene_acquisition_time']:
        raise ValueError('conditional calendar does not match the scene label')
    # The pinned source's own test uses this numeric start and naive result.
    test_handle = SimpleNamespace(nc=SimpleNamespace(attrs={'observation_start_time': 623084431.957882}))
    if namespace['start_time'].fget(test_handle) != dt.datetime(2019, 9, 30, 3, 0, 31, 957882):
        raise ValueError('pinned external test example differs')
    offset = float(raw['time_synchro_utc'] - raw['time_synchro_obt'])
    affine_start = dt.datetime(2000, 1, 1, 12) + dt.timedelta(
        seconds=float(raw['time_synchro_utc'] + (raw['observation_start_time'] - raw['time_synchro_obt'])))
    if input_sha != sha(args.input) or SATPY_READER_SHA != sha(args.satpy_source):
        raise ValueError('input/source changed during probe')
    result = dict(satpy_commit=SATPY_COMMIT, satpy_reader_sha256=SATPY_READER_SHA,
        input_sha256=input_sha, raw=raw,
        conditional_epoch='2000-01-01T12:00:00; naive, no timezone',
        conditional_start=start.isoformat(), conditional_end=end.isoformat(),
        raw_interval_seconds=float(raw['observation_end_time']-raw['observation_start_time']),
        raw_sync_pair_difference=offset,
        conditional_affine_start=affine_start.isoformat(),
        affine_assumptions='same epoch/seconds/clock rate; input start is OBT; synchronization not already applied',
        actual_utc_verified=False, pixel_scan_time_verified=False,
        applied_to_observation_payload=False, kdm_rttov_or_model_run=False)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(start.isoformat(), end.isoformat(), 'conditional only; observation UTC remains unset')


if __name__ == '__main__':
    main()
