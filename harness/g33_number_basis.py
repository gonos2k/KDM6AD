"""What Arm N still leaves against the PHYSICAL number measure.

Arm N gives the interface number transfer the air-mass ratio, and the archive
shows its residual collapsing to roundoff. That closes the OPERATOR's own
ledger: `dend(i,k) = den(i,k)` (F:870) is MOIST density. The physical column
number is `sum rho_d*dz*nr`, because `nr` is per kg of DRY air (G33-BASIS-006),
so a gap remains and its size is what this measures.

Per interface, divide what arrives by what should arrive; the transfer `b`
drops out and a COEFFICIENT is left that depends on the profile alone. With
`A` the density the kernel weights by and `B` the measure the ledger is taken
in,

    eps = [B(lower)/B(upper)] * [A(upper)/A(lower)] - 1

Three readings follow, and the third is the one that was not available before:

    legacy, operator measure   A = 1     B = den     eps = den(lo)/den(up) - 1
    legacy, physical measure   A = 1     B = den_d
    ARM N,  physical measure   A = den   B = den_d   eps = (1+qv_up)/(1+qv_lo) - 1

with `den_d = den/(1+qv)`. The third is PURELY THE MOISTURE JUMP: Arm N's
remaining physical defect does not depend on the density profile at all.

And the three compose exactly, not approximately:

    1 + eps_legacy_dry = (1 + eps_legacy_moist) * (1 + eps_armn_dry)

so the legacy defect against the physical measure FACTORISES into a density
term and a moisture term, and Arm N removes exactly the first one. That is the
statement `G33-BASIS-002` was holding open a decision about, now with a size.

WHY THIS NEEDS A REAL ATMOSPHERE. Every stream in the archive that carries qv
carries it UNIFORM in the column -- measured, in-column spread exactly 0.0
across `armn`, `f64` and `migrate`. Under a uniform profile the moisture term
is identically 1 and the two ledgers differ by a constant per column, which
cancels out of every ratio. So no fixture published so far can distinguish the
bases, and this is not a defect of Arm N's evidence: it is the reason the
question stayed open. It takes a moisture GRADIENT, which is what a real state
has.

What this is NOT: a forecast impact, a column-number change, or a precipitation
difference. `eps` is the per-interface coefficient of the transport metric; how
much number actually crosses is `b`, which this does not measure.
"""
import sys
from pathlib import Path

RD, CP, P0, G = 287.04, 1004.5, 1.0e5, 9.81
#: Rd/Rv. The dry-density relation for a MIXING ratio is
#: `rho_d = p / (Rd T (1 + qv/EPS))`; the published statistics used
#: `rho_m / (1 + qv)` with a virtual-temperature linearisation instead.
EPS = 0.622


def _dry_density(d, p, temp, qv, basis: str):
    """Dry-air density by one of three routes, named.

    `canonical` is the model's OWN: WRF's hydrostatic relation is
    `d(phi)/d(eta) = -mu_d * alpha_d`, so `rho_d * dz = mu_d |d(eta)| / g`
    exactly in its discretisation. Nothing thermodynamic is assumed.

    The other two are estimates from `p`, `T` and `qv`. Measured against the
    canonical route on the real 5 km state they differ by a median 2.3e-03 and
    up to 31 % -- which is about 2500 times the difference BETWEEN them
    (median 9.5e-07). So the choice that matters is thermodynamic-vs-canonical,
    not exact-vs-approximate.

    It does not move the published statistic: the Arm N residual fraction where
    rain number is runs 1.9422 % (approx), 1.9420 % (exact) and 1.9169 %
    (canonical). `eps_armn` depends on `qv` alone and is route-free.
    """
    import numpy as np
    if basis == "canonical":
        mu = np.asarray(d["MU"][-1], dtype="float64") + \
            np.asarray(d["MUB"][-1], dtype="float64")
        dnw = np.asarray(d["DNW"][-1], dtype="float64")
        ph = np.asarray(d["PH"][-1], dtype="float64") + \
            np.asarray(d["PHB"][-1], dtype="float64")
        dz = np.diff(ph, axis=0) / G
        return (mu[None, :, :] * np.abs(dnw)[:, None, None]) / G / dz
    if basis == "exact":
        return p / (RD * temp * (1.0 + qv / EPS))
    if basis == "approx":
        return (p / (RD * temp * (1.0 + 0.608 * qv))) / (1.0 + qv)
    raise ValueError(f"basis must be canonical|exact|approx, got {basis!r}")


