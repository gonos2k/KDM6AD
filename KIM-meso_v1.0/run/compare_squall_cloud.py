#!/usr/bin/env python3
"""Per-frame cloud-variable parity diff for slot-37 vs slot-137 squall2d_x runs.

Focus on QC, QR, QI, QS, QG, QNCCN — the variables that exercise
autoconversion / accretion / sedimentation paths once convection forms.

Usage:
  python3 compare_squall_cloud.py wrfout.37.squall.30min.nc wrfout.137.squall.30min.nc
"""
import sys, numpy as np, netCDF4 as nc

CLOUD_VARS = ['QCLOUD', 'QRAIN', 'QICE', 'QSNOW', 'QGRAUP', 'QNCCN', 'QNCLOUD', 'QNRAIN', 'QNICE']

def safe_get(d, name):
    """Try a few WRFOUT name variants for the same physical variable."""
    aliases = {
        'QCLOUD': ['QCLOUD', 'QC'],
        'QRAIN': ['QRAIN', 'QR'],
        'QICE': ['QICE', 'QI'],
        'QSNOW': ['QSNOW', 'QS'],
        'QGRAUP': ['QGRAUP', 'QG'],
        'QNCCN': ['QNCCN', 'QNN'],
        'QNCLOUD': ['QNCLOUD', 'QNC'],
        'QNRAIN': ['QNRAIN', 'QNR'],
        'QNICE': ['QNICE', 'QNI'],
    }
    for n in aliases.get(name, [name]):
        if n in d.variables:
            return d.variables[n], n
    return None, name

def main():
    p37  = sys.argv[1] if len(sys.argv) > 1 else 'wrfout.37.squall.30min.nc'
    p137 = sys.argv[2] if len(sys.argv) > 2 else 'wrfout.137.squall.30min.nc'
    a = nc.Dataset(p37, 'r')
    b = nc.Dataset(p137, 'r')
    n = min(a.dimensions['Time'].size, b.dimensions['Time'].size)
    print(f'# {p37} vs {p137}, {n} common frames')

    for v in CLOUD_VARS:
        va, na = safe_get(a, v)
        vb, nb = safe_get(b, v)
        if va is None or vb is None:
            print(f'\n## {v}: missing in one dataset (a:{na} b:{nb}) — skip')
            continue
        print(f'\n## {v} ({na} / {nb})')
        print(f'{"frame":>5s} {"max(a)":>12s} {"max(b)":>12s} {"mean(a)":>12s} {"mean(b)":>12s} {"max-abs":>12s} {"max-rel":>12s}')
        for i in range(n):
            xa = np.asarray(va[i], dtype=np.float64)
            xb = np.asarray(vb[i], dtype=np.float64)
            d = np.abs(xa - xb)
            ma = float(d.max()); maxa = float(np.abs(xa).max()); maxb = float(np.abs(xb).max())
            denom = np.maximum(np.abs(xa), np.abs(xb))
            with np.errstate(divide='ignore', invalid='ignore'):
                rel = np.where(denom > 0, d/denom, 0.0)
            mr = float(np.nanmax(rel))
            mna = float(np.abs(xa).mean()); mnb = float(np.abs(xb).mean())
            flag = ''
            if maxa > 0 or maxb > 0:
                if mr > 1e-2: flag = '  *'
                if mr > 0.5: flag = '  **'
            print(f'{i:5d} {maxa:12.4e} {maxb:12.4e} {mna:12.4e} {mnb:12.4e} {ma:12.4e} {mr:12.4e}{flag}')

if __name__ == '__main__':
    main()
