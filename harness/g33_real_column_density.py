"""The density-profile contrast proxy, over a real atmosphere.

The density-only component of the transport metric can be written:

    R_proxy = sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b

Dividing the proxy term by `den(upper)*delz(upper)*b` gives:

    eps_j = den(lower)/den(upper) - 1

That is a density-profile contrast proxy for the legacy metric. It is a function
of the density profile alone; it does not measure the actual applied inflow or
outflow transfers, clipping, or forecast impact. The proxy magnitude is
measurable without running the model, while the full residual remains a
separate measurement.

What this is NOT: a full residual, a forecast impact, a column-number increase,
or a precipitation change. `eps_j` describes the density contrast at an
interface; the applied transfer and clipping terms are not read here. A column
where nothing sediments has the same `eps` profile as one that rains.

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
    import g33_netcdf_read as nr
    with netCDF4.Dataset(str(state)) as d:
        def g(k):
            read = nr.read_numeric(d[k], 0)
            if read["nonfinite_count"]:
                raise ValueError(
                    f"{k}: {read['nonfinite_count']} nonfinite cells in density input")
            return read["data"]
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
            "interfaces": int(eps.size),
            "residual_scope": "density_profile_contrast_proxy",
            "applied_transfers_included": False,
            "clipping_included": False}


def report(state: Path) -> dict:
    import numpy as np
    p = profile(state)
    eps, mid = p["eps"], p["p_mid"]
    out = {
        # NAMED IN THE OUTPUT, not only in the docstring: a reader
        # comparing this against a number_basis figure must be able to see
        # that the two are on different density authorities.
        "density_authority": "thermodynamic p/(Rd T (1+0.608 qv))",
        "residual_scope": p["residual_scope"],
        "applied_transfers_included": p["applied_transfers_included"],
        "clipping_included": p["clipping_included"],
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