def profile(state: Path, basis: str = "canonical") -> dict:
    """The three per-interface coefficients from a WRF state file.

    `basis` selects the dry-density route; see `_dry_density`. The default is
    the model's own `mu_d`/`d(eta)`, which assumes no thermodynamics at all.
    """
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(state))
    frame = -1 if d["P"].shape[0] > 1 else 0
    g = lambda k: np.asarray(d[k][frame], dtype="float64")   # noqa: E731
    pressure = g("P") + g("PB")
    theta = g("T") + 300.0
    qv = g("QVAPOR")
    temp = theta * (pressure / P0) ** (RD / CP)
    if basis == "canonical" and not all(v in d.variables
                                        for v in ("MU", "MUB", "DNW", "PH")):
        raise KeyError(
            "this state carries no MU/MUB/DNW/PH, so the model's own dry-air "
            "layer mass is not available; pass basis='exact' to estimate it")
    den_d = _dry_density(d, pressure, temp, qv, basis)
    # Total moist density, which is the kernel's `den`.
    den = den_d * (1.0 + qv)
    # WRF k=0 is the BOTTOM, so [:-1] is the LOWER side of each interface and
    # [1:] the upper -- the direction sedimentation moves.
    lo, up = slice(None, -1), slice(1, None)
    return {
        # what departs the upper cell, per unit mixing ratio
        "dry_layer_mass_upper": den_d[up] * (np.diff(
            (np.asarray(d["PH"][frame], dtype="float64")
             + np.asarray(d["PHB"][frame], dtype="float64")), axis=0) / G)[up]
        if "PH" in d.variables else den_d[up],
        "legacy_moist": den[lo] / den[up] - 1.0,
        "legacy_dry": den_d[lo] / den_d[up] - 1.0,
        "armn_dry": (1.0 + qv[up]) / (1.0 + qv[lo]) - 1.0,
        "qv_lower": qv[lo],
        "p_mid": 0.5 * (pressure[lo] + pressure[up]),
    }


