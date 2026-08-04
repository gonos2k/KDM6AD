#!/usr/bin/env python3
"""Strict reader for the G33P precision-probe stream (owner priority 2).

The probe was a side-channel: decimal records with no framing, no precision
declared, and no parser of its own. Two hazards followed. An f64 stream and an
f32 one are the same text with different numbers, so nothing structurally stopped
a reader mixing them; and an incomplete probe stream looked like a complete one.

    G33P BEGIN <schema> precision <p> source_precision <sp> fixture <name>
        algorithm <algo> mode <carry|rezero> <nsplit> <loops> <ntile>
        <delt> <dtcld> <B> <K>
    G33P STATE|INITIAL <field> <col> <k_topfirst> <value>
    G33P FORCING rho|delz|pii <col> <k_topfirst> <value>
    G33P PREC <species> <col> <value>
    G33P END

`source_precision` is the precision of the REFERENCE this arm instruments, which
is always f32: an f64 arm is an instrument, not the operator being certified.

Refuses: a missing BEGIN or END, a foreign schema, a field set that is not
exactly the state vocabulary, a ragged (col, k) grid, forcing that is present but
incomplete, PREC that is not species 1/2/3 over the state's columns, a duplicate
record, and any non-finite value. `compare()` additionally refuses a pair of
streams whose grids or source precision disagree.
"""
from __future__ import annotations

import math
import re
import struct
import sys
from pathlib import Path

BEGIN = re.compile(
    r"^G33P BEGIN (\d+) precision (f32|f64) source_precision (f32|f64) "
    r"fixture (\S+) algorithm (\S+) mode (carry|rezero) tiles (\S+) "
    r"(\d+) (\d+) (\d+) (\S+) (\S+) (\d+) (\d+)$")
END = re.compile(r"^G33P END$")
STATE = re.compile(r"^G33P (STATE|INITIAL) (\S+) (\d+) (-?\d+)\s+(\S+)$")
FORCING = re.compile(r"^G33P FORCING (rho|delz|pii) (\d+) (-?\d+)\s+(\S+)$")
PREC = re.compile(r"^G33P PREC (\d+) (\d+)\s+(\S+)$")

SCHEMA = 3
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as _ra   # noqa: E402

#: The state vocabulary, taken from the G33R contract rather than restated. The
#: driver emits ONE state vector; a second copy of the list here drifts (the
#: first version of this file said `brs` where the stream says `bg`).
FIELDS = _ra.STATE_FIELDS


class ProbeError(Exception):
    """The probe stream is not a complete record of the run it claims to be."""


def _expect(cond, msg):
    if not cond:
        raise ProbeError(msg)


def _f(tok: str) -> float:
    """Fortran ES formatting drops the `E` once an exponent needs three digits
    (5.3e-316 as `5.2679749487822913-316`). ES26.16E3 prevents it; this accepts
    the older form rather than silently failing on an archived stream."""
    try:
        return float(tok)
    except ValueError:
        m = re.fullmatch(r"([-+]?[\d.]+)([-+]\d{3})", tok)
        _expect(m, f"unparseable value {tok!r}")
        return float(f"{m.group(1)}E{m.group(2)}")


