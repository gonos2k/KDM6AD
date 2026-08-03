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
import sys
from pathlib import Path

BEGIN = re.compile(
    r"^G33P BEGIN (\d+) precision (f32|f64) source_precision (f32|f64) "
    r"fixture (\S+) algorithm (\S+) mode (carry|rezero) "
    r"(\d+) (\d+) (\d+) (\S+) (\S+) (\d+) (\d+)$")
END = re.compile(r"^G33P END$")
STATE = re.compile(r"^G33P (STATE|INITIAL) (\S+) (\d+) (-?\d+)\s+(\S+)$")
FORCING = re.compile(r"^G33P FORCING (rho|delz|pii) (\d+) (-?\d+)\s+(\S+)$")
PREC = re.compile(r"^G33P PREC (\d+) (\d+)\s+(\S+)$")

SCHEMA = 2
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
    (schema, precision, source, fixture, algorithm, mode, nsplit, loops,
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
    cells = {(k[2], k[3]) for k in st}
    _expect(len(cells) == int(B) * int(K),
            f"state covers {len(cells)} cells, header declares {B}x{K}")
    per_col = {c: {kk for cc, kk in cells if cc == c} for c, _ in cells}
    _expect(len({tuple(sorted(v)) for v in per_col.values()}) == 1,
            "columns carry different level sets")
    if (init := [k for k in out if k[0] == "initial"]):
        _expect({k[1:] for k in init} == {k[1:] for k in st},
                "INITIAL covers different (field, col, k) than STATE")
    if (fo := [k for k in out if k[0] == "forcing"]):
        names = {k[1] for k in fo}
        _expect(("rho" in names) == ("delz" in names),
                f"forcing carries {sorted(names)}: rho and delz must be together")
        for nm in names:
            _expect({(k[2], k[3]) for k in fo if k[1] == nm} == cells,
                    f"forcing `{nm}` does not cover the state's cells")
    if (pr := [k for k in out if k[0] == "prec"]):
        _expect({(k[1], k[2]) for k in pr}
                == {(sp, c) for sp in (1, 2, 3) for c, _ in cells},
                "prec is not exactly species 1/2/3 over the state's columns")
    out |= {("meta", "schema"): int(schema), ("meta", "precision"): precision,
            ("meta", "source_precision"): source, ("meta", "fixture"): fixture,
            ("meta", "algorithm"): algorithm, ("meta", "mode"): mode,
            ("meta", "nsplit"): int(nsplit), ("meta", "loops"): int(loops),
            ("meta", "ntile"): int(ntile), ("meta", "delt"): _f(delt),
            ("meta", "dtcld"): _f(dtcld)}
    return out


#: What must be IDENTICAL for each kind of comparison, and what must DIFFER.
#: A single `compare` could pair `legacy f32 N=3` with `conservative f64 N=96`
#: purely because their record universes matched (owner P0-5).
COMPARISONS = {
    "precision_pair": (("fixture", "algorithm", "mode", "nsplit", "dtcld"),
                       "precision"),
    "variant":        (("fixture", "precision", "mode", "nsplit", "dtcld"),
                       "algorithm"),
    "refinement":     (("fixture", "algorithm", "mode", "precision"), "dtcld"),
}


def compare(a: dict, b: dict, kind: str) -> None:
    """Two probe streams are comparable only under a NAMED contract.

    `kind` says which one thing may differ; everything else identifying the
    experiment must match. `refinement` additionally allows the record universes
    to differ in nothing but their values, since two steps of one chain describe
    the same grid.
    """
    _expect(kind in COMPARISONS,
            f"unknown comparison {kind!r}; expected one of {sorted(COMPARISONS)}")
    same, differs = COMPARISONS[kind]
    for f in same:
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


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        r = read(Path(path).read_text())
        print(f"  {path}: precision={r[('meta','precision')]} "
              f"records={sum(1 for k in r if k[0] != 'meta')}")
    if len(argv) == 3:
        compare(read(Path(argv[0]).read_text()), read(Path(argv[1]).read_text()),
                argv[2])
        print(f"  comparable under the {argv[2]} contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
