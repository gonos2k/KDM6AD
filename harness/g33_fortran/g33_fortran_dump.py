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


# ── strict, fail-closed run parser (owner P0-1) ───────────────────────────────
# One parser that consumes the whole G33F stream and refuses anything incomplete
# or malformed: exact-MULTISET op completeness against a universe derived
# INDEPENDENTLY from the per-column mstep + the schema (not from counting the ops
# themselves), canonical op_seq_id from schema.expected_records, unique keys,
# in-range indices, exactly one BEGIN/END. A missing record, a duplicate, a
# whole cell/column/substep dropped, a reordered or malformed line all raise.
import hashlib as _hashlib          # noqa: E402
import os as _os                    # noqa: E402
import sys as _sys                  # noqa: E402
from dataclasses import dataclass    # noqa: E402

_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
import g33_schema as _schema         # noqa: E402


class FortranRunError(ValueError):
    """A structural/completeness violation in a Fortran G33F run (fail-closed)."""


@dataclass(frozen=True)
class OpRecord:
    op_seq_id: int
    loop: int
    chain: str
    n: int
    col: int
    k: int
    cell_role: str
    species: str
    op_id: str
    field: str
    dtype: str
    bits: int


# The exact field universes the driver emits (fail-closed against these).
_STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                 "nccn", "nc", "ni", "nr", "bg")
_FIXIN_FIELDS = _STATE_FIELDS + ("rho", "pii", "p", "delz")
_COMMON_PARAMS = ("dt", "ncmin_land", "ncmin_sea", "qmin")


def _signed_i32(u):
    return u - 0x100000000 if u >= 0x80000000 else u


@dataclass(frozen=True)
class FortranRun:
    algorithm: str
    K: int
    B: int
    mstep: dict            # col -> substep count
    fixture_sha256: str    # over the FIXIN inputs only
    parameter_sha256: str  # over the PARAM scalars only
    ops: tuple             # OpRecord, in canonical op_seq order
    state: dict            # (field, col, k) -> bits
    precip: dict           # (family, col) -> bits
    fixin: dict            # (field, col, k) -> bits
    params: dict           # name -> bits


_KNOWN = (_OP, _MSTEP, _FIXIN, _PARAM, _STATE, _PREC, _BEGIN, _END)


def _expected_op_universe(algo, K, B, mstep):
    """(observed-key Counter target, key->op_seq_id map) derived from the schedule
    the mstep implies + the schema — NOT from the observed records."""
    from collections import Counter
    max_mstep = max(mstep.values())
    sched = {"case_id": "fortran", "pair_id": "fortran", "backend": "fortran",
             "algorithm": algo, "B": B, "K": K, "loops": 1,
             "mstepmax_main": [max_mstep], "mstepmax_ice": [1],
             "species_scope": ["qr", "nr"], "qcrmin": 1e-9, "dtcld": 20.0,
             "instrumented_stages": ["op"]}
    want = Counter()
    seq = {}
    for r in _schema.expected_records(sched):
        if r["stage"] != "op":
            continue
        key_bk = (r["n"], r["k"], r["op_id"], r["field"], r["dtype"])
        seq[key_bk] = r["op_seq_id"]
        for col in range(1, B + 1):            # per-column: gate n<=mstep[col]
            if r["n"] <= mstep[col]:
                want[(r["n"], col, r["k"], r["op_id"], r["field"], r["dtype"])] += 1
    return want, seq


