"""Analytic pure-absorption check of PyDISORT top-down ordering and thermal BCs."""

import argparse
import pydisort
import ctypes
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from pydisort import Disort, DisortOptions

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
OUT = parser.parse_args().output
libpath = next(
    iter(sorted((Path(pydisort.__file__).parent / "lib").glob("libdisort_release.*")))
)
lib = ctypes.CDLL(str(libpath))
planck_band = lib.c_planck_func2
planck_band.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
planck_band.restype = ctypes.c_double
lo, hi = 900.0, 901.0
scale = 0.001  # mW m^-2 sr^-1 cm -> W m^-2 sr^-1 over 1 cm^-1


def equivalent_temperature(target):
    if target <= 0.0:
        return 0.0
    left, right = 0.0, 2000.0
    goal = target * scale
    for _ in range(100):
        mid = 0.5 * (left + right)
        if planck_band(lo, hi, mid) < goal:
            left = mid
        else:
            right = mid
    return 0.5 * (left + right)


def integrate(func, a, b):
    x, w = np.polynomial.legendre.leggauss(256)
    t = 0.5 * (b - a) * x + 0.5 * (b + a)
    return 0.5 * (b - a) * float(np.dot(w, func(t)))


tau_layers = np.array([0.3, 0.7], dtype=np.float64)  # top-to-bottom
cum = np.concatenate(([0.0], np.cumsum(tau_layers)))
source = np.array(
    [10.0, 35.0, 75.0], dtype=np.float64
)  # top/mid/bottom; linear in tau per layer
surface = 90.0
cosmic = 2.4
mu = 0.65

op = (
    DisortOptions()
    .flags("lamber,planck,usrtau,usrang,quiet")
    .nwave(1)
    .ncol(1)
    .upward(0)
    .user_tau([0.0, 0.3, 1.0])
    .user_mu([-mu, mu])
    .user_phi([0.0])
    .wave_lower([lo])
    .wave_upper([hi])
)
op.ds().nlyr = 2
op.ds().nstr = 4
op.ds().nmom = 4
op.ds().nphase = 4
disort = Disort(op)
prop = torch.zeros((1, 1, 2, 2), dtype=torch.float64)
prop[0, 0, :, 0] = torch.as_tensor(tau_layers)
# No scattering: PMOM slots absent and SSA is exactly zero.
T = lambda x: torch.tensor(x, dtype=torch.float64)
flux = disort.forward(
    prop,
    temf=T([[equivalent_temperature(x) for x in source]]),
    btemp=T([equivalent_temperature(surface)]),
    ttemp=T([equivalent_temperature(source[0])]),
    albedo=T([[0.0]]),
    temis=T([[1.0]]),
    fisot=T([[cosmic * scale]]),
    fbeam=T([[0.0]]),
    fluor=T([[0.0]]),
    umu0=T([1.0]),
    phi0=T([0.0]),
)
rads = disort.gather_rad()[0, 0, 0]  # [top,bottom][+mu,-mu]
up_top = float(rads[0, 1]) / scale
# piecewise-linear source in cumulative top-down tau; black Lambert surface source at bottom
B = lambda t: np.interp(t, cum, source)
up_ref = surface * np.exp(-cum[-1] / mu) + sum(
    integrate(lambda t: B(t) * np.exp(-t / mu) / mu, cum[k], cum[k + 1])
    for k in range(len(tau_layers))
)
# Downward surface ray: top input is cosmic + top-boundary Planck; internal source adds on the way down.
dn_surface = float(rads[-1, 0]) / scale
dn_ref = (cosmic + source[0]) * np.exp(-cum[-1] / mu) + sum(
    integrate(lambda t: B(t) * np.exp(-(cum[-1] - t) / mu) / mu, cum[k], cum[k + 1])
    for k in range(len(tau_layers))
)
result = {
    "status": "PASS"
    if abs(up_top - up_ref) < 1e-10 and abs(dn_surface - dn_ref) < 1e-10
    else "FAIL",
    "disort_source": "pydisort 1.8.13 / bundled cdisort 2.1.3",
    "libdisort_sha256": hashlib.sha256(libpath.read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "upward_option": 0,
    "layer_order": "top-down; TAUC(0)=0 and DISORT2.doc says layers are numbered from top boundary down",
    "mu_up": mu,
    "tau_layers_top_down": tau_layers.tolist(),
    "source_radiance_level_values": source.tolist(),
    "surface_radiance": surface,
    "cosmic_top_radiance": cosmic,
    "all_levels_user_mu_negative_positive": rads.tolist(),
    "top_up_disort": up_top,
    "top_up_formal_solution": up_ref,
    "top_up_abs_error": abs(up_top - up_ref),
    "bottom_down_disort": dn_surface,
    "bottom_down_formal_solution": dn_ref,
    "bottom_down_abs_error": abs(dn_surface - dn_ref),
    "interpretation": "upwelling solution is independent of top incoming BC for a black nonreflecting lower surface; downwelling check verifies cosmic + top Planck BC mapping",
}
OUT.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
if result["status"] != "PASS":
    raise SystemExit(1)