def read(text: str) -> dict:
    """{(cls, field, col, k): value} plus ("meta", ...) entries."""
    lines = [l for l in text.splitlines() if l.startswith("G33P")]
    _expect(lines, "no G33P records")
    m = BEGIN.match(lines[0])
    _expect(m, f"stream does not begin with G33P BEGIN: {lines[0]!r}")
    (schema, precision, source, fixture, algorithm, mode, tiles, nsplit, loops,
     ntile, delt, dtcld, B, K) = m.groups()
    _expect(int(schema) == SCHEMA,
            f"stream declares schema {schema}, parser is {SCHEMA}")
    _expect(END.match(lines[-1]), "stream has no G33P END — it is truncated")

    out, seen = {}, set()
    for ln in lines[1:-1]:
        if (g := STATE.match(ln)):
            cls, field, col, k, v = g.groups()
            key = (cls.lower(), field, int(col), int(k))
        elif (g := FORCING.match(ln)):
            name, col, k, v = g.groups()
            key = ("forcing", name, int(col), int(k))
        elif (g := PREC.match(ln)):
            sp, col, v = g.groups()
            key = ("prec", int(sp), int(col))
        else:
            raise ProbeError(f"unrecognised G33P record: {ln!r}")
        _expect(key not in seen, f"duplicate record {key}")
        seen.add(key)
        val = _f(v)
        _expect(math.isfinite(val), f"non-finite value at {key}")
        out[key] = val

    st = [k for k in out if k[0] == "state"]
    _expect(st, "no STATE records")
    _expect({k[1] for k in st} == set(FIELDS),
            f"state field set is {sorted({k[1] for k in st})}, expected "
            f"{sorted(FIELDS)}")
    # EXACT rectangular universe (owner §7.2). Checking the field NAMES and the
    # cell COUNT separately let one field skip a cell while another supplied it:
    # both sets look complete, the product is not.
    cells = {(c, k) for c in range(1, int(B) + 1) for k in range(int(K))}
    want = {("state", f, c, k) for f in FIELDS for c, k in cells}
    got = set(st)
    _expect(got == want,
            f"STATE is not the exact {len(FIELDS)}x{B}x{K} universe: "
            f"{len(want - got)} missing, {len(got - want)} unexpected")
    # The driver always emits these, so they are REQUIRED, not optional: a stream
    # missing them is incomplete, and "absent" silently disabled every check.
    _expect({k[1:] for k in out if k[0] == "initial"} == {k[1:] for k in st},
            "INITIAL is not the exact STATE universe")
    for nm in ("rho", "delz", "pii"):
        _expect({(k[2], k[3]) for k in out if k[0] == "forcing" and k[1] == nm}
                == cells, f"forcing `{nm}` is not the exact cell universe")
    _expect({(k[1], k[2]) for k in out if k[0] == "prec"}
            == {(sp, c) for sp in (1, 2, 3) for c in range(1, int(B) + 1)},
            "prec is not exactly species 1/2/3 over every column")
    out |= {("meta", "schema"): int(schema), ("meta", "precision"): precision,
            ("meta", "source_precision"): source, ("meta", "fixture"): fixture,
            ("meta", "algorithm"): algorithm, ("meta", "mode"): mode,
            ("meta", "nsplit"): int(nsplit), ("meta", "loops"): int(loops),
            ("meta", "ntile"): int(ntile), ("meta", "delt"): _f(delt),
            ("meta", "dtcld"): _f(dtcld),
            # The tile VECTOR, not just its length: `ntile` alone cannot tell
            # (2,1) from (1,2), and `ncmin` is a scalar overwritten in the column
            # loop, so those two decompositions can disagree (owner §8.1).
            ("meta", "tiles"): tuple(int(t) for t in tiles.split(","))}
    return out


#: What must be IDENTICAL for each kind of comparison, and what must DIFFER.
#: A single `compare` could pair `legacy f32 N=3` with `conservative f64 N=96`
#: purely because their record universes matched (owner P0-5).
#: kind -> (the axis that must DIFFER, the axes allowed to covary with it).
#: Everything else the header carries must be IDENTICAL, and that set is COMPUTED
#: rather than listed (owner §8.1): the listed form silently omitted
#: `source_precision`, `loops`, `ntile`, `delt` and the tile vector, so two runs
#: differing in any of them compared clean. Computing it means a field added to
#: the header becomes an invariant by default -- fail-closed rather than
#: fail-open on the next schema change.
COMPARISONS = {
    "precision_pair": ("precision", frozenset()),
    "variant":        ("algorithm", frozenset()),
    # dtcld is the refinement axis; nsplit and delt are the same knob expressed
    # differently, so they must move with it rather than being invariants.
    "refinement":     ("dtcld", frozenset({"nsplit", "delt"})),
}

#: Header fields that identify the experiment. `schema` is included: two streams
#: written under different protocol versions are not obviously the same fields.
IDENTITY = ("schema", "precision", "source_precision", "fixture", "algorithm",
            "mode", "nsplit", "loops", "ntile", "tiles", "delt", "dtcld")


def invariants(kind: str) -> tuple:
    """What must match for `kind`: everything identifying, less the axis under
    test and whatever necessarily moves with it."""
    differs, covaries = COMPARISONS[kind]
    return tuple(f for f in IDENTITY if f != differs and f not in covaries)


def compare(a: dict, b: dict, kind: str) -> None:
    """Two probe streams are comparable only under a NAMED contract.

    `kind` says which one thing may differ; everything else identifying the
    experiment must match. `refinement` additionally allows the record universes
    to differ in nothing but their values, since two steps of one chain describe
    the same grid.
    """
    _expect(kind in COMPARISONS,
            f"unknown comparison {kind!r}; expected one of {sorted(COMPARISONS)}")
    differs, _ = COMPARISONS[kind]
    for f in invariants(kind):
        _expect(a[("meta", f)] == b[("meta", f)],
                f"{kind}: streams disagree on {f} "
                f"({a[('meta', f)]} vs {b[('meta', f)]}) — they are not the same "
                f"experiment")
    _expect(a[("meta", differs)] != b[("meta", differs)],
            f"{kind}: {differs} is the same in both ({a[('meta', differs)]}); "
            f"there is nothing to compare")
    ka = {k for k in a if k[0] != "meta"}
    kb = {k for k in b if k[0] != "meta"}
    _expect(ka == kb, f"streams carry different records ({len(ka ^ kb)} differ)")