def parse_fortran_run(text, algo, K, B):
    from collections import Counter
    lines = text.splitlines()
    begins = [m.group(1) for line in lines if (m := _BEGIN.match(line))]
    ends = [m.group(1) for line in lines if (m := _END.match(line))]
    if begins != [algo]:
        raise FortranRunError(f"expected exactly one 'G33F BEGIN v1 {algo}', got {begins}")
    if ends != [algo]:
        raise FortranRunError(f"expected exactly one 'G33F END v1 {algo}', got {ends}")

    # every G33F-prefixed line MUST match a known record — never silently skipped.
    for line in lines:
        if line.startswith("G33F") and not any(p.match(line) for p in _KNOWN):
            raise FortranRunError(f"malformed/unknown G33F line: {line!r}")

    # BRACKETING: the whole stream must be BEGIN, then FIXIN/PARAM, then
    # MSTEP/OP, then STATE/PREC, then END — no stale append or spliced run.
    def _phase(line):
        if _BEGIN.match(line):
            return 0
        if _FIXIN.match(line) or _PARAM.match(line):
            return 1
        if _MSTEP.match(line) or _OP.match(line):
            return 2
        if _STATE.match(line) or _PREC.match(line):
            return 3
        return 4                                      # _END
    phases = [_phase(line) for line in lines if line.startswith("G33F")]
    if phases != sorted(phases):
        raise FortranRunError("G33F records out of phase order "
                              "(BEGIN < FIXIN/PARAM < MSTEP/OP < STATE/PREC < END)")

    # MSTEP: a SIGNED int32 in [1, 100] (the Fortran mstep cap), one per column.
    mstep_raw = parse_mstep(text)
    if set(mstep_raw) != set(range(1, B + 1)):
        raise FortranRunError(f"MSTEP must cover columns 1..{B}, got {sorted(mstep_raw)}")
    mstep = {c: _signed_i32(w) for c, w in mstep_raw.items()}
    for c, v in mstep.items():
        if not (1 <= v <= 100):
            raise FortranRunError(f"mstep[{c}]={v} out of [1,100]")

    raw_ops = parse_ops(text)
    _, seq = _expected_op_universe(algo, K, B, mstep)
    obs = Counter()
    for o in raw_ops:
        if o["loop"] != 1 or o["chain"] != "main":
            raise FortranRunError(f"op loop/chain must be 1/main: {o}")
        if not (1 <= o["col"] <= B):
            raise FortranRunError(f"op col out of range 1..{B}: {o}")
        if not (0 <= o["k"] <= K - 1):
            raise FortranRunError(f"op k out of range 0..{K-1}: {o}")
        if not (1 <= o["n"] <= mstep[o["col"]]):
            raise FortranRunError(f"op n out of gate 1..mstep[{o['col']}]: {o}")
        obs[(o["n"], o["col"], o["k"], o["op"], o["field"], o["dtype"])] += 1

    want, _ = _expected_op_universe(algo, K, B, mstep)
    if obs != want:
        missing, extra = want - obs, obs - want
        raise FortranRunError(
            f"op multiset != expected universe: {sum(missing.values())} missing "
            f"(e.g. {next(iter(missing), None)}), {sum(extra.values())} extra "
            f"(e.g. {next(iter(extra), None)})")

    # RAW ORDER: each (col, n, k) cell's op records must be a CONTIGUOUS block in
    # the stream — a producer may not scatter a cell's rungs across the run. (The
    # physical emission order is deterministic but not the canonical op_seq order:
    # legacy emits the nr update before the qr update, and the top cell before the
    # interior loop; within one cell the field order is irrelevant because the
    # comparator keys every rung by its canonical op_seq. So contiguity — not
    # global monotonicity — is the integrity invariant, and it catches any record
    # moved out of its cell, a spliced run, or an interleaved second stream.)
    seen_cells = set()
    prev_cell = None
    for o in raw_ops:
        cell = (o["col"], o["n"], o["k"])
        if cell != prev_cell:
            if cell in seen_cells:
                raise FortranRunError(f"op records for cell {cell} are not contiguous")
            seen_cells.add(cell)
            prev_cell = cell

    ops = tuple(sorted(
        (OpRecord(op_seq_id=seq[(o["n"], o["k"], o["op"], o["field"], o["dtype"])],
                  loop=o["loop"], chain=o["chain"], n=o["n"], col=o["col"], k=o["k"],
                  cell_role=cell_role(o["k"], K), species=species_of(o["op"]),
                  op_id=o["op"], field=o["field"], dtype=o["dtype"], bits=o["bits"])
         for o in raw_ops),
        key=lambda r: (r.col, r.op_seq_id)))

    state = parse_state(text)
    exp_state = {(f, c, k) for f in _STATE_FIELDS
                 for c in range(1, B + 1) for k in range(K)}
    _require_exact(state, exp_state, _STATE, text, "STATE")
    precip = parse_prec(text)
    exp_prec = {(fam, c) for fam in (1, 2, 3) for c in range(1, B + 1)}
    _require_exact(precip, exp_prec, _PREC, text, "PREC")
    fixin = parse_fixin(text)
    exp_fixin = {(f, c, k) for f in _FIXIN_FIELDS
                 for c in range(1, B + 1) for k in range(K)}
    exp_fixin |= {("xland", c, -1) for c in range(1, B + 1)}
    _require_exact(fixin, exp_fixin, _FIXIN, text, "FIXIN")
    params = parse_param(text)
    n_param_raw = sum(1 for line in lines if _PARAM.match(line))
    if n_param_raw != len(params):
        raise FortranRunError(f"PARAM: {n_param_raw - len(params)} duplicate key(s)")
    if set(params) != set(_COMMON_PARAMS):
        raise FortranRunError(f"PARAM names {sorted(params)} != {sorted(_COMMON_PARAMS)}")

    fx = "".join(f"{f}:{c}:{k}:{b:08x}" for (f, c, k), b in sorted(fixin.items()))
    pr = "".join(f"{n}:{b:08x}" for n, b in sorted(params.items()))
    fixture_sha256 = _hashlib.sha256(fx.encode()).hexdigest()
    parameter_sha256 = _hashlib.sha256(pr.encode()).hexdigest()

    return FortranRun(algorithm=algo, K=K, B=B, mstep=mstep,
                      fixture_sha256=fixture_sha256, parameter_sha256=parameter_sha256,
                      ops=ops, state=state, precip=precip, fixin=fixin, params=params)


