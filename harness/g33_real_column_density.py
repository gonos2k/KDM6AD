"""The number-transport defect's COEFFICIENT, over a real atmosphere.

`g33_number_transport` establishes the residual as an identity:

    R_N = sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b

Divide the interface term by what SHOULD have arrived, `den(upper)*delz(upper)*b`,
and the transfer drops out:

    eps_j = den(lower)/den(upper) - 1

That is the fraction of number the legacy metric over-delivers across one
interface, and it is a function of the DENSITY PROFILE ALONE. So the magnitude
this defect can reach in a real atmosphere is measurable without running the
model, without the corrected arm, and without touching the frozen kernel --
which is what makes it available while the freeze-lift for that arm is a
decision the owner has not taken.

What this is NOT: a forecast impact, a column-number increase, or a
precipitation change. `eps_j` bounds the per-interface error of the transport
metric; how much number actually crosses each interface is `b`, which this
does not measure. A column where nothing sediments has the same `eps` profile
as one that rains.

Density here is MOIST, matching the kernel's `den` (`dend(i,k) = den(i,k)`,
F:870) -- so this is the operator's own measure, not the dry-air one the
physical column number would use. The basis offset is a separate question
(`FINDING_number_mass_basis_v1`).
"""
import sys
from pathlib import Path

RD, CP, P0 = 287.04, 1004.5, 1.0e5


def profile(state: Path) -> dict:
    """Per-interface over-delivery from a WRF state file.

    WHICH DENSITY THIS IS, named rather than assumed. `den` here is the
    THERMODYNAMIC estimate `p / (Rd T (1 + 0.608 qv))` -- pressure, temperature
    and a linearised virtual temperature. `g33_number_basis` uses a different
    authority for the same physical question: WRF's own hydrostatic relation,
    `rho_d dz = mu_d |d(eta)| / g`, which assumes no thermodynamics at all.

    They are not interchangeable. Measured against each other on the real 5 km
    state, the thermodynamic routes differ from the canonical one by a median
    2.3e-03 and by up to 31 %, which is about 2500 times the difference BETWEEN
    the two thermodynamic routes. So the choice that matters is
    thermodynamic-versus-canonical.

    This module keeps the thermodynamic route because its published statistics
    were taken with it, and switching authorities silently would move numbers
    that are already cited. The output says which one it is, so a reader does
    not have to infer it, and `g33_number_basis.profile(..., basis='canonical')`
    is the one to call when the model's own layer mass is the question.
    """
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(state))
    import g33_netcdf_read as nr
    g = lambda k: nr.read_numeric(d[k], 0)["data"]   # noqa: E731  f64, mask refused
    pressure = g("P") + g("PB")
    theta = g("T") + 300.0
    qv = g("QVAPOR")
    temp = theta * (pressure / P0) ** (RD / CP)
    # Moist density, as the kernel's `den` -- thermodynamic route, see above.
    den = pressure / (RD * temp * (1.0 + 0.608 * qv))
    # WRF k=0 is the BOTTOM, so `den[:-1]` is the LOWER side of each interface
    # and `den[1:]` the upper -- the direction sedimentation moves.
    eps = den[:-1] / den[1:] - 1.0
    mid = 0.5 * (pressure[:-1] + pressure[1:])
    return {"eps": eps, "p_mid": mid, "columns": eps.shape[1] * eps.shape[2],
            "interfaces": int(eps.size)}


def report(state: Path) -> dict:
    import numpy as np
    p = profile(state)
    eps, mid = p["eps"], p["p_mid"]
    out = {
        # NAMED IN THE OUTPUT, not only in the docstring: a reader
        # comparing this against a number_basis figure must be able to see
        # that the two are on different density authorities.
        "density_authority": "thermodynamic p/(Rd T (1+0.608 qv))",
        "state": str(state),
        "columns": p["columns"],
        "interfaces": p["interfaces"],
        "eps_median": float(np.median(eps)),
        "eps_mean": float(eps.mean()),
        "eps_p90": float(np.percentile(eps, 90)),
        "eps_max": float(eps.max()),
        "eps_negative_fraction": float((eps < 0).mean()),
        "by_level": [{"k": int(k),
                      "p_mid_hpa": float(np.median(mid[k]) / 100.0),
                      "eps_median": float(np.median(eps[k]))}
                     for k in range(eps.shape[0])],
    }
    return out


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    import json
    print(json.dumps(report(Path(argv[0])), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
