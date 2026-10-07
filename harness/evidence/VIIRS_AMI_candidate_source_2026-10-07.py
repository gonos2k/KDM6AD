#!/usr/bin/env python3
"""Read actual LA 05:56 BT/QC near the selected VIIRS nominal location.

No pixel-time, footprint, warm-column or model-state approval is inferred.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'oracle'))
from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table
from kdm6.obs.gk2a_l1b_la import read_la_slot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ami-dir', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output already exists')
    candidate_sha = sha(args.candidate)
    selected = json.loads(args.candidate.read_text())['selected_candidate']
    if selected is None:
        raise ValueError('no screened VIIRS sample')
    files = sorted(args.ami_dir.glob('*_la020ge_202507190556.nc'))
    table_path = ROOT / 'oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json'
    table_sha = sha(table_path)
    read = read_la_slot(files, load_cal_table(table_path), stride=1)
    if read.payload.valid_time_utc is not None:
        raise ValueError('LA OBT unexpectedly certified as UTC')
    a, b = np.deg2rad(read.payload.lat.numpy()), np.deg2rad(read.payload.lon.numpy())
    sa, sb = np.deg2rad(selected['obs_lat_lon'])
    sin2 = np.sin((a-sa)/2)**2 + np.cos(a)*np.cos(sa)*np.sin((b-sb)/2)**2
    meters = 2*6371008.8*np.arcsin(np.sqrt(np.clip(sin2, 0, 1)))
    eligible = np.isfinite(meters)
    if not eligible.any():
        raise ValueError('no finite LA positions')
    index = np.flatnonzero(eligible)[np.argmin(meters[eligible])]
    if meters[index] > 3500:
        raise ValueError('no LA nominal center within the predeclared 3.5 km screen')
    m = read.metadata
    # Satpy v0.57.0 arithmetic assumption only; the production UTC stays None.
    epoch = dt.datetime(2000, 1, 1, 12)
    conditional_start = epoch + dt.timedelta(seconds=m['observation_start_time_raw'])
    conditional_end = epoch + dt.timedelta(seconds=m['observation_end_time_raw'])
    decoder_paths = [ROOT / 'oracle/kdm6/obs' / n for n in
                     ('gk2a_l1b_la.py', 'gk2a_l1b.py', 'gk2a_l1b_fd.py', 'obs_ingest.py')]
    result = dict(schema='retained_viirs_ami_nominal_candidate_v1',
        producer_sha256=sha(__file__), candidate_sha256=candidate_sha,
        calibration_sha256=table_sha,
        decoder_sha256={str(p.relative_to(ROOT)): sha(p) for p in decoder_paths},
        selected_viirs_sample=selected,
        ami_row_col_0based=[int(read.pixel_rows[index]), int(read.pixel_cols[index])],
        ami_lat_lon=[float(read.payload.lat[index]), float(read.payload.lon[index])],
        center_distance_from_viirs_m=float(meters[index]),
        channels=list(CLEAN_IR_CHANNELS), bt_K=read.payload.bt[index].tolist(),
        dqf=read.payload.obs_quality[index].tolist(),
        full_slot_pixels=read.payload.n_obs, ami_metadata=m,
        conditional_naive_calendar_interval=[conditional_start.isoformat(), conditional_end.isoformat()],
        time_assumption='Satpy v0.57.0 noon epoch arithmetic; no clock synchronization or pixel UTC certification',
        actual_ami_utc_verified=False, pixel_times_verified=False,
        footprint_or_parallax_matched=False, scientific_qa_approved=False,
        warm_single_layer_verified=False, target_native_state_generated=False,
        kdm_rttov_or_host_run=False)
    if sha(args.candidate) != candidate_sha or sha(table_path) != table_sha:
        raise ValueError('candidate/calibration changed during read')
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('ami_row_col_0based', 'ami_lat_lon',
                     'center_distance_from_viirs_m', 'bt_K', 'dqf', 'conditional_naive_calendar_interval')}, indent=2))


if __name__ == '__main__':
    main()
