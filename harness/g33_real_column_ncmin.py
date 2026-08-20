"""How much of a real domain the scalar `ncmin` mis-thresholds.

In the Fortran reference `ncmin` is a SCALAR set inside the column loop, so
after the loop it holds the value belonging to the LAST column of the tile --
and every column in that tile is thresholded by that one column's `xland`.

Which columns are affected therefore depends on the GEOGRAPHY and the TILING
alone. Neither needs a run, a corrected arm, or any change to frozen code, so
this is measurable while the freeze-lift for the per-column arm is still a
decision the owner has not taken.

What this is NOT: a rain difference, a precipitation change, or a forecast
impact. A column is only actually affected when its number concentration lies
between the two thresholds -- a column far from both branches the same way
whichever value it is given. This bounds the EXPOSURE: how many columns are
handed a threshold from a column of the other surface type, and how much that
set moves when the decomposition does.

That second number is the one that matters for locality: if the affected set
were the same under every decomposition, the operator would still be wrong but
it would at least be a FUNCTION of the state. It is not.
"""
import sys
from pathlib import Path


def imposed(xland, tiles: int):
    """The `xland` each column is actually thresholded by, under `tiles`
    equal i-patches -- that is, the last column of its own patch."""
    import numpy as np
    out = np.empty_like(xland)
    edges = np.linspace(0, xland.shape[1], tiles + 1).astype(int)
    for a, b in zip(edges[:-1], edges[1:]):
        if b > a:
            out[:, a:b] = xland[:, b - 1][:, None]
    return out


def report(state: Path, tilings=(1, 2, 4, 8)) -> dict:
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(state))
    xland = np.asarray(d["XLAND"][0], dtype="int32")
    seen = {n: imposed(xland, n) for n in tilings}
    pairs = [{"a": a, "b": b,
              "columns_disagreeing": float((seen[a] != seen[b]).mean())}
             for i, a in enumerate(tilings) for b in tilings[i + 1:]]
    return {
        "state": str(state),
        "columns": int(xland.size),
        "land_fraction": float((xland == 1).mean()),
        "by_tiling": [{"tiles": n,
                       "mis_thresholded": float((seen[n] != xland).mean())}
                      for n in tilings],
        "decomposition_pairs": pairs,
        # The columns every tiling gets right. Everything else is a column
        # whose threshold is an artefact of how the domain was cut.
        "correct_under_all": float(
            np.all([seen[n] == xland for n in tilings], axis=0).mean()),
    }


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    import json
    print(json.dumps(report(Path(argv[0])), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
