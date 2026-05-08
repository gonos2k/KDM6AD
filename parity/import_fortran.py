"""Convert a Fortran-side capture (two unformatted binaries) into a golden
vector directory consumable by `parity/test_parity.py` and `run_parity.py`.

Pairs with `parity/snippets/capture.F90.txt`. Endianness is host-native;
both Fortran and the macOS/Linux x86/arm64 hosts we run on are
little-endian, so `<f8` is fine. If you ever capture on a big-endian host
(unlikely), swap the dtype here.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import struct
import sys
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS))

from _schema import StateFields, ForcingFields, save as save_golden  # noqa: E402


_DTYPE = np.dtype("<f8")  # 64-bit float, little-endian


def _read_record(stream) -> bytes:
    """Read one Fortran `access='stream'` write — caller knows length."""
    raise RuntimeError("stream-mode binaries have no record markers — "
                       "use _read_array(stream, shape, dtype) instead")


def _read_array(stream, shape, dtype=_DTYPE) -> np.ndarray:
    nbytes = int(np.prod(shape)) * dtype.itemsize
    buf = stream.read(nbytes)
    if len(buf) != nbytes:
        raise EOFError(f"expected {nbytes} bytes, got {len(buf)}")
    # Fortran column-major → numpy row-major. Reverse shape, transpose.
    arr = np.frombuffer(buf, dtype=dtype).reshape(shape[::-1])
    return np.ascontiguousarray(arr.T)


def _read_scalar(stream, dtype=_DTYPE) -> float:
    nbytes = dtype.itemsize
    buf = stream.read(nbytes)
    if len(buf) != nbytes:
        raise EOFError(f"expected scalar of {nbytes} bytes, got {len(buf)}")
    fmt = "<d" if dtype == _DTYPE else "<f"
    return struct.unpack(fmt, buf)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", type=Path,
                        help="kdm6_parity_in.bin from capture.F90 snippet")
    parser.add_argument("outfile", type=Path,
                        help="kdm6_parity_out.bin from capture.F90 snippet")
    parser.add_argument("--out", type=Path, required=True,
                        help="Destination golden-vector directory")
    parser.add_argument("--test-name", default="unnamed",
                        help="Short label, stored in metadata")
    parser.add_argument("--kim-version", default="unknown",
                        help="KIM-meso build identifier, stored in metadata")
    parser.add_argument("--fortran-commit", default="unknown",
                        help="module_mp_kdm6.F commit hash, stored in metadata")
    args = parser.parse_args()

    # ---- input file --------------------------------------------------------
    with args.infile.open("rb") as f:
        # First record: B, K (2 × int32)
        header = f.read(8)
        B, K = struct.unpack("<ii", header)
        shape = (B, K)
        ms_shape = shape  # ims:ime equals its:ite for our captures

        t   = _read_array(f, shape)
        qv  = _read_array(f, shape)
        qc  = _read_array(f, shape)
        qi  = _read_array(f, shape)
        qr  = _read_array(f, shape)
        qs  = _read_array(f, shape)
        qg  = _read_array(f, shape)
        nc  = _read_array(f, shape)
        ni  = _read_array(f, shape)
        nr  = _read_array(f, shape)
        brs = _read_array(f, shape)
        p    = _read_array(f, ms_shape)
        den  = _read_array(f, ms_shape)
        delz = _read_array(f, ms_shape)
        dend = _read_array(f, shape)
        dtcld      = _read_scalar(f)
        ccn0       = _read_scalar(f)
        qmin       = _read_scalar(f)
        ncmin_land = _read_scalar(f)
        ncmin_sea  = _read_scalar(f)

    state_in = StateFields(
        qv=qv, qc=qc, qr=qr, qs=qs, qg=qg, qi=qi,
        nc=nc, nr=nr, ni=ni, brs=brs, t=t,
    )
    forcing = ForcingFields(p=p, den=den, delz=delz, dend=dend)
    scalars = {
        "dtcld": dtcld,
        "ccn0": ccn0,
        "qmin": qmin,
        "ncmin_land": ncmin_land,
        "ncmin_sea": ncmin_sea,
    }

    # ---- output file -------------------------------------------------------
    with args.outfile.open("rb") as f:
        t_out   = _read_array(f, shape)
        qv_out  = _read_array(f, shape)
        qc_out  = _read_array(f, shape)
        qi_out  = _read_array(f, shape)
        qr_out  = _read_array(f, shape)
        qs_out  = _read_array(f, shape)
        qg_out  = _read_array(f, shape)
        nc_out  = _read_array(f, shape)
        ni_out  = _read_array(f, shape)
        nr_out  = _read_array(f, shape)
        brs_out = _read_array(f, shape)
        rainncv    = _read_array(f, (B,))
        snowncv    = _read_array(f, (B,))
        graupelncv = _read_array(f, (B,))

    state_out = StateFields(
        qv=qv_out, qc=qc_out, qr=qr_out, qs=qs_out, qg=qg_out, qi=qi_out,
        nc=nc_out, nr=nr_out, ni=ni_out, brs=brs_out, t=t_out,
    )
    surface_accum = {
        "rain_mm": rainncv.tolist(),
        "snow_mm": snowncv.tolist(),
        "graupel_mm": graupelncv.tolist(),
    }
    metadata = {
        "test_name": args.test_name,
        "kim_version": args.kim_version,
        "fortran_commit": args.fortran_commit,
        "capture_date": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "shape": [B, K],
    }

    save_golden(
        args.out,
        state_in=state_in, forcing=forcing, scalars=scalars,
        state_out=state_out, surface_accum=surface_accum, metadata=metadata,
    )
    print(f"wrote {args.out}/  (B={B}, K={K})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
