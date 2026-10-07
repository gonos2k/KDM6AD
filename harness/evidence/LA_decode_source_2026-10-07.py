#!/usr/bin/env python3
"""Actual LA decode and independent arithmetic/geometry checks; no model run."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'oracle'))
from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table
from kdm6.obs.gk2a_l1b_la import read_la_slot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    files = sorted(args.input_dir.glob('*.nc'))
    table_path = ROOT / 'oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json'
    table_hash = sha(table_path)
    table = load_cal_table(table_path)
    source_paths = [ROOT / p for p in [
        'oracle/kdm6/obs/gk2a_l1b_la.py', 'oracle/kdm6/obs/gk2a_l1b.py',
        'oracle/kdm6/obs/gk2a_l1b_fd.py', 'oracle/kdm6/obs/obs_ingest.py']]
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    input_hashes = {p.name: sha(p) for p in files}
    result = read_la_slot(files, table, stride=1)
    payload = result.payload
    if payload.valid_time_utc is not None:
        raise RuntimeError('OBT was exposed as verified UTC')
    rows, cols = result.pixel_rows, result.pixel_cols
    checks = {}
    radiances = []
    for j, ch in enumerate(CLEAN_IR_CHANNELS):
        path = args.input_dir / f'gk2a_ami_le1b_{ch}_la020ge_202507190534.nc'
        with netCDF4.Dataset(path) as ds:
            variable = ds.variables['image_pixel_values']
            variable.set_auto_maskandscale(False)
            raw = np.asarray(variable[:], dtype=np.uint16)
            bits = int(variable.getncattr('number_of_valid_bits_per_pixel'))
        packed_quality = (raw.astype(np.uint32) // 16384) % 4
        dn = raw.astype(np.uint32) % (1 << bits)
        c = table['channels'][ch]
        radiance = float(c['DN_to_Radiance_Offset']) + float(c['DN_to_Radiance_Gain']) * dn
        if not np.all(np.isfinite(radiance) & (radiance > 0)):
            raise RuntimeError('This independent probe requires the retained positive-radiance domain')
        quality = np.where((radiance <= 0) & (packed_quality == 0), 3, packed_quality)
        if not np.array_equal(payload.obs_quality[:, j].numpy(), quality[rows, cols]):
            raise RuntimeError('Independent DQF result differs')
        wn = float(c['bt_wavenumber_cm1']) * 100
        planck_r = 2 * float(c['Plank_constant_h']) * float(c['light_speed'])**2 * wn**3
        teff = (float(c['Plank_constant_h']) * float(c['light_speed']) * wn
                / float(c['Boltzmann_constant_k']) / np.log1p(planck_r / (radiance * 1e-5)))
        expected = (float(c['Teff_to_Tbb_c0']) + float(c['Teff_to_Tbb_c1']) * teff
                    + float(c['Teff_to_Tbb_c2']) * teff * teff)
        difference = float(np.max(np.abs(payload.bt[:, j].numpy() - expected[rows, cols])))
        if difference >= 1e-10:
            raise RuntimeError('Independent Planck result differs')
        checks[ch] = dict(dqf_exact=True, bt_max_abs_difference_K=difference,
            quality_counts={str(int(q)): int((quality[rows, cols] == q).sum()) for q in np.unique(quality)},
            bt_min_K=float(payload.bt[:, j].min()), bt_max_K=float(payload.bt[:, j].max()))
        radiances.append(radiance[rows, cols])
    # Independent ellipsoidal Cartesian forward projection recovers NMSC scan
    # coordinates (one-based); raster provenance indices remain zero-based.
    g = result.metadata['geos']
    lat = np.deg2rad(payload.lat.numpy())
    lon = np.deg2rad(payload.lon.numpy()) - g['sub_longitude']
    a, b = g['earth_equatorial_radius'], g['earth_polar_radius']
    e2 = 1 - b*b/(a*a)
    normal = a / np.sqrt(1 - e2*np.sin(lat)**2)
    x = normal*np.cos(lat)*np.cos(lon)
    y = normal*np.cos(lat)*np.sin(lon)
    z = normal*(1-e2)*np.sin(lat)
    ray_x = g['nominal_satellite_height'] - x
    sx, sy = np.arctan2(y, ray_x), np.arctan2(z, np.sqrt(ray_x*ray_x+y*y))
    recovered_cols = g['coff'] + np.rad2deg(sx)*g['cfac']/65536
    recovered_rows = g['loff'] + np.rad2deg(sy)*g['lfac']/65536
    row_error = float(np.max(np.abs(recovered_rows-(rows+1))))
    col_error = float(np.max(np.abs(recovered_cols-(cols+1))))
    if max(row_error, col_error) >= 1e-8:
        raise RuntimeError('Independent projection does not recover scan indices')
    if table_hash != sha(table_path) or input_hashes != {p.name: sha(p) for p in files} or source_hashes != {
            str(p.relative_to(ROOT)): sha(p) for p in source_paths}:
        raise RuntimeError('Source or input changed during probe')
    output = args.output_dir / 'decoded.npz'
    np.savez_compressed(output, bt=payload.bt.numpy(), obs_quality=payload.obs_quality.numpy(),
        radiance_mW_m2_sr_cm1=np.stack(radiances, axis=1), lat=payload.lat.numpy(),
        lon=payload.lon.numpy(), pixel_rows=rows, pixel_cols=cols)
    receipt = dict(metadata=result.metadata, channels=checks, n_pixels=payload.n_obs,
        n_channel_values=int(payload.bt.numel()),
        latitude_range=[float(payload.lat.min()), float(payload.lat.max())],
        longitude_range=[float(payload.lon.min()), float(payload.lon.max())],
        forward_projection_max_pixel_error=dict(row=row_error, column=col_error),
        input_hashes=input_hashes, source_hashes=source_hashes,
        producer_sha256=sha(__file__), table_sha256=table_hash, decoded_sha256=sha(output),
        scientific_phase_verified=False, model_collocated=False, actual_utc_verified=False,
        scope='one retained LA scene; real image values/DQF/BT/nominal GEOS read; no KDM/RTTOV/model run')
    (args.output_dir / 'result.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(payload.bt.shape, 'quality exact; BT log1p and geometry checks pass; UTC remains unset')


if __name__ == '__main__':
    main()