def where_the_number_is(state: Path, field: str = "QNRAIN",
                        basis: str = "canonical") -> dict:
    """The same coefficients, restricted to interfaces that actually carry number.

    `report()` summarises every interface in the domain, and most of them hold
    no rain number at all -- a coefficient there is a property of the air, not
    of anything being transported. The defect only reaches a forecast where
    there is something to transport, so this weights the same profile by where
    the number is.

    TWO POPULATIONS, because the first published one was the wrong question.
    "Both cells carry the field" is the interior of the population, and
    sedimentation moves number DOWNWARD from the upper cell -- so an interface
    whose upper cell is loaded and whose lower cell is empty is transport-active
    and was excluded. Measured, that is 23 492 interfaces against 13 611: the
    published population was 42 % of the transport-active one.

    AND A RATIO OF MEDIANS IS NOT THE COLUMN DEFECT. The residual is
    `sum_j F_j eps_j`, so the coefficients are weighted by how much number
    actually crosses.

    WHAT IS WEIGHTED HERE IS NOT THAT. `m_d(upper) * n(upper)` is the upper
    cell's number INVENTORY, and the transferred amount is `m_d * dn` with `dn`
    set by fall speed, sub-stepping and the interface cap. A state file records
    the first and not the second, so this is an
    `upper_inventory_weighted` aggregate and is named so. The actual
    flux-weighted number needs the kernel's own per-interface transfers. A
    replay gets closer -- `from_stream` weights by the transfers RECOVERED from
    the endpoints -- but the kernel emits only the surface one, so even that is
    `recovered_transfer_weighted` and not a measured interface flux.

    "Transport-active" is likewise the population that COULD transport: `n > 0`
    in the upper cell does not mean the timestep moved any of it.

    Measured on the 20 s `mp37` frame, none of this moves the answer: median
    1.92 % on the occupied-pair population, 2.02 % on the upper-populated one,
    and 1.98 % upper-inventory-weighted on either.
    """
    import netCDF4
    import numpy as np
    p = profile(state, basis)
    d = netCDF4.Dataset(str(state))
    n = np.asarray(d[field][-1] if d[field].shape[0] > 1 else d[field][0],
                   dtype="float64")
    lo, up = slice(None, -1), slice(1, None)
    pops = {"occupied_pair": (n[lo] > 0) & (n[up] > 0),
            # NOT "transport_active": `n > 0` above the interface says the
            # number is there to be moved, not that the step moved it.
            "upper_populated": n[up] > 0}
    live = pops["occupied_pair"]
    out = {"state": str(state), "field": field, "basis": basis,
           "interfaces": int(live.size),
           "carrying": int(live.sum()),
           "carrying_fraction": float(live.mean()),
           "upper_populated": int(pops["upper_populated"].sum())}
    if not live.any():
        out["empty"] = True
        return out
    # The upper cell's number INVENTORY. Not `F_j`: that is `m_d * dn` and `dn`
    # is what the kernel actually moved, which a state file does not record.
    inventory = p["dry_layer_mass_upper"] * n[up]
    out["populations"] = {}
    for nm, m in pops.items():
        if not m.any():
            continue
        f = np.abs(p["armn_dry"][m]) / np.maximum(np.abs(p["legacy_dry"][m]),
                                                  1e-300)
        w = inventory[m]
        num = abs(float((w * p["armn_dry"][m]).sum()))
        den = abs(float((w * p["legacy_dry"][m]).sum()))
        out["populations"][nm] = {
            "interfaces": int(m.sum()),
            "median": float(np.median(f)),
            "p90": float(np.percentile(f, 90)),
            "upper_inventory_weighted": num / den if den else None}
    for key in ("legacy_moist", "legacy_dry", "armn_dry"):
        e = p[key][live]
        out[key] = {"median": float(np.median(e)), "mean": float(e.mean()),
                    "abs_p90": float(np.percentile(np.abs(e), 90)),
                    "abs_max": float(np.abs(e).max())}
    frac = np.abs(p["armn_dry"][live]) / np.maximum(
        np.abs(p["legacy_dry"][live]), 1e-300)
    out["armn_residual_fraction"] = {
        "median": float(np.median(frac)), "p90": float(np.percentile(frac, 90))}
    return out


def report(state: Path, basis: str = "canonical") -> dict:
    import numpy as np
    p = profile(state, basis)
    out = {"state": str(state), "basis": basis,
           "interfaces": int(p["armn_dry"].size)}
    for key in ("legacy_moist", "legacy_dry", "armn_dry"):
        e = p[key]
        out[key] = {"median": float(np.median(e)),
                    "mean": float(e.mean()),
                    "abs_p90": float(np.percentile(np.abs(e), 90)),
                    "abs_max": float(np.abs(e).max())}
    # What Arm N leaves, as a fraction of what legacy had -- the number the
    # basis question is really asking for. Taken per interface and then
    # summarised, NOT as a ratio of the summaries: a ratio of medians is not
    # the median of ratios, and the difference is where a defect hides.
    keep = np.abs(p["legacy_dry"]) > 0.0
    frac = np.abs(p["armn_dry"][keep]) / np.abs(p["legacy_dry"][keep])
    tail = frac > 0.10
    out["armn_residual_fraction"] = {
        "median": float(np.median(frac)),
        "p90": float(np.percentile(frac, 90)),
        "max": float(frac.max()),
        "over_10_percent": float(tail.mean()),
        # A RATIO WITHOUT ITS SCALE IS NOT A RESULT. The fraction blows up at a
        # near-isopycnal interface, where legacy had almost no defect to remove
        # -- a large share of nearly nothing. So the tail is reported with the
        # ABSOLUTE size of what Arm N leaves there and of what legacy had, and
        # the reader decides whether it matters instead of being handed a
        # maximum that is an artefact of the denominator.
        "tail_abs_armn_median": float(np.median(np.abs(p["armn_dry"][keep][tail]))
                                      ) if tail.any() else 0.0,
        "tail_abs_legacy_median": float(np.median(np.abs(p["legacy_dry"][keep][tail]))
                                        ) if tail.any() else 0.0,
        "interfaces": int(frac.size)}
    # The exact composition, verified on the data rather than asserted.
    err = np.abs((1 + p["legacy_moist"]) * (1 + p["armn_dry"])
                 - (1 + p["legacy_dry"]))
    out["composition_max_abs_error"] = float(err.max())
    out["by_level"] = [
        {"k": int(k),
         "p_mid_hpa": float(np.median(p["p_mid"][k]) / 100.0),
         "qv_median": float(np.median(p["qv_lower"][k])),
         "legacy_dry_median": float(np.median(p["legacy_dry"][k])),
         "armn_dry_median": float(np.median(p["armn_dry"][k]))}
        for k in range(p["armn_dry"].shape[0])]
    return out


