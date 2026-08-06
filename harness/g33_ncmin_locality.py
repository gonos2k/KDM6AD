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

    python g33_ncmin_locality.py <driver> <fixture-name>
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra  # noqa: E402
from g33_refine_experiment import fixture_dims  # noqa: E402

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


def run(driver: str, tiles) -> str:
    """The driver's stdout for one decomposition."""
    r = subprocess.run([driver, "1", "rezero", ",".join(map(str, tiles))],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    return r.stdout


def tile_brackets(text: str) -> list:
    """The (i0, i1) column bounds each kernel call ACTUALLY received.

    `G33N CALL_BEGIN` is written from INSIDE the tile loop, carrying the very
    bounds handed to `kdm62D` on the next statement. Needs an `--nflux` build,
    whose STATE records are byte-identical to the plain one on this fixture.
    """
    return [(int(p[5]), int(p[6]))
            for p in (ln.split() for ln in text.splitlines())
            if p[:2] == ["G33N", "CALL_BEGIN"]]


def _expect_tiles_are_live(text: str, tiles, label: str) -> None:
    """The kernel must have been called over the decomposition we ASKED for.

    The previous version ran an INVALID spec and required a refusal. That only
    proves the argument is parsed and validated -- and validation lives in the
    argument parser while use lives in the tile loop, so a driver that validated
    the spec and then called the kernel over the whole domain passed it
    (Codex). Every partition would then equal the baseline and the tool would
    report zero differences everywhere: "the operator is column-local", the
    strongest possible pass and the exact claim it exists to refute.

    This reads the bounds the kernel was given, so validating-and-ignoring is
    caught where being-refused never was.
    """
    want, i = [], 0
    for t in tiles:
        want.append((i + 1, i + t))
        i += t
    got = tile_brackets(text)
    if not got:
        raise ra.RefineError(
            f"{label}: no G33N CALL_BEGIN records -- this needs an --nflux "
            f"build, without which nothing says which decomposition ran")
    if got != want:
        raise ra.RefineError(
            f"{label}: the kernel was called over {got}, not the requested "
            f"{want} -- the tile argument is not reaching the partitioning")


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def _ulps(a: str, b: str) -> int:
    """Distance in representable f32 steps -- the unit a rounding claim is in."""
    ia, ib = (struct.unpack(">i", bytes.fromhex(x))[0] for x in (a, b))
    return abs(ia - ib)


def _expect_universe(got: dict, cols: int, levels: int, label: str) -> None:
    """The run must cover the domain the FIXTURE declares.

    Comparing a partition against the baseline only asks whether they agree with
    each other, and a run that drops a column agrees with itself perfectly: with
    column 3 gone everywhere, the tool reported `31/96` and a shrunken
    denominator as a normal result. Had the SEA column gone instead, it would
    have reported zero differences and concluded the operator is column-local --
    the claim it exists to refute. Only a figure from outside the run can catch
    that, so this one comes from the fixture source.
    """
    # The emitter writes `emit_fld(name, i, KM-k, ...)` over `i = 1..IM`,
    # `k = 1..KM`, so the protocol's indices are columns 1..B and levels 0..K-1.
    # Both are checked as SETS. Levels were checked by COUNT alone, which
    # admitted an axis shifted off its origin -- `{10,11,12,13}` has four
    # entries too (owner/Codex).
    #
    # What a universe check CANNOT see, enumerated so the boundary is stated
    # once rather than discovered one axis at a time: a REVERSED level axis and
    # a TRANSPOSED column mapping are both the same SET. They are ordering
    # properties, not universe ones. Neither passes silently -- either applied
    # to one run and not the other makes most cells differ, so they surface as
    # an implausibly large result rather than a clean one, which is the
    # opposite of the failure mode this gate exists for.
    want_cols, want_k = set(range(1, cols + 1)), set(range(levels))
    have_cols = {k[1] for k in got}
    have_k = {k[2] for k in got}
    if have_cols != want_cols:
        raise ra.RefineError(
            f"{label}: columns {sorted(have_cols)}, fixture declares "
            f"{sorted(want_cols)}")
    if have_k != want_k:
        raise ra.RefineError(
            f"{label}: levels {sorted(have_k)}, fixture declares "
            f"{sorted(want_k)}")
    want = len(ra.STATE_FIELDS) * cols * levels
    if len(got) != want:
        raise ra.RefineError(f"{label}: {len(got)} STATE records, expected {want}")


def analysis(driver: str, fixture: str) -> dict:
    """Every contiguous partition against the whole domain as one tile.

    Raw hex compared, not parsed floats: the question is whether the operator
    produced the same bits, and a float round-trip is the wrong instrument.
    """
    width, levels = fixture_dims(fixture)

    def snapshot(tiles):
        label = f"tiles={','.join(map(str, tiles))}"
        text = run(driver, tiles)
        _expect_tiles_are_live(text, tiles, label)
        got = read_state(text, label=label)
        _expect_universe(got, width, levels, label)
        return got

    base = snapshot((width,))
    rows = {}
    for tiles in compositions(width):
        if tiles == (width,):
            continue
        got = snapshot(tiles)
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


def report(driver: str, fixture: str) -> None:
    a = analysis(driver, fixture)
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
    if len(argv) != 2:
        print(__doc__)
        return 2
    report(argv[0], argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
