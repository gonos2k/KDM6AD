#!/usr/bin/env python3
"""Strict reader for the G33P precision-probe stream (owner priority 2).

The probe was a side-channel: decimal records with no framing, no precision
declared, and no parser of its own. Two hazards followed. An f64 stream and an
f32 one are the same text with different numbers, so nothing structurally stopped
a reader mixing them; and an incomplete probe stream looked like a complete one.

    G33P BEGIN <schema> precision <f32|f64> source_precision <f32> <B> <K>
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

BEGIN = re.compile(r"^G33P BEGIN (\d+) precision (f32|f64) source_precision "
                   r"(f32|f64) (\d+) (\d+)$")
END = re.compile(r"^G33P END$")
STATE = re.compile(r"^G33P (STATE|INITIAL) (\S+) (\d+) (-?\d+)\s+(\S+)$")
FORCING = re.compile(r"^G33P FORCING (rho|delz|pii) (\d+) (-?\d+)\s+(\S+)$")
PREC = re.compile(r"^G33P PREC (\d+) (\d+)\s+(\S+)$")

SCHEMA = 1
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
    schema, precision, source, B, K = m.groups()
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
    out[("meta", "schema")] = int(schema)
    out[("meta", "precision")] = precision
    out[("meta", "source_precision")] = source
    return out


def compare(a: dict, b: dict) -> None:
    """Two probe streams may be compared only if they describe the same run."""
    for field in ("source_precision",):
        _expect(a[("meta", field)] == b[("meta", field)],
                f"streams disagree on {field}")
    _expect(a[("meta", "precision")] != b[("meta", "precision")],
            "a precision pair needs two different precisions; these are both "
            f"{a[('meta', 'precision')]}")
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
    if len(argv) == 2:
        compare(read(Path(argv[0]).read_text()), read(Path(argv[1]).read_text()))
        print("  comparable: same grid, same source precision, two precisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