def from_stream(text: str, species: str = "nr") -> dict:
    """The same question put to a KERNEL RUN instead of a state file.

    `profile()` reads coefficients off an atmosphere; this reads the residual an
    arm actually leaves, in BOTH ledgers, from the transfers the run performed:

        moist:  N = sum rho        * dz * n     -- the OPERATOR's own measure
        dry:    N = sum rho/(1+qv) * dz * n     -- the physical one, G33-BASIS-006

    and each is reported beside its closed form. With `A` the density the arm
    weights the interface transfer by and `B` the ledger's,

        R = sum_j a_j * dz_j * ( B_{j+1} * A_j / A_{j+1} - B_j )

    which is an IDENTITY, not a fit -- ratio 1.00000000 on all six rows of
    `g33_fixture_moisture_gradient_v1`. Where `A == B` every term is exactly
    zero, which is why Arm N's moist prediction is 0.000000 against a measured
    roundoff, and its DRY prediction is not.

    Each residual is reported TWICE: once from the recovered transfers and once
    from the ACTUAL `XFER` record the kernel emits, which shares no input with
    the prediction. Measured on `g33_fixture_moisture_gradient_v1`, the dry
    residuals agree to better than 0.1 % -- so the moisture term is an
    independent measurement, not an artefact of the recovery.

    The moist row is where they must NOT be read the same way. `A == B` makes
    the recovered residual algebraically zero, so its 1e-17 relative is forced;
    the XFER path gives 5.7e-08 relative, which is the honest number and is
    still below the f32 epsilon of 1.19e-07.

    This needs a fixture with a vertical moisture gradient. Under a
    column-uniform `qv` the two ledgers differ by a constant factor per column
    and say the same thing (`FINDING_number_basis_gap_v1`).
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    import g33_number_transport as nt
    import g33_matched_closure as mc
    xfer = mc.transfers(text)
    call = nt.calls(text)[0]
    loop = nt.single_loop(call)
    pre, post = call["outer_pre_sed"], call["outer_post_sed"]
    metric = nt.number_transfer_metric(call.get("algorithm"),
                                       call.get("declared_metric"))
    out = {}
    for col in sorted({c for l, c, _k in pre if l == loop}):
        ks = sorted(k for l, c, k in pre if c == col and l == loop)
        den = [pre[(loop, col, k)]["rho"] for k in ks]
        qv = [pre[(loop, col, k)]["qv"] for k in ks]
        dz = [pre[(loop, col, k)]["delz"] for k in ks]
        x = [pre[(loop, col, k)][species] for k in ks]
        x1 = [post[(loop, col, k)][species] for k in ks]
        # THE WINDOW-INITIAL DRY MASS, from the repository's single authority.
        #
        # `den[t] / (1 + qv[t])` with THIS call's `qv` is a moving measure: dry
        # air does not leave the column during microphysics, so a ledger whose
        # denominator changes is not a conserved quantity being tracked -- it is
        # a quantity being redefined. `window_cell_mass(stream, "physical")`
        # takes `qv` from `G33R INITIAL` and freezes `rho*dz` together, and its
        # docstring records that an earlier version of THAT function made this
        # same mistake. Making it twice is what a second copy of a fact is for
        # (owner review §4).
        wm = mc.window_cell_mass(text, "physical")
        dry = [mc.measure_at(wm, (col, k), "from_stream").density for k in ks]
        dz_fixed = [mc.measure_at(wm, (col, k), "from_stream").delz for k in ks]
        # THE WEIGHT THE ARM USED, which is what produced these endpoints --
        # taken from the arm's own registered measure, not from whether its
        # name contains a substring. `nmass_dry` and `nmass_dry_window` both
        # contain `nmass` and both weight by a DRY mass; inverting them with
        # the moist one returned transfers that never happened (owner review
        # §9). The window arm's measure is the frozen mass this function
        # already has in hand.
        mdry0 = [dry[t] * dz_fixed[t] for t in range(len(ks))]
        w = nt.number_transfer_weights(metric, den, dz, qv, mdry0)
        a = nt.transfers(x, x1, w)
        row = {}
        # THE ACTUAL surface transfer, from the XFER record the kernel emits.
        # `a[-1]` above is recovered from the endpoints, so a residual built on
        # it and a prediction built on it share their input -- the agreement is
        # an algebraic check and not an independent measurement (owner §6).
        chain = "main" if species in ("qr", "nr") else "ice"
        _dq, dn = xfer[(1, loop, col, chain)]
        # THE ACTUAL FLUX WEIGHTING, which only a replay can give. `a[j]` is
        # what crossed interface `j`, so the column defect is
        # `sum_j a_j dz_j eps_j` and the ratio between two arms' coefficients is
        # weighted by it. A state file records the upper cell's INVENTORY and
        # not this, which is why the domain statistic is named for the
        # inventory (owner review §4).
        eps_leg = [den[j] / den[j + 1] - 1.0 for j in range(len(ks) - 1)]
        eps_arm = [(1.0 + qv[j + 1]) / (1.0 + qv[j]) - 1.0
                   for j in range(len(ks) - 1)]
        wj = [abs(a[j] * dz[j]) for j in range(len(ks) - 1)]
        num = abs(sum(w * e for w, e in zip(wj, eps_arm)))
        den_ = abs(sum(w * e for w, e in zip(wj, eps_leg)))
        # RECOVERED, not emitted. `a[j]` comes from inverting the update at
        # each interface; the kernel emits only the SURFACE transfer. So this
        # weights the coefficients by the transfers the endpoints imply, and
        # calling it the actual interface flux would claim an instrument that
        # does not exist yet (owner review §7).
        row["recovered_transfer_weighted_fraction"] = num / den_ if den_ else None
        # The density half of the same registered measure, for the closed form.
        a_w = nt.number_layer_density(metric, den, qv, dry)
        for tag, B, DZ in (("moist", den, dz), ("dry", dry, dz_fixed)):
            n0 = sum(B[t] * DZ[t] * x[t] for t in range(len(ks)))
            n1 = sum(B[t] * DZ[t] * x1[t] for t in range(len(ks)))
            meas = (n1 - n0) + B[-1] * DZ[-1] * a[-1]
            row[f"{tag}_xfer"] = (n1 - n0) + B[-1] * DZ[-1] * dn
            pred = sum(a[j] * DZ[j] * (B[j + 1] * a_w[j] / a_w[j + 1] - B[j])
                       for j in range(len(ks) - 1))
            row[tag] = meas
            row[f"{tag}_predicted"] = pred
            row[f"start_{tag}"] = n0
            # `None` where there is nothing to divide by: an arm whose weight IS
            # the ledger drives both sides to roundoff, and a ratio taken there
            # says only which way the last bit fell.
            row[f"{tag}_predicted_over_measured"] = (
                pred / meas if abs(meas) > 1e-9 * (abs(n0) or 1.0) else None)
        out[col] = row
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