def _bits(x: float, precision: str) -> int:
    """Sign-magnitude bit pattern mapped to a monotone integer, so a subtraction
    counts representable steps across zero as well as within a sign."""
    fmt, width = (">f", 32) if precision == "f32" else (">d", 64)
    n = int.from_bytes(struct.pack(fmt, x), "big")
    sign = 1 << (width - 1)
    # Positive patterns already increase with the value; negative ones increase
    # with MAGNITUDE, so they are reflected. This maps -0.0 and +0.0 to the same
    # point, which is what "zero representable steps apart" should mean.
    return -(n & (sign - 1)) if n & sign else n


def diff(a: dict, b: dict, kind: str) -> dict:
    """Compare two probe streams under a named contract, and REPORT the numbers.

    `compare` only certifies that two streams may be compared; producing
    `0 / 333 records differ` still needed a separate uncommitted calculation
    (owner P0-E3). This does both, and reports ULP distance rather than only a
    relative difference, because a bitwise claim is a claim about representable
    steps.
    """
    compare(a, b, kind)
    # The ULP LATTICE is named, not inherited from whichever stream was passed
    # first (owner §8.2). `precision = a[("meta","precision")]` made
    # diff(f32, f64) and diff(f64, f32) count steps on different lattices, so the
    # statistic depended on argument order. Across precisions there is no single
    # "max ULP" at all, so the f32 lattice is used and SAID SO in the field name:
    # both values are rounded to f32 first, which is the comparison a
    # precision_pair is actually asking about -- does promoting the arithmetic
    # change the answer at the reference's own resolution.
    same_precision = a[("meta", "precision")] == b[("meta", "precision")]
    lattice = a[("meta", "precision")] if same_precision else "f32"
    keys = sorted(k for k in a if k[0] != "meta")
    worst_abs = worst_rel = 0.0
    worst_ulp, first, ndiff, nbits = 0, None, 0, 0
    for k in keys:
        x, y = a[k], b[k]
        # RAW BITS, separately from numeric equality (owner §8.3). `x == y` is
        # True for +0.0 and -0.0, and `_bits` maps both to the same point, so a
        # pair whose stored patterns differ was reported `bitwise_identical`.
        # "Bitwise" is a certification word; it has to mean the bits.
        if struct.pack(">d", x) != struct.pack(">d", y):
            nbits += 1
        if x == y:
            continue
        ndiff += 1
        if first is None:
            first = {"key": list(k), "a": x, "b": y}
        d = abs(x - y)
        worst_abs = max(worst_abs, d)
        worst_rel = max(worst_rel, d / max(abs(x), abs(y)))
        worst_ulp = max(worst_ulp, abs(_bits(x, lattice) - _bits(y, lattice)))
    out = {"kind": kind, "records": len(keys),
           "equal": len(keys) - ndiff, "different": ndiff,
           "max_abs": worst_abs, "max_rel": worst_rel,
           "ulp_lattice": lattice, f"max_ulp_{lattice}": worst_ulp,
           "first_difference": first,
           # Two different questions, previously one field: are the numbers the
           # same, and are the stored patterns the same.
           "numerically_identical": ndiff == 0,
           "raw_bit_identical": nbits == 0}
    if same_precision:
        out["precision"] = lattice
    return out


def main(argv) -> int:
    """    g33_probe_read.py <stream> [<stream> ...]           # read and validate
    g33_probe_read.py <a> <b> <kind> [out.json]         # compare and report
    """
    if not argv:
        print(__doc__)
        return 2
    if len(argv) >= 3 and argv[2] in COMPARISONS:
        a, b = (read(Path(q).read_text()) for q in argv[:2])
        d = diff(a, b, argv[2])
        print(f"  {argv[2]}: {d['different']} of {d['records']} records differ"
              f"   max_rel={d['max_rel']:.3e}  max_ulp={d['max_ulp']}"
              f"   bitwise_identical={d['bitwise_identical']}")
        if len(argv) == 4:
            import json
            Path(argv[3]).write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")
        return 0
    for path in argv:
        r = read(Path(path).read_text())
        print(f"  {path}: precision={r[('meta','precision')]} "
              f"algorithm={r[('meta','algorithm')]} dtcld={r[('meta','dtcld')]:g} "
              f"records={sum(1 for k in r if k[0] != 'meta')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