def _require_exact(parsed, expected, pattern, text, label):
    """No duplicate keys (dicts silently overwrite) AND the key set is EXACTLY
    the expected universe — missing / extra / wrong-index all fail."""
    n_raw = sum(1 for line in text.splitlines() if pattern.match(line))
    if n_raw != len(parsed):
        raise FortranRunError(f"{label}: {n_raw - len(parsed)} duplicate key(s)")
    if set(parsed) != expected:
        missing, extra = expected - set(parsed), set(parsed) - expected
        raise FortranRunError(
            f"{label}: {len(missing)} missing (e.g. {next(iter(missing), None)}), "
            f"{len(extra)} extra (e.g. {next(iter(extra), None)})")


def verify_offline_replay(run):
    """Prove the ACTUAL stored update (q_post/n_post) equals an offline replay
    from the dumped operands — the actual↔shadow causal link (owner P0-6).

    q_post is the STORED qrs after the update; the pre-clamp value
    (q_plus_in_preclamp interior / q_minus_out top) is an independent shadow
    recompute from the operands. Bit-exact: conservative has no clamp so
    q_post == preclamp; legacy clamps to zero so q_post == preclamp if >0 else 0.
    A mutated ACTUAL update (shadows unchanged) breaks this and RAISES.
    """
    import struct

    def f32(b):
        return struct.unpack(">f", b.to_bytes(4, "big"))[0]

    by = {}
    for r in run.ops:
        by.setdefault((r.col, r.k, r.n), {})[(r.op_id, r.field)] = r.bits
    checked = 0
    for (col, k, n), d in by.items():
        for upd, pre_in, pre_out, post in (
                ("QR_UPDATE", "q_plus_in_preclamp", "q_minus_out", "q_post"),
                ("NR_UPDATE", "n_plus_in_preclamp", "n_minus_out", "n_post")):
            if (upd, post) not in d:
                continue
            preclamp = d.get((upd, pre_in), d.get((upd, pre_out)))
            if preclamp is None:
                raise FortranRunError(f"{upd} col={col} k={k} n={n}: no pre-clamp operand")
            actual = d[(upd, post)]
            expect = preclamp if (run.algorithm != "legacy" or f32(preclamp) > 0.0) \
                else 0x00000000
            if actual != expect:
                raise FortranRunError(
                    f"offline-replay mismatch {upd} col={col} k={k} n={n}: stored "
                    f"q_post {actual:08x} != replay {expect:08x} (actual update "
                    f"diverges from its dumped operands)")
            checked += 1
    if checked == 0:
        raise FortranRunError("offline replay checked 0 updates — no q_post/n_post")
    return checked
