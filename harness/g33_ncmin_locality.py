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

#: The condensate species, and the vapour that feeds them.
CONDENSATE = ("qc", "qr", "qi", "qs", "qg")

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


def _ordered(h: str) -> int:
    """The f32 bits mapped to a MONOTONIC integer.

    A raw signed-int32 difference is the representable-step distance only for
    same-sign positives: it is wrong across zero, and makes +0.0 and -0.0 look
    2^31 apart (owner §11.4). Flipping the sign bit for positives and inverting
    negatives gives an ordering in which adjacent floats are adjacent integers.
    """
    u = struct.unpack(">I", bytes.fromhex(h))[0]
    return (0xFFFFFFFF - u) if u & 0x80000000 else (u | 0x80000000)


def _ulps(a: str, b: str) -> int:
    """Distance in representable f32 steps -- the unit a rounding claim is in."""
    return abs(_ordered(a) - _ordered(b))


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


def column_integrated(base_text: str, got_text: str) -> dict:
    """{(col, field): (baseline, partition, abs, rel)} under the rho*dz measure.

    A per-component RELATIVE difference near 1 says the two runs disagree about
    a value, not that the value is large: `qi` reaches 0.997 on a baseline of
    6.6e-08 kg/kg, an absolute difference of 1.9e-05. Only a column integral
    says whether the disagreement carries mass (owner §11.3).
    """
    a, b = (ra.read_text(t, nsplit=1) for t in (base_text, got_text))
    cells = {(k[2], k[3]) for k in a if k[0] == "state"}
    out = {}
    for col in sorted({c for c, _ in cells}):
        ks = sorted(k for c, k in cells if c == col)

        def col_mass(run, fields):
            return sum(run[("forcing", "rho", col, k)]
                       * run[("forcing", "delz", col, k)]
                       * sum(run[("state", f, col, k)] for f in fields)
                       for k in ks)

        for name, fields in ([(f, (f,)) for f in CONDENSATE]
                             + [("total_condensate", CONDENSATE)]):
            x, y = col_mass(a, fields), col_mass(b, fields)
            if x != y:
                out[(col, name)] = (x, y, abs(y - x),
                                    abs(y - x) / max(abs(x), 1e-30))
    return out


def analysis(driver: str, fixture: str) -> dict:
    """Every contiguous partition against the whole domain as one tile.

    Raw hex compared, not parsed floats: the question is whether the operator
    produced the same bits, and a float round-trip is the wrong instrument.
    """
    width, levels = fixture_dims(fixture)

    base_text = run(driver, (width,))
    _expect_tiles_are_live(base_text, (width,), "baseline")
    base = read_state(base_text, label="baseline")
    _expect_universe(base, width, levels, "baseline")
    rows = {}
    for tiles in compositions(width):
        if tiles == (width,):
            continue
        got_text = run(driver, tiles)
        label = f"tiles={','.join(map(str, tiles))}"
        _expect_tiles_are_live(got_text, tiles, label)
        got = read_state(got_text, label=label)
        _expect_universe(got, width, levels, label)
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
            d = fields.setdefault(f, {"components": 0, "max_rel": 0.0,
                                      "max_ulps": 0, "max_abs": 0.0,
                                      "max_abs_baseline": 0.0})
            d["components"] += 1
            d["max_rel"] = max(d["max_rel"], rel)
            d["max_ulps"] = max(d["max_ulps"], _ulps(a, b))
            # ABSOLUTE too (owner §11.3). A relative difference near 1 says the
            # two runs disagree about the value, not that the value is large: a
            # tiny baseline gives ~100% for a negligible mass. Both are needed
            # before "cloud ice differs by O(1)" can mean anything physical, and
            # the baseline magnitude says which regime it is.
            if abs(fb - fa) > d["max_abs"]:
                d["max_abs"] = abs(fb - fa)
                d["max_abs_baseline"] = abs(fa)
        rows[",".join(map(str, tiles))] = {
            "components_differing": len(diff),
            "components_total": len(base),
            # 144 = 12 fields x 3 columns x 4 levels. The grid has
            # 12 CELLS; 144 is the number of prognostic state
            # COMPONENTS, and calling them cells overstated the
            # spatial extent by a factor of twelve (owner §11.1).
            "grid_cells": len({(k[1], k[2]) for k in base}),
            "columns": sorted({k[1] for k in diff}),
            # The judgement the finding asserted, now derived: is the largest
            # difference at the scale arithmetic noise lives at, or far above it?
            "max_rel": max((d["max_rel"] for d in fields.values()), default=0.0),
            "is_roundoff_scale": all(d["max_rel"] <= 16 * F32_EPS
                                     for d in fields.values()),
            "by_field": fields,
            # What the disagreement is worth once integrated over the column --
            # the only form in which "cloud ice differs" is a physical
            # statement rather than a per-component ratio (owner §11.3).
            "column_integrated": {f"{c}/{f}": {"baseline": x, "partition": y,
                                               "abs": ad, "rel": rd}
                                  for (c, f), (x, y, ad, rd)
                                  in column_integrated(base_text, got_text).items()},
        }
    return {"f32_eps": F32_EPS, "partitions": rows}


def report(driver: str, fixture: str) -> None:
    a = analysis(driver, fixture)
    print("  Tile decomposition changes the answer. Size, not only count.\n")
    print(f"  {'partition':>10} {'components':>11} {'columns':>9} {'field':>6} "
          f"{'max |rel|':>12} {'max ulps':>10} {'max |abs|':>12} "
          f"{'baseline':>12}")
    for tiles, r in a["partitions"].items():
        if not r["components_differing"]:
            print(f"  {tiles:>10} {'0':>10} {'-':>9}   (both tiles end on the "
                  f"same surface type -- identical gating)")
            continue
        first = f"{r['components_differing']}/{r['components_total']}"
        for f, d in sorted(r["by_field"].items(), key=lambda x: -x[1]["max_rel"]):
            print(f"  {tiles if first else '':>10} {first:>11} "
                  f"{str(r['columns']) if first else '':>9} {f:>6} "
                  f"{d['max_rel']:12.4e} {d['max_ulps']:10d} "
                  f"{d['max_abs']:12.4e} {d['max_abs_baseline']:12.4e}")
            first = ""
    print(f"\n  f32 eps = {a['f32_eps']:.3e}. A rounding difference lives there.")
    for tiles, r in a["partitions"].items():
        if r["components_differing"] and not r["is_roundoff_scale"]:
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
