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
import argparse
import sys
from pathlib import Path

RD, CP, P0 = 287.04, 1004.5, 1.0e5


def _resolve_frame(dataset, frame: int) -> int:
    """Return a checked non-negative Time index.

    Frame zero remains the compatibility default for this published proxy. A
    caller comparing it with a terminal-frame sibling reader must choose that
    frame explicitly (``frame=-1`` is accepted and recorded as its resolved
    index), rather than relying on an undocumented reader-specific choice.
    """
    import numbers

    if isinstance(frame, bool) or not isinstance(frame, numbers.Integral):
        raise ValueError(f"frame must be an integer Time index, got {frame!r}")
    n = int(dataset["P"].shape[0])
    index = int(frame)
    if index < 0:
        index += n
    if not 0 <= index < n:
        raise ValueError(f"frame {frame} is outside the available Time range 0..{n - 1}")
    return index


def profile(state: Path, frame: int = 0) -> dict:
    """Per-interface over-delivery from a WRF state file.

    ``frame`` is an explicit Time selection. The default ``0`` preserves the
    historical one-frame ``wrfinput`` behavior; use ``-1`` for a terminal
    ``wrfout`` frame and inspect ``frame_index`` in the result.

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
    from g33_number_basis import _physical
    with netCDF4.Dataset(str(state)) as d:
        frame_index = _resolve_frame(d, frame)
        def g(k):
            read = nr.read_numeric(d[k], frame_index)
            if read["nonfinite_count"]:
                raise ValueError(
                    f"{k}: {read['nonfinite_count']} nonfinite cells in density input")
            return read["data"]
        pressure = g("P") + g("PB")
        theta = g("T") + 300.0
        qv = g("QVAPOR")
    _physical("pressure", pressure, positive=True)
    _physical("potential temperature", theta, positive=True)
    _physical("QVAPOR", qv, nonnegative=True)
    temp = _physical("temperature", theta * (pressure / P0) ** (RD / CP), positive=True)
    # Moist density, as the kernel's `den` -- thermodynamic route, see above.
    denominator = _physical("density denominator", RD * temp * (1.0 + 0.608 * qv), positive=True)
    den = _physical("moist density", pressure / denominator, positive=True)
    # WRF k=0 is the BOTTOM, so `den[:-1]` is the LOWER side of each interface
    # and `den[1:]` the upper -- the direction sedimentation moves.
    eps = _physical("density contrast", den[:-1] / den[1:] - 1.0)
    if eps.size == 0:
        raise ValueError("density profile requires at least one interface")
    mid = _physical("interface pressure", 0.5 * (pressure[:-1] + pressure[1:]), positive=True)
    return {"eps": eps, "p_mid": mid, "columns": eps.shape[1] * eps.shape[2],
            "interfaces": int(eps.size),
            "frame_index": frame_index,
            "frame_request": int(frame),
            "frame_policy": "explicit; default frame 0 for compatibility",
            "residual_scope": "density_profile_contrast_proxy",
            "applied_transfers_included": False,
            "clipping_included": False}


def report(state: Path, frame: int = 0) -> dict:
    import numpy as np
    p = profile(state, frame=frame)
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
        "frame_index": p["frame_index"],
        "frame_request": p["frame_request"],
        "frame_policy": p["frame_policy"],
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
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", type=Path)
    ap.add_argument("--frame", type=int, default=0,
                    help="Time frame (default: 0, retained for compatibility; "
                         "use -1 for the terminal frame)")
    args = ap.parse_args(argv)
    print(json.dumps(report(args.state, frame=args.frame), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
