"""Reader for the standalone-Fortran G3.3-M dump (the four-case comparator's
Fortran-side input). Parses the driver's stdout into:

  ops:   list of {col, k, n, op, field, bits}  from `G33OP <i> <k> <n> <op.field> <hex8>`
  state: {(field, i, k): bits}                  from `FLD <name> <i> <k> <hex8>`
  prec:  {(family, i): bits}                    from `PREC <f> <i> <hex8>`

`bits` is the raw uint32 (int) of the operand-domain f32 value — the same
representation the C++ .g33 payloads carry, so the comparator can compare
Fortran and C++ at the operation domain.
"""
import re

_OP = re.compile(r"^G33OP\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+?)\.(\S+)\s+([0-9A-Fa-f]{8})$")
_FLD = re.compile(r"^FLD\s+(\S.*?)\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^PREC\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")


def parse_ops(text):
    out = []
    for line in text.splitlines():
        m = _OP.match(line)
        if m:
            out.append({"col": int(m.group(1)), "k": int(m.group(2)),
                        "n": int(m.group(3)), "op": m.group(4),
                        "field": m.group(5), "bits": int(m.group(6), 16)})
    return out


def parse_state(text):
    st = {}
    for line in text.splitlines():
        m = _FLD.match(line)
        if m:
            st[(m.group(1).strip(), int(m.group(2)), int(m.group(3)))] = int(m.group(4), 16)
    return st


def parse_prec(text):
    pr = {}
    for line in text.splitlines():
        m = _PREC.match(line)
        if m:
            pr[(int(m.group(1)), int(m.group(2)))] = int(m.group(3), 16)
    return pr
