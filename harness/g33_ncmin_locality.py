#!/usr/bin/env python3
"""What the scalar `ncmin` costs, measured rather than counted.

`ncmin` is assigned inside the column loop and survives it holding the LAST
column's threshold (`ncmin_land` or `ncmin_sea` by that column's `xland`). A
column-local operator must give the same answer for every tile decomposition;
this one does not, so the answer depends on where a tile or MPI boundary falls.

`FINDING_ncmin_scalar_vs_percell.md` reported "31 / 144 cells differ" and called
it "a whole-state difference, not a rounding one". That was a COUNT and an
assertion. A count cannot tell a roundoff-scale difference from a dominating
one -- the same conflation owner §10 named for the cap-bound interfaces -- so
this reports the SIZE beside it.

Exhaustive over the CONTIGUOUS PARTITIONS of the domain, not just even splits:
`(1, 2)` differs in zero cells because both tiles end on land, so a gate that
only tried even splits would pass while the operator was arbitrarily non-local.

    python g33_ncmin_locality.py <driver> [width]
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra  # noqa: E402

#: f32 machine epsilon. The scale a "rounding difference" would live at.
F32_EPS = 2.0 ** -23


def compositions(n: int) -> list[tuple]:
    """Every ordered way to split `n` columns into contiguous tiles."""
    if n == 0:
        return [()]
    return [(first,) + rest
            for first in range(1, n + 1)
            for rest in compositions(n - first)]


def read_state(text: str, *, label: str) -> dict:
    """{(field, col, k): raw hex}, and ONLY from a stream the strict parser took.

    The first version parsed the lines itself. That accepted anything: a driver
    emitting NOTHING gave an empty dict, every partition then showed zero cells,
    and
    the report printed "identical gating" -- a completely broken run reading as
    the strongest possible pass. Validating through `ra.read_text` first brings
    the checks that already exist (exactly one BEGIN and END, the full field
    set, a non-ragged grid, no duplicate records, no non-finite value) instead
    of re-deriving a weaker set beside them.

    The hex is then taken raw, because the comparison is about the BITS the
    operator produced and 0.0 == -0.0 would hide a sign flip.
    """
    ra.read_text(text, nsplit=1, label=label)
    out = {}
    for p in (ln.split() for ln in text.splitlines()):
        if p[:2] == ["G33R", "STATE"]:
            out[(p[2], int(p[3]), int(p[4]))] = p[5]
    if not out:
        raise ra.RefineError(f"{label}: no G33R STATE records")
    return out


def state(driver: str, tiles) -> dict:
    """{(field, col, k): raw hex} after one call under this decomposition."""
    r = subprocess.run([driver, "1", "rezero", ",".join(map(str, tiles))],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    return read_state(r.stdout, label=f"tiles={','.join(map(str, tiles))}")


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def _ulps(a: str, b: str) -> int:
    """Distance in representable f32 steps -- the unit a rounding claim is in."""
    ia, ib = (struct.unpack(">i", bytes.fromhex(x))[0] for x in (a, b))
    return abs(ia - ib)


def analysis(driver: str, width: int = 3) -> dict:
    """Every contiguous partition against the whole domain as one tile.

    Raw hex compared, not parsed floats: the question is whether the operator
    produced the same bits, and a float round-trip is the wrong instrument.
    """
    base = state(driver, (width,))
    rows = {}
    for tiles in compositions(width):
        if tiles == (width,):
            continue
        got = state(driver, tiles)
        # The universes must be the SAME cells, or "how many differ" is counted
        # over whatever both happened to carry -- and a short baseline reports
        # FEWER differences, which is the flattering direction.
        if set(got) != set(base):
            raise ra.RefineError(
                f"tiles={tiles}: {len(set(got) ^ set(base))} cells are not in "
                f"both this partition and the whole-domain baseline")
        diff = {k: (base[k], got[k]) for k in base if base[k] != got[k]}
        fields = {}
        for (f, _c, _k), (a, b) in diff.items():
            fa, fb = _f32(a), _f32(b)
            rel = abs(fb - fa) / max(abs(fa), abs(fb), 1e-30)
            d = fields.setdefault(f, {"cells": 0, "max_rel": 0.0, "max_ulps": 0})
            d["cells"] += 1
            d["max_rel"] = max(d["max_rel"], rel)
            d["max_ulps"] = max(d["max_ulps"], _ulps(a, b))
        rows[",".join(map(str, tiles))] = {
            "cells_differing": len(diff),
            "cells_total": len(base),
            "columns": sorted({k[1] for k in diff}),
            # The judgement the finding asserted, now derived: is the largest
            # difference at the scale arithmetic noise lives at, or far above it?
            "max_rel": max((d["max_rel"] for d in fields.values()), default=0.0),
            "is_roundoff_scale": all(d["max_rel"] <= 16 * F32_EPS
                                     for d in fields.values()),
            "by_field": fields,
        }
    return {"f32_eps": F32_EPS, "partitions": rows}


def report(driver: str, width: int = 3) -> None:
    a = analysis(driver, width)
    print("  Tile decomposition changes the answer. Size, not only count.\n")
    print(f"  {'partition':>10} {'cells':>10} {'columns':>9} {'field':>6} "
          f"{'max |rel|':>12} {'max ulps':>10}")
    for tiles, r in a["partitions"].items():
        if not r["cells_differing"]:
            print(f"  {tiles:>10} {'0':>10} {'-':>9}   (both tiles end on the "
                  f"same surface type -- identical gating)")
            continue
        first = f"{r['cells_differing']}/{r['cells_total']}"
        for f, d in sorted(r["by_field"].items(), key=lambda x: -x[1]["max_rel"]):
            print(f"  {tiles if first else '':>10} {first:>10} "
                  f"{str(r['columns']) if first else '':>9} {f:>6} "
                  f"{d['max_rel']:12.4e} {d['max_ulps']:10d}")
            first = ""
    print(f"\n  f32 eps = {a['f32_eps']:.3e}. A rounding difference lives there.")
    for tiles, r in a["partitions"].items():
        if r["cells_differing"] and not r["is_roundoff_scale"]:
            print(f"  {tiles}: max relative difference {r['max_rel']:.4e} is "
                  f"{r['max_rel'] / a['f32_eps']:.3g}x f32 eps.")


def main(argv) -> int:
    if not 1 <= len(argv) <= 2:
        print(__doc__)
        return 2
    width = int(argv[1]) if len(argv) == 2 else 3
    report(argv[0], width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
