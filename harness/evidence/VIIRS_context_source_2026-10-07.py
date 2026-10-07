#!/usr/bin/env python3
"""Stored-byte QA and nominal neighborhoods of the retained VIIRS candidate.

No scan interpolation, category averaging, footprint weighting or model state.
The PR387 producer/result are historical: its 'raw' QA counts used auto masking.
"""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

ORIGINALS = {
    'JRR-CloudPhase_v3r2_j01_s202507190554217_e202507190555463_c202507190622280.nc':
        '9ff002cd37aeb2b99de3fd93a62aa0db7826c6fd77366c98117f76e811a2dd4b',
    'JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc':
        '7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2',
    'JRR-CloudPhase_v3r2_j01_s202507190557115_e202507190558360_c202507190621256.nc':
        '31111e5cbe18693d7626f51aa1472013de6be4d4549e81a30aef1530d8dae9ec',
}
SELECTED = tuple(ORIGINALS)[1]
ROW, COL = 205, 27
RADIUS_M = 6371008.8


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stored(variable):
    """Read actual stored codes, including bytes outside misleading valid_range."""
    variable.set_auto_maskandscale(False)
    return np.asarray(variable[:])


def counts(values):
    keys, numbers = np.unique(values, return_counts=True)
    return {str(int(k)): int(n) for k, n in zip(keys, numbers)}


def qa_statistics(raw, fill, valid_range):
    present = raw != fill
    return dict(stored_counts=counts(raw), fill_pixels=int((~present).sum()),
                nonfill_outside_declared_range=int((present & ((raw < valid_range[0]) |
                                                  (raw > valid_range[1]))).sum()))


def distance_m(lat, lon, center):
    a = np.deg2rad(np.asarray(lat, dtype=np.float64))
    b = np.deg2rad(np.asarray(lon, dtype=np.float64))
    ca, cb = np.deg2rad(center)
    h = np.sin((a-ca)/2)**2 + np.cos(a)*np.cos(ca)*np.sin((b-cb)/2)**2
    return 2*RADIUS_M*np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--originals', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output already exists')
    records = []
    for name, pinned_sha in ORIGINALS.items():
        path = args.originals / name
        if sha(path) != pinned_sha:
            raise ValueError(f'original hash mismatch: {name}')
        with netCDF4.Dataset(path) as d:
            variable = d['CloudPhaseFlag']
            default = variable[:]
            fill = int(variable.getncattr('_FillValue'))
            valid_range = variable.getncattr('valid_range').astype(int).tolist()
            raw = stored(variable)
            record = dict(file=name, sha256=pinned_sha, qa_fill_value=fill,
                qa_declared_valid_range=valid_range,
                netcdf_default_masked_pixels=int(np.ma.getmaskarray(default).sum()),
                **qa_statistics(raw, fill, valid_range))
            if name == SELECTED:
                a, b = stored(d['Latitude']), stored(d['Longitude'])
                phase, kind = stored(d['CloudPhase']), stored(d['CloudType'])
                packed = stored(d['CloudTypePacked'])
                if a.shape != (768, 3200) or raw.shape != (*a.shape, 1):
                    raise ValueError('retained geometry/QA dimensions differ')
                center = [float(a[ROW, COL]), float(b[ROW, COL])]
                valid_geo = np.isfinite(a) & np.isfinite(b) & (a >= -90) & (a <= 90) & (b >= -180) & (b <= 180)
                distance = distance_m(a, b, center)
                selected = dict(file=name, row_col_0based=[ROW, COL], lat_lon=center,
                    phase_code=int(phase[ROW, COL]), cloud_type_code=int(kind[ROW, COL]),
                    quality_stored_byte=int(raw[ROW, COL, 0]),
                    type_diagnostic_stored_bytes=packed[ROW, COL].astype(int).tolist(),
                    granule_time_coverage={k:d.getncattr(k) for k in ('time_coverage_start', 'time_coverage_end')})
                neighborhoods = []
                for radius in (1000, 3500, 5000, 10000):
                    mask = valid_geo & (distance <= radius)
                    rr, cc = np.where(mask)
                    neighborhoods.append(dict(radius_m=radius, nominal_center_count=int(mask.sum()),
                        phase_counts=counts(phase[mask]), cloud_type_counts=counts(kind[mask]),
                        quality_stored_counts=counts(raw[..., 0][mask]),
                        row_col_extrema=[int(rr.min()), int(rr.max()), int(cc.min()), int(cc.max())]))
                record['invalid_geolocation_pixels'] = int((~valid_geo).sum())
            records.append(record)
        if sha(path) != pinned_sha:
            raise ValueError('source changed during read')
    result = dict(schema='retained_viirs_stored_context_v1', producer_sha256=sha(__file__),
        selected=selected, full_granule_qa=records, neighborhoods=neighborhoods,
        previous_receipt_scope='PR387 masked nonfill out-of-range QA; its raw_quality_counts are not stored-byte counts',
        raw_quality_bits_decoded=False, qa_version_approved=False,
        pixel_time_verified=False, footprint_or_parallax_matched=False,
        warm_single_layer_verified=False, kdm_rttov_or_host_run=False,
        spatial_statistic='counts of nominal geolocated centers inside spherical radii, not physical area weights or independent samples')
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(selected=selected, neighborhoods=neighborhoods), indent=2))


if __name__ == '__main__':
    main()
