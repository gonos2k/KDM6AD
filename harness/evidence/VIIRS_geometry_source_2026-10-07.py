#!/usr/bin/env python3
"""Actual GMTCO scan/angles and conditional relative-parallax scale.

Uses documented 16 M-band detector rows per scan, not row-linear time fitting.
Parallax is a local tangent sensitivity at hypothetical heights; never applied.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import h5py
import netCDF4
import numpy as np

GEO_SHA = '2a194c417533a1087543cc7a91b1de2a5a6d8d71d1d71e2bfeb1571cc9f8dd0c'
PHASE_SHA = '7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2'
ROW, COL, DETECTORS = 205, 27, 16


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar_attr(obj, name):
    return np.asarray(obj.attrs[name]).reshape(-1)[0].decode()


def ami_tangent(lat_lon, geometry):
    lat, lon = np.deg2rad(lat_lon)
    a, b = geometry['earth_equatorial_radius'], geometry['earth_polar_radius']
    normal = a / np.sqrt(1-(1-b*b/(a*a))*np.sin(lat)**2)
    point = normal*np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon),
                             b*b/(a*a)*np.sin(lat)])
    slon = geometry['sub_longitude']  # radians; height is geocentric distance.
    satellite = geometry['nominal_satellite_height']*np.array([np.cos(slon), np.sin(slon), 0])
    ray = satellite-point
    east = np.array([-np.sin(lon), np.cos(lon), 0])
    north = np.array([-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)])
    up = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    enu = np.array([ray@east, ray@north, ray@up])
    if enu[2] <= 0:
        raise ValueError('satellite below local horizon')
    return enu[:2]/enu[2], float(np.rad2deg(np.arctan2(np.hypot(*enu[:2]), enu[2]))), float(np.rad2deg(np.arctan2(enu[0], enu[1])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geo', type=Path, required=True)
    parser.add_argument('--phase', type=Path, required=True)
    parser.add_argument('--ami-result', type=Path, required=True)
    parser.add_argument('--products-result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output already exists')
    if sha(args.geo) != GEO_SHA or sha(args.phase) != PHASE_SHA:
        raise ValueError('original geolocation/phase hash differs')
    ami_sha = sha(args.ami_result)
    ami = json.loads(args.ami_result.read_text())
    products_sha = sha(args.products_result)
    products = json.loads(args.products_result.read_text())['products']
    with netCDF4.Dataset(args.phase) as d:
        if int(d['StartRow'][:]) != 1 or int(d['StartColumn'][:]) != 1:
            raise ValueError('unexpected EDR subset origins')
        d['Latitude'].set_auto_maskandscale(False)
        d['Longitude'].set_auto_maskandscale(False)
        lat, lon = d['Latitude'][:], d['Longitude'][:]
    with h5py.File(args.geo) as f:
        g = f['All_Data/VIIRS-MOD-GEO-TC_All']
        valid = (lat >= -90) & (lat <= 90) & (lon >= -180) & (lon <= 180)
        if not (np.array_equal(lat[valid], g['Latitude'][:][valid]) and
                np.array_equal(lon[valid], g['Longitude'][:][valid])):
            raise ValueError('valid geolocation arrays do not match the EDR')
        scan, detector = divmod(ROW, DETECTORS)
        nscans = int(g['NumberOfScans'][0])
        if not (0 <= scan < nscans-1):
            raise ValueError('no valid next-scan bracket')
        starts = g['StartTime'][:]
        iet_start, iet_next, iet_mid = (int(g[k][index]) for k, index in
                                      [('StartTime', scan), ('StartTime', scan+1), ('MidTime', scan)])
        if not iet_start <= iet_mid < iet_next:
            raise ValueError('invalid scan timing values')
        aggregate = f['Data_Products/VIIRS-MOD-GEO-TC/VIIRS-MOD-GEO-TC_Aggr']
        granule = f['Data_Products/VIIRS-MOD-GEO-TC/VIIRS-MOD-GEO-TC_Gran_0']
        beginning_date = scalar_attr(aggregate, 'AggregateBeginningDate')
        beginning_time = scalar_attr(aggregate, 'AggregateBeginningTime')
        anchor_iet = int(np.asarray(granule.attrs['N_Beginning_Time_IET']).reshape(-1)[0])
        if anchor_iet != int(starts[0]):
            raise ValueError('beginning IET is not the first scan anchor')
        anchor_utc = dt.datetime.strptime(beginning_date+beginning_time, '%Y%m%d%H%M%S.%fZ').replace(tzinfo=dt.timezone.utc)
        scan_utc = anchor_utc+dt.timedelta(microseconds=iet_start-anchor_iet)
        next_utc = anchor_utc+dt.timedelta(microseconds=iet_next-anchor_iet)
        angles = {k: float(g[k][ROW, COL]) for k in
                  ('SatelliteZenithAngle', 'SatelliteAzimuthAngle', 'SolarZenithAngle', 'SolarAzimuthAngle')}
        qf = dict(scan_QF1=int(g['QF1_SCAN_VIIRSSDRGEO'][scan]),
                  scan_QF2=int(g['QF2_SCAN_VIIRSSDRGEO'][scan]),
                  pixel_QF2=int(g['QF2_VIIRSSDRGEO'][ROW, COL]))
    center = [float(lat[ROW, COL]), float(lon[ROW, COL])]
    if center != ami['selected_viirs_sample']['obs_lat_lon']:
        raise ValueError('AMI candidate differs from the fixed VIIRS sample')
    tangent, zenith, azimuth = ami_tangent(center, ami['ami_metadata']['geos'])
    vz, va = np.deg2rad([angles['SatelliteZenithAngle'], angles['SatelliteAzimuthAngle']])
    if not (0 <= vz < np.pi/2 and -np.pi <= va <= np.pi):
        raise ValueError('invalid selected satellite angles')
    viirs_tangent = np.tan(vz)*np.array([np.sin(va), np.cos(va)])
    relative = tangent-viirs_tangent
    height_fields = products['height']['fields']
    height_center = [height_fields[k]['raw_value'] for k in ('Latitude', 'Longitude')]
    if height_center != center or products['height']['target_index_zero_based'] != [ROW, COL]:
        raise ValueError('cloud-height sample geolocation differs')
    retrieved_height = float(height_fields['CldTopHght']['raw_value'])
    product_pc = [height_fields[k]['raw_value'] for k in ('Latitude_Pc', 'Longitude_Pc')]
    if not (0 <= retrieved_height < 20000 and -90 <= product_pc[0] <= 90 and -180 <= product_pc[1] <= 180):
        raise ValueError('invalid selected cloud-height/parallax fields')
    a0, b0, a1, b1 = np.deg2rad([*center, *product_pc])
    hav = np.sin((a1-a0)/2)**2+np.cos(a0)*np.cos(a1)*np.sin((b1-b0)/2)**2
    pc_distance = float(2*6371008.8*np.arcsin(np.sqrt(np.clip(hav, 0, 1))))
    result = dict(schema='retained_viirs_geometry_v1', producer_sha256=sha(__file__),
        geo_sha256=GEO_SHA, phase_sha256=PHASE_SHA, ami_result_sha256=ami_sha,
        products_result_sha256=products_sha,
        row_col_0based=[ROW, COL], lat_lon=center, valid_edr_geo_arrays_exact=True,
        number_of_actual_scans=nscans, allocated_scan_slots=len(starts),
        scan_index_0based=scan, detector_index_0based=detector, detectors_per_scan=DETECTORS,
        anchor_utc_from_product=anchor_utc.isoformat(), anchor_iet_microseconds=anchor_iet,
        selected_scan_iet_start=iet_start, selected_scan_iet_mid=iet_mid, next_scan_iet_start=iet_next,
        product_anchored_scan_bracket_utc=[scan_utc.isoformat(), next_utc.isoformat()],
        time_scope='IET differences from same granule UTC anchor; scan start/bracket, not pixel acquisition time; no absolute epoch/leap conversion',
        viirs_angles_degrees=angles, geolocation_quality_stored=qf,
        ami_nominal_zenith_degrees=zenith, ami_nominal_azimuth_degrees=azimuth,
        local_tangent_convention='east/north; azimuth toward satellite clockwise from geographic north',
        relative_parallax_tangent_per_height=relative.tolist(),
        hypothetical_relative_parallax_m={str(h):float(np.linalg.norm(relative)*h) for h in (0, 500, 1000, 2000)},
        cloud_height_product_retrieval_m=retrieved_height,
        viirs_product_parallax_corrected_lat_lon=product_pc,
        viirs_product_nominal_to_pc_center_distance_m=pc_distance,
        relative_scale_if_retrieved_height_is_above_surface_m=float(np.linalg.norm(relative)*retrieved_height),
        parallax_scope='flat local tangent scale only; no actual cloud displacement, height datum or footprint correction applied',
        pixel_time_verified=False, ami_clock_verified=False, footprint_or_parallax_matched=False,
        warm_single_layer_verified=False, kdm_rttov_or_host_run=False)
    if (sha(args.geo) != GEO_SHA or sha(args.phase) != PHASE_SHA or
            sha(args.ami_result) != ami_sha or sha(args.products_result) != products_sha):
        raise ValueError('source changed during read')
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
