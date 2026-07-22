"""Reader for the standalone-Fortran G3.3-M dump (the four-case comparator's
Fortran-side input). Parses the driver's stdout into:

  ops:   list of {col, k, n, op, field, dtype, bits}
                                          from `G33OP <i> <k> <n> <op.field> <dtype> <hex>`
  state: {(field, i, k): bits}            from `FLD <name> <i> <k> <hex8>`
  prec:  {(family, i): bits}              from `PREC <f> <i> <hex8>`

`bits` is the raw integer of the operand's native bit pattern — f32 (8 hex),
f64 (16 hex) or u8 (2 hex, the 0/1 branch flag). This is the same representation
the C++ .g33 payloads carry, so the comparator's normalizer can compare Fortran
and C++ at the operation domain, keyed by (op_id, field, dtype).
"""
import re

_OP = re.compile(
    r"^G33OP\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+?)\.(\S+)\s+(f32|f64|u8)\s+([0-9A-Fa-f]+)$")
_FLD = re.compile(r"^FLD\s+(\S.*?)\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^PREC\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")

_HEXWIDTH = {"f32": 8, "f64": 16, "u8": 2}


def parse_ops(text):
    out = []
    for line in text.splitlines():
        m = _OP.match(line)
        if m:
            dtype, hexbits = m.group(6), m.group(7)
            if len(hexbits) != _HEXWIDTH[dtype]:
                raise ValueError(
                    f"{dtype} payload must be {_HEXWIDTH[dtype]} hex, got "
                    f"{len(hexbits)!r}: {line!r}")
            out.append({"col": int(m.group(1)), "k": int(m.group(2)),
                        "n": int(m.group(3)), "op": m.group(4),
                        "field": m.group(5), "dtype": dtype,
                        "bits": int(hexbits, 16)})
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
