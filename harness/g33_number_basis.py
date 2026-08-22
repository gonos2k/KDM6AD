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

RD, CP, P0 = 287.04, 1004.5, 1.0e5


def profile(state: Path) -> dict:
    """The three per-interface coefficients from a WRF state file."""
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(state))
    g = lambda k: np.asarray(d[k][0], dtype="float64")   # noqa: E731
    pressure = g("P") + g("PB")
    theta = g("T") + 300.0
    qv = g("QVAPOR")
    temp = theta * (pressure / P0) ** (RD / CP)
    # Total moist density, which is the kernel's `den`; dry is that over 1+qv.
    den = pressure / (RD * temp * (1.0 + 0.608 * qv))
    den_d = den / (1.0 + qv)
    # WRF k=0 is the BOTTOM, so [:-1] is the LOWER side of each interface and
    # [1:] the upper -- the direction sedimentation moves.
    lo, up = slice(None, -1), slice(1, None)
    return {
        "legacy_moist": den[lo] / den[up] - 1.0,
        "legacy_dry": den_d[lo] / den_d[up] - 1.0,
        "armn_dry": (1.0 + qv[up]) / (1.0 + qv[lo]) - 1.0,
        "qv_lower": qv[lo],
        "p_mid": 0.5 * (pressure[lo] + pressure[up]),
    }


def report(state: Path) -> dict:
    import numpy as np
    p = profile(state)
    out = {"state": str(state), "interfaces": int(p["armn_dry"].size)}
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

    This needs a fixture with a vertical moisture gradient. Under a
    column-uniform `qv` the two ledgers differ by a constant factor per column
    and say the same thing (`FINDING_number_basis_gap_v1`).
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    import g33_number_transport as nt
    call = nt.calls(text)[0]
    loop = nt.single_loop(call)
    pre, post = call["outer_pre_sed"], call["outer_post_sed"]
    carries = nt.number_carries_density(call.get("algorithm"))
    out = {}
    for col in sorted({c for l, c, _k in pre if l == loop}):
        ks = sorted(k for l, c, k in pre if c == col and l == loop)
        den = [pre[(loop, col, k)]["rho"] for k in ks]
        qv = [pre[(loop, col, k)]["qv"] for k in ks]
        dz = [pre[(loop, col, k)]["delz"] for k in ks]
        x = [pre[(loop, col, k)][species] for k in ks]
        x1 = [post[(loop, col, k)][species] for k in ks]
        dry = [den[t] / (1.0 + qv[t]) for t in range(len(ks))]
        # The weight the ARM used, which is what produced these endpoints.
        a_w = den if carries else [1.0] * len(ks)
        w = [0.0] + [dz[t - 1] / dz[t] * (a_w[t - 1] / a_w[t])
                     for t in range(1, len(ks))]
        a = nt.transfers(x, x1, w)
        row = {}
        for tag, B in (("moist", den), ("dry", dry)):
            n0 = sum(B[t] * dz[t] * x[t] for t in range(len(ks)))
            n1 = sum(B[t] * dz[t] * x1[t] for t in range(len(ks)))
            meas = (n1 - n0) + B[-1] * dz[-1] * a[-1]
            pred = sum(a[j] * dz[j] * (B[j + 1] * a_w[j] / a_w[j + 1] - B[j])
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
