"""Fortran-faithful f32-stepwise runtime constants (kdm6init, module_mp_kdm6.F:3100-3300).

Mirror of libtorch/include/kdm6/fconst.h — see that header for the full
rationale (double-precomputed DSD constants differ 1 ULP from gfortran's REAL(4)
stepwise evaluation; measured as the step-45 DSD-snap divergence seed). Each
value is the exact float32 result held as a Python float (double).
"""
import math
import struct

def _f32(v: float) -> float:
    return struct.unpack('f', struct.pack('f', v))[0]

def gammln_f(x: float) -> float:
    """Exact port of Fortran GAMMLN (double internals, float32 return)."""
    STP = 2.5066282746310005
    COF = (76.18009172947146, -86.50532032941677, 24.01409824083091,
           -1.231739572450155, .1208650973866179e-2, -.5395239384953e-5)
    xx = _f32(x); y = xx
    tmp = xx + 5.5
    tmp = (xx + 0.5) * math.log(tmp) - tmp
    ser = 1.000000000190015
    for c in COF:
        y += 1.0
        ser += c / y
    return _f32(tmp + math.log(STP * ser / xx))

def rgmma_f(x: float) -> float:
    """Fortran rgmma = EXP(GAMMLN(x)) in REAL(4): f32 exp of f32 gammln."""
    return _f32(math.exp(gammln_f(x)))

_DENR = _f32(1000.0); _DENI = _f32(500.0)
_MUC = _f32(2.0); _MUR = _f32(1.0); _MUI = _f32(0.0)
_DMC = _f32(3.0); _DMR = _f32(3.0); _DMI = _f32(3.0)

PI    = _f32(4.0 * _f32(math.atan(1.0)))
CMC   = _f32(_f32(PI * _DENR) / 6.0)
CMR   = CMC
CMI   = _f32(_f32(PI * _DENI) / 6.0)
G1PMC = rgmma_f(_f32(1.0 + _f32(1.0 / _f32(_MUC + 1.0))))
G3PMC = rgmma_f(_f32(1.0 + _f32(3.0 / _f32(_MUC + 1.0))))
G4PMC = rgmma_f(_f32(1.0 + _f32(4.0 / _f32(_MUC + 1.0))))
G6PMC = rgmma_f(_f32(1.0 + _f32(6.0 / _f32(_MUC + 1.0))))
G1PMR = rgmma_f(_f32(1.0 + _MUR))
G2PMR = rgmma_f(_f32(2.0 + _MUR))
G4PMR = rgmma_f(_f32(4.0 + _MUR))
G7PMR = rgmma_f(_f32(7.0 + _MUR))
G1PDRMR = rgmma_f(_f32(_f32(1.0 + _DMR) + _MUR))
G1PMI = rgmma_f(_f32(1.0 + _MUI))
G4PMI = rgmma_f(_f32(4.0 + _MUI))
G1PDIMI = rgmma_f(_f32(_f32(1.0 + _DMI) + _MUI))
G1P2DCOMUC1 = rgmma_f(_f32(1.0 + _f32(_f32(2.0 * _DMC) / _f32(_MUC + 1.0))))  # Γ(3) — D3 pfrzdtc (F:3207)
G1PDCOMUC1  = rgmma_f(_f32(1.0 + _f32(_DMC / _f32(_MUC + 1.0))))              # Γ(2) — D3 nfrzdtc (F:3208)
PIDNC = _f32(CMC * rgmma_f(_f32(1.0 + _f32(_DMC / _f32(_MUC + 1.0)))))
PIDNR = _f32(_f32(CMR * G1PDRMR) / G1PMR)
PIDNI = _f32(_f32(CMI * G1PDIMI) / G1PMI)
# snow pidn0s = cms*n0s*g1pdsms/g1pms (REAL, f32-stepwise; kdm6init F:3326). dens=100 (snow).
# double-then-round differs 1 ULP (gfortran 4E15CD86 vs double 4E15CD85) — §44 f32-stepwise.
_DENS = _f32(100.0); _N0S = _f32(2.0e6); _MUS = _f32(0.0); _DMS = _f32(3.0)
CMS    = _f32(_f32(PI * _DENS) / 6.0)
G1PMS  = rgmma_f(_f32(1.0 + _MUS))
G1PDSMS = rgmma_f(_f32(_f32(1.0 + _DMS) + _MUS))
PIDN0S = _f32(_f32(_f32(CMS * _N0S) * G1PDSMS) / G1PMS)
# ele2 = 4.*pi*1.38E-23/(6.*pi*Rcn) — Fortran F:1521, REAL(4) stepwise (D2 contact
# freezing aerosol diffusivity; loop-invariant). C++ fconst.h mirror (step-67 seed).
_RCN = _f32(0.1e-6)
ELE2 = _f32(_f32(_f32(4.0 * PI) * _f32(1.38e-23)) / _f32(_f32(6.0 * PI) * _RCN))


# libm float32 powf (gfortran REAL**REAL) — for f32-stepwise init constants
# (rslope*max family, kdm6init F:3297-3340). ctypes, init-time only.
import ctypes as _ctypes
_libm = _ctypes.CDLL(None)
_libm.powf.restype = _ctypes.c_float
_libm.powf.argtypes = [_ctypes.c_float, _ctypes.c_float]

def powf(x: float, y: float) -> float:
    return float(_libm.powf(_f32(x), _f32(y)))
