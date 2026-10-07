#!/usr/bin/env python3
"""Read pinned independent science and screen nominal native-grid candidates.

Offline receipt producer, not a cloud retrieval, footprint operator or DA path.
Requires numpy, scipy and netCDF4. No network or model-state substitution.
"""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np
from scipy.spatial import cKDTree

FILES = {
    'JRR-CloudPhase_v3r2_j01_s202507190554217_e202507190555463_c202507190622280.nc':
        '9ff002cd37aeb2b99de3fd93a62aa0db7826c6fd77366c98117f76e811a2dd4b',
    'JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc':
        '7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2',
    'JRR-CloudPhase_v3r2_j01_s202507190557115_e202507190558360_c202507190621256.nc':
        '31111e5cbe18693d7626f51aa1472013de6be4d4549e81a30aef1530d8dae9ec',
}
IC_SHA = '5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970'
PHASE = {0: 'clear', 1: 'liquid (>273 K retrieval category)',
         2: 'supercooled', 3: 'mixed', 4: 'ice', 5: 'undetermined'}
RADIUS_M = 6371008.8


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _sha_stream(handle)


def _sha_stream(handle):
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1048576), b''):
        digest.update(block)
    return digest.hexdigest()


def xyz(lat, lon):
    # NetCDF geolocation is f32; promote before trigonometry, not after it.
    a = np.deg2rad(np.asarray(lat, dtype=np.float64))
    b = np.deg2rad(np.asarray(lon, dtype=np.float64))
    return np.stack((np.cos(a)*np.cos(b), np.cos(a)*np.sin(b), np.sin(a)), axis=-1)


def counts(values):
    keys, numbers = np.unique(values, return_counts=True)
    return {str(int(k)): int(n) for k, n in zip(keys, numbers)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--originals', type=Path, required=True)
    parser.add_argument('--native-input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output already exists')
    if sha(args.native_input) != IC_SHA:
        raise ValueError('native input is not the retained 5 km IC')
    with netCDF4.Dataset(args.native_input) as d:
        lat = np.asarray(d['XLAT'][0], dtype=np.float64)
        lon = np.asarray(d['XLONG'][0], dtype=np.float64)
        land = np.asarray(d['XLAND'][0])
        times = netCDF4.chartostring(d['Times'][:]).tolist()
    # NetCDF dimensions are (south_north, west_east), not the advertised nx by ny.
    if lat.shape != (282, 234) or lon.shape != lat.shape or land.shape != lat.shape:
        raise ValueError('native geometry shape mismatch')
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError('native geolocation nonfinite')
    tree = cKDTree(xyz(lat, lon).reshape(-1, 3))
    records, candidates = [], []
    for name, expected_sha in FILES.items():
        path = args.originals / name
        if sha(path) != expected_sha:
            raise ValueError(f'original hash differs: {name}')
        with netCDF4.Dataset(path) as d:
            a = np.ma.filled(d['Latitude'][:], np.nan)
            b = np.ma.filled(d['Longitude'][:], np.nan)
            phase = np.ma.filled(d['CloudPhase'][:], -128)
            flag = np.ma.filled(d['CloudPhaseFlag'][:], -128)
            if a.shape != (768, 3200) or b.shape != a.shape or phase.shape != a.shape or flag.shape != (*a.shape, 1):
                raise ValueError('retained science/QA schema differs')
            raw_time = {k: d.getncattr(k) for k in ('time_coverage_start', 'time_coverage_end')}
            # Coverage strings have explicit Z. They are granule bounds, not pixel times.
            if not all(v.endswith('Z') for v in raw_time.values()):
                raise ValueError('coverage has no explicit UTC indicator')
        flag = flag[..., 0]
        bbox = (a >= lat.min()) & (a <= lat.max()) & (b >= lon.min()) & (b <= lon.max())
        rr, cc = np.where(bbox & np.isfinite(a) & np.isfinite(b))
        chord, index = tree.query(xyz(a[rr, cc], b[rr, cc]), workers=1)
        meters = 2*RADIUS_M*np.arcsin(np.minimum(chord/2, 1))
        jj, ii = np.unravel_index(index, lat.shape)
        # Predeclared nominal screen: <=3.5 km and ten native cells from each edge.
        interior = (meters <= 3500) & (jj >= 10) & (ii >= 10) & (jj < lat.shape[0]-10) & (ii < lat.shape[1]-10)
        records.append(dict(file=name, sha256=expected_sha, bytes=path.stat().st_size,
            azure_url='https://jpss.blob.core.windows.net/noaa-20/VIIRS-JRR-CloudPhase/2025/07/19/'+name,
            time_coverage=raw_time, extrema_rectangle_pixels=int(len(rr)),
            nominal_interior_pixels=int(interior.sum()),
            phase_counts=counts(phase[rr[interior], cc[interior]]),
            raw_quality_counts=counts(flag[rr[interior], cc[interior]])))
        # Zero raw QA is a candidate screen only: doc/file packing ambiguity remains.
        eligible = interior & (phase[rr, cc] == 1) & (flag[rr, cc] == 0) & (land[jj, ii] == 2)
        if eligible.any():
            choice = np.flatnonzero(eligible)[np.argmin(meters[eligible])]
            r, c, j, i = (int(x[choice]) for x in (rr, cc, jj, ii))
            candidates.append(dict(file=name, obs_row_col_0based=[r, c], native_j_i_0based=[j, i],
                obs_lat_lon=[float(a[r, c]), float(b[r, c])],
                native_lat_lon=[float(lat[j, i]), float(lon[j, i])],
                spherical_center_distance_m=float(meters[choice]), xland=int(land[j, i]),
                phase_code=int(phase[r, c]), phase_category=PHASE[int(phase[r, c])],
                quality_raw=int(flag[r, c]), time_coverage=raw_time))
        if sha(path) != expected_sha:
            raise ValueError('science source changed during reading')
    if sha(args.native_input) != IC_SHA:
        raise ValueError('native source changed during reading')
    selected = min(candidates, key=lambda x: x['spherical_center_distance_m']) if candidates else None
    result = dict(schema='retained_viirs_nominal_native_candidate_v1',
        producer_sha256=sha(__file__), native_input_sha256=IC_SHA,
        native_input_times=times, native_geometry_only=True,
        native_geometry_dimensions=['south_north', 'west_east'],
        native_geometry_shape=list(lat.shape), files=records,
        candidate_policy='phase code1, raw QA0, native XLAND2, <=3500m, ten-cell edge margin; minimum distance',
        selected_candidate=selected, candidates=candidates,
        distance_definition='unit-sphere great-circle centers, R=6371008.8 m; not ellipsoid/PSF/parallax',
        independent_sensor='NOAA-20 VIIRS; derived retrieval uses ancillary GFS/CMC SST, not ground truth',
        cloud_phase_document='NOAA ATBD v3.0 Table31 p74; quality Table32 p75; file flags retained raw',
        scientific_qa_approved=False, warm_single_layer_verified=False,
        pixel_time_verified=False, ami_matched=False, target_native_state_generated=False,
        kdm_rttov_or_host_run=False)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(selected, indent=2))


if __name__ == '__main__':
    main()
