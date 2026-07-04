#!/usr/bin/env python3
"""Compare step-1 microphysics output: Fortran kdm6 (slot 37) vs PyTorch kdm6ad (slot 137).

Reads four binary dumps written by module_mp_kdm6.F and module_mp_kdm6ad.F:
  kdm6_step1_kdm6_in.bin    (Fortran kdm6 input,  pre-physics)
  kdm6_step1_kdm6_out.bin   (Fortran kdm6 output, post-physics)
  kdm6_step1_kdm6ad_in.bin  (PyTorch kdm6ad input,  pre-physics)
  kdm6_step1_kdm6ad_out.bin (PyTorch kdm6ad output, post-physics)

Each file format:
  6 x int32: ims, ime, kms, kme, jms, jme
  12 x float32 array, shape (ims:ime, kms:kme, jms:jme), in order:
    Q, QC, QR, QI, QS, QG, NC, NR, NI, NN, BG, TH

Compares:
  - input parity (proves IC machinery matches between slot 37 and slot 137)
  - output parity (the actual scheme-level forward consistency metric)
"""
import sys, numpy as np
from pathlib import Path

FIELDS = ['Q', 'QC', 'QR', 'QI', 'QS', 'QG', 'NC', 'NR', 'NI', 'NN', 'BG', 'TH']

def load(path):
    # WRF built with -fconvert=big-endian → use big-endian dtypes.
    with open(path, 'rb') as f:
        hdr = np.fromfile(f, dtype='>i4', count=6)
        ims, ime, kms, kme, jms, jme = hdr.tolist()
        nx = ime - ims + 1
        nk = kme - kms + 1
        ny = jme - jms + 1
        n = nx * nk * ny
        out = {}
        for v in FIELDS:
            arr = np.fromfile(f, dtype='>f4', count=n)
            assert arr.size == n, f'{path}: {v} short read ({arr.size} vs {n})'
            # Fortran column-major (i, k, j) -> reshape order='F'
            out[v] = arr.reshape((nx, nk, ny), order='F').astype(np.float64)
        out['_dims'] = dict(ims=ims, ime=ime, kms=kms, kme=kme, jms=jms, jme=jme)
    return out

def diff_table(a, b, tag):
    print(f'\n## {tag}')
    print(f'{"field":6s} {"max-abs":>12s} {"max-rel":>12s} {"mean(a)":>14s} {"mean(b)":>14s} {"rms-diff":>12s} {"location":>20s}')
    for v in FIELDS:
        x = a[v]; y = b[v]
        d = np.abs(x - y)
        ma = float(d.max())
        denom = np.maximum(np.abs(x), np.abs(y))
        with np.errstate(divide='ignore', invalid='ignore'):
            rel = np.where(denom > 0, d / denom, 0.0)
        mr = float(np.nanmax(rel))
        rms = float(np.sqrt((d**2).mean()))
        idx = np.unravel_index(int(np.argmax(d)), d.shape)
        ma_a = float(np.abs(x).mean())
        ma_b = float(np.abs(y).mean())
        flag = '' if mr < 1e-6 else ('  *' if mr < 1e-3 else '  **' if mr < 1e-1 else '  !')
        print(f'{v:6s} {ma:12.3e} {mr:12.3e} {ma_a:14.5e} {ma_b:14.5e} {rms:12.3e} {str(idx):>20s}{flag}')

def main():
    base = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    f37_in  = load(base / 'kdm6_step1_kdm6_in.bin')
    f37_out = load(base / 'kdm6_step1_kdm6_out.bin')
    f137_in  = load(base / 'kdm6_step1_kdm6ad_in.bin')
    f137_out = load(base / 'kdm6_step1_kdm6ad_out.bin')

    print(f'# Step-1 forward-consistency: Fortran kdm6 (slot 37) vs PyTorch kdm6ad (slot 137)')
    print(f'# dims: {f37_in["_dims"]}')

    diff_table(f37_in, f137_in, 'INPUT  parity (slot 37 vs 137 IC + state passing)')
    diff_table(f37_out, f137_out, 'OUTPUT parity (Fortran kdm6 vs PyTorch kdm6ad after one call)')

    # Net change comparison: how much each scheme changed the state in one call
    delta_f37 = {v: f37_out[v] - f37_in[v] for v in FIELDS}
    delta_f137 = {v: f137_out[v] - f137_in[v] for v in FIELDS}
    diff_table(delta_f37, delta_f137,
               'NET CHANGE parity (Δ_kdm6 vs Δ_kdm6ad per field — true scheme drift)')

if __name__ == '__main__':
    main()
