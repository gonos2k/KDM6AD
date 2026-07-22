"""Reader for the standalone-Fortran G3.3-M dump (protocol G33F). The driver
brackets the run with a versioned header + the fixture identity, then the module
overlay emits the sed op ladder, then the driver emits the final state + precip:

  G33F BEGIN v1 <algo>
  G33F FIXIN <field> <col> <k_top> f32 <hex>      # fixture inputs (k=-1 = column scalar)
  G33F PARAM <name> f32 <hex>                      # scalar parameters
  G33F MSTEP <col> i32 <hex>                       # per-column substep count (overlay)
  G33FOP <loop> <chain> <n> <col> <k_top> <op_id> <field> <dtype> <hex>   # overlay
  G33F STATE <field> <col> <k_top> f32 <hex>       # final prognostic state (top-first)
  G33F PREC <family> <col> f32 <hex>
  G33F END v1 <algo>

`bits` is the raw integer of the operand's native bit pattern — f32 (8 hex),
f64 (16 hex) or u8 (2 hex). Top-first k matches the C++ evidence (k=0 TOP). This
module provides the low-level line parsers; the strict fail-closed FortranRun
parser (exact multiset + canonical op_seq) is built on top of these.
"""
import re

_OP = re.compile(
    r"^G33FOP\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\S+)\s+(\S+)\s+"
    r"(f32|f64|u8)\s+([0-9A-Fa-f]+)$")
_MSTEP = re.compile(r"^G33F MSTEP\s+(\d+)\s+i32\s+([0-9A-Fa-f]{8})$")
_FIXIN = re.compile(r"^G33F FIXIN\s+(\S+)\s+(\d+)\s+(-?\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
_PARAM = re.compile(r"^G33F PARAM\s+(\S+)\s+f32\s+([0-9A-Fa-f]{8})$")
_STATE = re.compile(r"^G33F STATE\s+(\S+)\s+(\d+)\s+(-?\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^G33F PREC\s+(\d+)\s+(\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
_BEGIN = re.compile(r"^G33F BEGIN v1 (\S+)$")
_END = re.compile(r"^G33F END v1 (\S+)$")

_HEXWIDTH = {"f32": 8, "f64": 16, "u8": 2}


def parse_ops(text):
    out = []
    for line in text.splitlines():
        m = _OP.match(line)
        if m:
            dtype, hexbits = m.group(8), m.group(9)
            if len(hexbits) != _HEXWIDTH[dtype]:
                raise ValueError(
                    f"{dtype} payload must be {_HEXWIDTH[dtype]} hex: {line!r}")
            out.append({"loop": int(m.group(1)), "chain": m.group(2),
                        "n": int(m.group(3)), "col": int(m.group(4)),
                        "k": int(m.group(5)), "op": m.group(6),
                        "field": m.group(7), "dtype": dtype,
                        "bits": int(hexbits, 16)})
    return out


def parse_state(text):
    st = {}
    for line in text.splitlines():
        m = _STATE.match(line)
        if m:
            st[(m.group(1), int(m.group(2)), int(m.group(3)))] = int(m.group(4), 16)
    return st


def parse_prec(text):
    pr = {}
    for line in text.splitlines():
        m = _PREC.match(line)
        if m:
            pr[(int(m.group(1)), int(m.group(2)))] = int(m.group(3), 16)
    return pr


def parse_fixin(text):
    fx = {}
    for line in text.splitlines():
        m = _FIXIN.match(line)
        if m:
            fx[(m.group(1), int(m.group(2)), int(m.group(3)))] = int(m.group(4), 16)
    return fx


def parse_param(text):
    pm = {}
    for line in text.splitlines():
        m = _PARAM.match(line)
        if m:
            pm[m.group(1)] = int(m.group(2), 16)
    return pm


def parse_mstep(text):
    ms = {}
    for line in text.splitlines():
        m = _MSTEP.match(line)
        if m:
            ms[int(m.group(1))] = int(m.group(2), 16)
    return ms


# ── canonicalization for the four-case comparator ─────────────────────────────
# Mirror g33_expectation._cell_role (canonical top-first) + the QR_/NR_ split.
def cell_role(k, K):
    if k == 0:
        return "TOP"
    if k == K - 1:
        return "BOTTOM"
    return "INTERIOR"


def species_of(op_id):
    fam = op_id.split("_", 1)[0]
    try:
        return {"QR": "qr", "NR": "nr"}[fam]
    except KeyError:
        raise ValueError(f"unknown op family in {op_id!r}") from None


def to_records(text, K):
    """Parsed ops enriched with cell_role + species — the logical fields the
    comparator keys on. `col` (Fortran i, 1-based) maps to the C++ per-record
    [B] payload lane (col-1)."""
    return [{**o, "cell_role": cell_role(o["k"], K), "species": species_of(o["op"])}
            for o in parse_ops(text)]
