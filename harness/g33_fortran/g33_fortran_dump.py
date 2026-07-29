"""Reader for the standalone-Fortran G3.3-M dump (protocol G33F). The driver
brackets the run with a versioned header + the fixture identity, then the module
overlay emits the sed op ladder, then the driver emits the final state + precip:

  G33F BEGIN v2 <algo>
  G33F FIXIN <field> <col> <k_top> f32 <hex>      # fixture inputs (k=-1 = column scalar)
  G33F PARAM <name> f32 <hex>                      # scalar parameters
  G33F MSTEP <col> i32 <hex>                       # per-column substep count (overlay)
  G33FOP <loop> <chain> <n> <col> <k_top> <op_id> <field> <dtype> <hex>   # overlay
  G33F STAGE <loop> <chain> <stage> <n> <field> <col> <k> <dtype> <hex>   # overlay
  G33F STATE <field> <col> <k_top> f32 <hex>       # final prognostic state (top-first)
  G33F PREC <family> <col> f32 <hex>
  G33F END v2 <algo>

PROTOCOL VERSIONS. The banner selects the record grammar and the two are never
mixed. v1 STAGE records carry no <loop>/<chain>, so the reader derives them under
the single-main-chain-outer-loop scope the v1 overlay emitted; v2 carries the
RUNTIME cloud-subcycle index, which is what makes multi-outer-loop (dt=300)
evidence expressible at all. Both produce the same key shape
(loop, chain, stage, n, field, col, k), so downstream code is version-agnostic.

`bits` is the raw integer of the operand's native bit pattern — f32 (8 hex),
f64 (16 hex) or u8 (2 hex). Top-first k matches the C++ evidence (k=0 TOP). This
module provides the low-level line parsers; the strict fail-closed FortranRun
parser (exact multiset + canonical op_seq) is built on top of these.
"""
import re

_OP = re.compile(
    r"^G33FOP\s+(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\S+)\s+(\S+)\s+"
    r"(f32|f64|u8)\s+([0-9A-Fa-f]+)$")
# v1/v2: G33F MSTEP <col> i32 <hex>   v3: G33F MSTEP <loop> <chain> <col> i32 <hex>
_MSTEP_V1 = re.compile(r"^G33F MSTEP\s+(\d+)\s+i32\s+([0-9A-Fa-f]{8})$")
_MSTEP_V3 = re.compile(r"^G33F MSTEP\s+(\d+)\s+(\S+)\s+(\d+)\s+i32\s+([0-9A-Fa-f]{8})$")
# v1: G33F STAGE <stage> <n> <field> <col> <k> <dtype> <hex>
# v2: G33F STAGE <outer_loop> <chain> <stage> <n> <field> <col> <k> <dtype> <hex>
_STAGE_V1 = re.compile(
    r"^G33F STAGE\s+(\S+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(-?\d+)\s+"
    r"(f32|f64|i32|u8)\s+([0-9A-Fa-f]+)$")
_STAGE_V2 = re.compile(
    r"^G33F STAGE\s+(\d+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(-?\d+)\s+"
    r"(f32|f64|i32|u8)\s+([0-9A-Fa-f]+)$")
# A v1 stream carries no loop/chain, so they are DERIVED from the stage: the overlay
# that emits v1 is scoped to one main-chain outer loop. v2 carries the real values.
_STAGE_CHAIN = {"kernel_call_input": "-", "outer_pre_sed": "-",
                "surface": "-", "substep_pre": "main",
                "outer_post_sed": "-", "outer_post_micro": "-"}
_FIXIN = re.compile(r"^G33F FIXIN\s+(\S+)\s+(\d+)\s+(-?\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
_PARAM = re.compile(r"^G33F PARAM\s+(\S+)\s+f32\s+([0-9A-Fa-f]{8})$")
_LOCALPARAM = re.compile(r"^G33F LOCALPARAM\s+(\S+)\s+f32\s+([0-9A-Fa-f]{8})$")
_STATE = re.compile(r"^G33F STATE\s+(\S+)\s+(\d+)\s+(-?\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^G33F PREC\s+(\d+)\s+(\d+)\s+f32\s+([0-9A-Fa-f]{8})$")
#: Which comparison boundary the run entered at. The wrapper path additionally
#: carries kdm6's preprocessing — the height-dependent CCN profile the C++ port has
#: no counterpart for — so the two are evidence for different questions and must
#: never be compared to each other.
# vocabulary lives in g33_schema (imported below as _schema); re-exported
# here because the parser is also used standalone.
_ENTRY = re.compile(r"^G33F ENTRY (kdm62d_kernel_entry_v1|kdm6_wrapper_input_v1)$")

_BEGIN = re.compile(r"^G33F BEGIN v([123456]) (\S+)$")
_END = re.compile(r"^G33F END v([123456]) (\S+)$")

_HEXWIDTH = {"f32": 8, "f64": 16, "i32": 8, "u8": 2}


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


def parse_localparam(text):
    lp = {}
    for line in text.splitlines():
        m = _LOCALPARAM.match(line)
        if m:
            lp[m.group(1)] = int(m.group(2), 16)
    return lp


def parse_mstep(text, version=1):
    """(loop, chain, col) -> substep count.

    The per-column mstep is recomputed at the start of EACH cloud outer loop from
    that loop's state, so m[L,c] and m[L+1,c] can legitimately differ. v1/v2 do not
    transmit loop/chain, so they fill (1, "main"); v3 carries the real values."""
    ms = {}
    for line in text.splitlines():
        if version >= 3:
            m = _MSTEP_V3.match(line)
            if m:
                ms[(int(m.group(1)), m.group(2), int(m.group(3)))] = int(m.group(4), 16)
        else:
            m = _MSTEP_V1.match(line)
            if m:
                ms[(1, "main", int(m.group(1)))] = int(m.group(2), 16)
    return ms


def parse_stage(text, version=1):
    """(loop, chain, stage, n, field, col, k_top) -> (dtype, bits).

    The key always carries the outer loop and chain so records from different cloud
    subcycles can never collide; a v1 stream, which does not transmit them, has them
    derived from the stage under the single-main-loop scope the v1 overlay emits."""
    st = {}
    for line in text.splitlines():
        if version >= 2:          # v2 introduced loop/chain; v3 keeps it
            m = _STAGE_V2.match(line)
            if not m:
                continue
            loop, chain, stage = int(m.group(1)), m.group(2), m.group(3)
            n, field, col, k = int(m.group(4)), m.group(5), int(m.group(6)), int(m.group(7))
            dtype, hexbits = m.group(8), m.group(9)
        else:
            m = _STAGE_V1.match(line)
            if not m:
                continue
            stage, n, field = m.group(1), int(m.group(2)), m.group(3)
            col, k = int(m.group(4)), int(m.group(5))
            dtype, hexbits = m.group(6), m.group(7)
            loop, chain = 1, _STAGE_CHAIN.get(stage, "-")
        if len(hexbits) != _HEXWIDTH[dtype]:
            raise ValueError(f"{dtype} stage payload width: {line!r}")
        st[(loop, chain, stage, n, field, col, k)] = (dtype, int(hexbits, 16))
    return st


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
import math as _math                # noqa: E402
import os as _os                    # noqa: E402
import struct as _struct            # noqa: E402
import sys as _sys                  # noqa: E402
from dataclasses import dataclass    # noqa: E402

_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
import g33_schema as _schema         # noqa: E402
KERNEL_ENTRY = _schema.KERNEL_ENTRY
WRAPPER_INPUT = _schema.WRAPPER_INPUT
ENTRY_BOUNDARIES = _schema.ENTRY_BOUNDARIES


class FortranRunError(ValueError):
    """A structural/completeness violation in a Fortran G33F run (fail-closed)."""


@dataclass(frozen=True)
class OpRecord:
    op_seq_id: int
    scalar_seq_id: int   # op_seq_id*B + (col-1): the SINGLE cross-tree total order
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
_LOCAL_PARAMS = ("ccn0", "scale_h")   # Fortran-only (no C++ runtime counterpart)


def _signed_i32(u):
    return u - 0x100000000 if u >= 0x80000000 else u


def _f32(bits):
    return _struct.unpack(">f", bits.to_bytes(4, "big"))[0]


def _f64(bits):
    return _struct.unpack(">d", bits.to_bytes(8, "big"))[0]


def _validate_stages(stages, n_raw, mstep, K, B, version=4,
                     entry_boundary=None):
    """Exact pre-sed STAGE universe from mstep + the schema (owner P0-7): once
    outer_pre_sed (n=0) + substep_pre for every substep, dtype-checked and finite."""
    if n_raw != len(stages):
        raise FortranRunError(f"STAGE: {n_raw - len(stages)} duplicate key(s)")
    # one snapshot set PER OUTER LOOP, and one substep set per (loop, chain) sized
    # by THAT scope's own mstep maximum
    scopes = sorted({(lp, ch) for lp, ch, _c in mstep})
    loops = sorted({lp for lp, _ch in scopes})
    carried = _CARRIED_BY_VERSION.get(min(version, 6), ())
    forcings = _FORCINGS_BY_VERSION.get(min(max(version, 4), 6), ())
    pre_sed_fields = ((carried + forcings) if version >= 4
                      else _OUTER_PRE_SED_FIELDS_V3)
    exp = {(L, "-", "outer_pre_sed", 0, f, c, k) for L in loops
           for f in pre_sed_fields for c in range(1, B + 1) for k in range(K)}
    for L, chain in scopes:
        top = max(v for (lp, ch, _c), v in mstep.items() if (lp, ch) == (L, chain))
        for n in range(1, top + 1):
            for c in range(1, B + 1):
                exp |= {(L, chain, "substep_pre", n, f, c, -1)
                        for f in _SUBSTEP_PRE_COL_FIELDS}
                exp |= {(L, chain, "substep_pre", n, f, c, k)
                        for f in _SUBSTEP_PRE_K_FIELDS for k in range(K)}
    exp |= {(L, "-", "surface", 0, f, c, -1) for L in loops
            for f in _SURFACE_FIELDS for c in range(1, B + 1)}
    # The causal bridge: one snapshot set per outer loop at each end of the body.
    # v4 introduced it, so the universe is keyed off the BANNER — an older stream
    # genuinely does not contain these records, and demanding them would report a
    # protocol difference as missing evidence.
    # v6: the ACTUAL kernel-call arguments, before the entry clamp. ONE set per run
    # (loop 0), because a kernel call happens once however many sub-cycles it takes.
    # ...but ONLY on the kernel leg. In wrapper mode the driver calls kdm6, so it
    # never sees the kernel arguments — those are the wrapper CONTRACT's business,
    # measured by a separate gate. Requiring the record of a stream that structurally
    # cannot produce it would report a boundary choice as missing evidence.
    if version >= 6 and entry_boundary == KERNEL_ENTRY:
        exp |= {(0, "-", "kernel_call_input", 0, f, c, k)
                for f in pre_sed_fields for c in range(1, B + 1) for k in range(K)}
    if version >= 4:
        for stage in ("outer_post_sed", "outer_post_micro"):
            exp |= {(L, "-", stage, 0, f, c, k) for L in loops
                    for f in carried for c in range(1, B + 1)
                    for k in range(K)}
    if set(stages) != exp:
        missing, extra = exp - set(stages), set(stages) - exp
        raise FortranRunError(
            f"STAGE universe: {len(missing)} missing (e.g. {next(iter(missing), None)}), "
            f"{len(extra)} extra (e.g. {next(iter(extra), None)})")
    for (_loop, _chain, stage, n, f, c, k), (dt, b) in stages.items():
        if dt != _STAGE_DTYPE[f]:
            raise FortranRunError(f"STAGE {stage}.{f} dtype {dt} != {_STAGE_DTYPE[f]}")
        if dt == "f32" and not _math.isfinite(_f32(b)):
            raise FortranRunError(f"STAGE {stage}.{f} col={c} k={k} not finite")
        if dt == "f64" and not _math.isfinite(_f64(b)):
            raise FortranRunError(f"STAGE {stage}.{f} col={c} k={k} not finite")
        if stage == "surface":                             # bottom fall / metrics
            v = _f32(b)
            if f in ("delz_bottom", "surface_denr") and v <= 0.0:
                raise FortranRunError(f"surface {f} col={c} must be > 0")
            if f not in ("delz_bottom", "surface_denr") and v < 0.0:
                raise FortranRunError(f"surface {f} col={c} must be >= 0")


def _validate_domain(fixin, params, localparams, state, precip, B, K):
    """Every f32 must be finite, and the arithmetic-synthetic input metrics must
    be physically well-formed. A one-line authority edit that produced a NaN or a
    non-positive metric must NOT be certified as a valid run (owner P0-3)."""
    for label, d in (("FIXIN", fixin), ("STATE", state), ("PREC", precip),
                     ("PARAM", params), ("LOCALPARAM", localparams)):
        for key, b in d.items():
            if not _math.isfinite(_f32(b)):
                raise FortranRunError(f"{label} {key} is not finite")
    for name in ("dt", "qmin", "ncmin_land", "ncmin_sea"):
        if _f32(params[name]) <= 0.0:
            raise FortranRunError(f"PARAM {name} must be > 0")
    nonneg = ("qv", "qc", "qr", "qi", "qs", "qg", "bg", "nccn", "nc", "ni", "nr")
    for c in range(1, B + 1):
        for k in range(K):
            for pos in ("rho", "pii", "p", "delz"):
                if _f32(fixin[(pos, c, k)]) <= 0.0:
                    raise FortranRunError(f"FIXIN {pos} col={c} k={k} must be > 0")
            for nn in nonneg:
                if _f32(fixin[(nn, c, k)]) < 0.0:
                    raise FortranRunError(f"FIXIN {nn} col={c} k={k} must be >= 0")
        ps = [_f32(fixin[("p", c, k)]) for k in range(K)]  # top-first: k=0 top
        if any(ps[k] >= ps[k + 1] for k in range(K - 1)):
            raise FortranRunError(f"FIXIN p col={c} not strictly increasing downward: {ps}")
        if _f32(fixin[("xland", c, -1)]) not in (1.0, 2.0):
            raise FortranRunError(f"FIXIN xland col={c} must be 1 or 2")
    for (fam, c), b in precip.items():                     # accumulated precip >= 0
        if _f32(b) < 0.0:
            raise FortranRunError(f"PREC family={fam} col={c} must be >= 0")


@dataclass(frozen=True)
class FortranRun:
    algorithm: str
    #: The G33F banner version this stream was emitted at. Carried because the
    #: PARSER accepts v1-v5 (migration and re-verification of past evidence need
    #: that) while the DECISION path must not: a v4 stream's bridge omits nc/ni/
    #: nccn/brs, so "the sedimentation result matched" would be a claim about
    #: two thirds of the carried state. Without the version on the run, a v4
    #: bundle with valid external anchors reaches verdict_ready.
    protocol_version: int
    entry_boundary: str        # one of ENTRY_BOUNDARIES; absent in pre-v5.1 streams
    K: int
    B: int
    mstep: dict            # (outer_loop, chain, col) -> substep count
    fixture_sha256: str          # over the FIXIN inputs only
    parameter_sha256: str        # over the common PARAM scalars only
    local_parameter_sha256: str  # over the ACTUAL-runtime LOCALPARAM (ccn0/scale_h)
    ops: tuple             # OpRecord, in canonical op_seq order
    stages: dict           # (stage, n, field, col, k) -> (dtype, bits)
    state: dict            # (field, col, k) -> bits
    precip: dict           # (family, col) -> bits
    fixin: dict            # (field, col, k) -> bits
    params: dict           # name -> bits
    localparams: dict      # name -> bits (ccn0, scale_h)


_KNOWN = (_ENTRY, _OP, _MSTEP_V1, _MSTEP_V3, _STAGE_V1, _STAGE_V2, _FIXIN, _PARAM,
          _LOCALPARAM, _STATE, _PREC, _BEGIN, _END)

# pre-sed STAGE field vocabulary (mirrors g33_fortran_bindings; small + stable).
#: The carried state, by protocol version. Keyed rather than versioned by constant
#: name so a new tier is one row, and an older stream is refused for the right reason
#: instead of being reported as missing evidence.
_CARRIED_BY_VERSION = {
    4: ("qr", "nr", "qv", "t", "qc", "qi", "qs", "qg"),
    5: ("qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
        "nc", "ni", "nccn", "brs"),
    6: ("qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
        "nc", "ni", "nccn", "brs"),
}
#: Forcings are keyed the same way, for the same reason. v6 adds `p`: it is a kernel
#: ARGUMENT that enters saturation vapour pressure, the diffusion/thermodynamic
#: coefficients and several process rates, so two backends entering with different
#: pressure would show it only as a rate difference far downstream (owner P0-4).
_FORCINGS_BY_VERSION = {4: ("rho", "delz"), 5: ("rho", "delz"),
                        6: ("p", "rho", "delz")}
_OUTER_PRE_SED_FIELDS = _CARRIED_BY_VERSION[6] + _FORCINGS_BY_VERSION[6]
#: What v3 emitted, kept so a pre-bridge stream still parses and the equivalence
#: proof (a new run reproduces the old sample's shared records exactly) stays
#: possible — that proof is how the bridge is shown not to perturb the run.
_OUTER_PRE_SED_FIELDS_V3 = ("qr", "nr", "qv", "t", "rho", "delz")
#: The outer-loop CAUSAL BRIDGE (owner P0-C1). Every prognostic the loop carries, so
#: that outer_post_micro(L) == outer_pre_sed(L+1) is a bit-for-bit statement about the
#: whole carried state rather than about qr/nr with the rest assumed. Declared here
#: rather than imported from the bindings: a parser that read the emitter's own list
#: would accept whatever the emitter chose to write.
_OUTER_POST_FIELDS = _CARRIED_BY_VERSION[5]
_SUBSTEP_PRE_K_FIELDS = ("qr", "nr", "work1_qr", "workn_qr", "dend_safe", "delz_safe")
_SUBSTEP_PRE_COL_FIELDS = ("mstep", "gate", "dtcld")
_SURFACE_FIELDS = ("bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
                   "bottom_fall_qi", "bottom_fall_total", "delz_bottom",
                   "surface_denr")
_STAGE_DTYPE = {"qr": "f32", "nr": "f32", "qv": "f32", "t": "f32", "rho": "f32",
                # v6: pressure, a kernel argument rather than a carried prognostic
                "p": "f32",
                "delz": "f32", "work1_qr": "f64", "workn_qr": "f64",
                # the carried species the bridge adds
                "qc": "f32", "qi": "f32", "qs": "f32", "qg": "f32",
                "nc": "f32", "ni": "f32", "nccn": "f32", "brs": "f32",
                "dend_safe": "f32", "delz_safe": "f32",
                "mstep": "i32", "gate": "u8", "dtcld": "f32",
                **{f: "f32" for f in _SURFACE_FIELDS}}


def _expected_op_universe(algo, K, B, mstep):
    """(observed-key Counter target, key->op_seq_id map) derived from the schedule
    the mstep implies + the schema — NOT from the observed records."""
    from collections import Counter
    # One schedule PER (outer_loop, chain): each cloud subcycle recomputes its own
    # per-column mstep, so its substep count is its own max — deriving a single
    # global mstepmax would demand records the later loops never produce.
    scopes = sorted({(lp, ch) for lp, ch, _c in mstep})
    want, seq = Counter(), {}
    for loop, chain in scopes:
        cols = {c: v for (lp, ch, c), v in mstep.items() if (lp, ch) == (loop, chain)}
        sched = {"case_id": "fortran", "pair_id": "fortran", "backend": "fortran",
                 "algorithm": algo, "B": B, "K": K, "loops": 1,
                 "mstepmax_main": [max(cols.values())], "mstepmax_ice": [1],
                 "species_scope": ["qr", "nr"], "qcrmin": 1e-9, "dtcld": 20.0,
                 "instrumented_stages": ["op"]}
        for r in _schema.expected_records(sched):
            if r["stage"] != "op":
                continue
            seq[(loop, chain, r["n"], r["k"], r["op_id"], r["field"], r["dtype"])] = \
                r["op_seq_id"]
            for col in range(1, B + 1):        # per-column gate: n <= mstep[col]
                if r["n"] <= cols[col]:
                    want[(loop, chain, r["n"], col, r["k"],
                          r["op_id"], r["field"], r["dtype"])] += 1
    return want, seq


def parse_fortran_run(text, algo, K, B, evidence_mode="instrumented"):
    """Strict fail-closed parse. evidence_mode 'instrumented' (the dump build C)
    requires the MSTEP + op ladder; 'noninstrumented' (A canonical / B macro-off)
    requires ZERO mstep + ZERO ops. Both require the same bracketed, exact-universe,
    finite, domain-valid FIXIN/PARAM/LOCALPARAM/STATE/PREC — so A/B are held to the
    SAME parser surface as C (owner P0-2), never a loose collector."""
    from collections import Counter
    if evidence_mode not in ("instrumented", "noninstrumented"):
        raise ValueError(f"bad evidence_mode {evidence_mode!r}")
    lines = text.splitlines()
    begin_ms = [m for line in lines if (m := _BEGIN.match(line))]
    versions = {int(m.group(1)) for m in begin_ms}
    begins = [m.group(2) for m in begin_ms]
    end_ms = [m for line in lines if (m := _END.match(line))]
    ends = [m.group(2) for m in end_ms]
    if begins != [algo]:
        raise FortranRunError(f"expected exactly one 'G33F BEGIN v* {algo}', got {begins}")
    if ends != [algo]:
        raise FortranRunError(f"expected exactly one 'G33F END v* {algo}', got {ends}")
    # the banner selects the record grammar; a mixed or disagreeing pair is refused
    # so a v1 stream can never be read with the v2 field positions or vice versa.
    if versions != {int(m.group(1)) for m in end_ms} or len(versions) != 1:
        raise FortranRunError(f"BEGIN/END protocol versions disagree: {versions}")
    version = versions.pop()

    entries = [m.group(1) for line in lines if (m := _ENTRY.match(line))]
    if len(entries) > 1:
        raise FortranRunError(f"stream declares {len(entries)} entry boundaries")
    # A pre-v5.1 stream carries none; it is a WRAPPER run by construction, since the
    # kernel path did not exist. Defaulting is safe here and only here.
    entry = entries[0] if entries else WRAPPER_INPUT

    # every G33F-prefixed line MUST match a known record — never silently skipped.
    for line in lines:
        if line.startswith("G33F") and not any(p.match(line) for p in _KNOWN):
            raise FortranRunError(f"malformed/unknown G33F line: {line!r}")

    # BRACKETING: the whole stream must be BEGIN, then FIXIN/PARAM, then
    # MSTEP/OP, then STATE/PREC, then END — no stale append or spliced run.
    def _phase(line):
        # ENTRY belongs with BEGIN: it declares WHICH boundary this stream is
        # evidence for, before any of that evidence appears.
        if _BEGIN.match(line) or _ENTRY.match(line):
            return 0
        if _FIXIN.match(line) or _PARAM.match(line) or _LOCALPARAM.match(line):
            return 1
        if (_MSTEP_V1.match(line) or _MSTEP_V3.match(line) or _OP.match(line)
                or _STAGE_V1.match(line) or _STAGE_V2.match(line)):
            return 2
        if _STATE.match(line) or _PREC.match(line):
            return 3
        return 4                                      # _END
    phases = [_phase(line) for line in lines if line.startswith("G33F")]
    if phases != sorted(phases):
        raise FortranRunError("G33F records out of phase order "
                              "(BEGIN < FIXIN/PARAM < MSTEP/OP < STATE/PREC < END)")

    _mstep_re = _MSTEP_V3 if version >= 3 else _MSTEP_V1
    n_mstep_raw = sum(1 for line in lines if _mstep_re.match(line))
    raw_ops = parse_ops(text)

    if evidence_mode == "noninstrumented":
        if n_mstep_raw or raw_ops:
            raise FortranRunError(
                f"noninstrumented run must emit no MSTEP/OP, got "
                f"{n_mstep_raw} MSTEP + {len(raw_ops)} op records")
        mstep, ops = {}, ()
    else:
        # MSTEP: exactly B records (no duplicate/stale), each a SIGNED int32 in
        # [1,100] (the Fortran cap), covering columns 1..B.
        mstep_raw = parse_mstep(text, version)
        mstep = {key: _signed_i32(w) for key, w in mstep_raw.items()}
        scopes = sorted({(loop, chain) for loop, chain, _c in mstep})
        if not scopes:
            raise FortranRunError("instrumented run emitted no MSTEP records")
        if n_mstep_raw != B * len(scopes):
            raise FortranRunError(
                f"MSTEP has {n_mstep_raw} records, expected {B} per (loop,chain) "
                f"over {len(scopes)} scope(s)")
        for loop, chain in scopes:               # every scope covers columns 1..B
            cols = {c for (lp, ch, c) in mstep if (lp, ch) == (loop, chain)}
            if cols != set(range(1, B + 1)):
                raise FortranRunError(
                    f"MSTEP loop{loop}/{chain} must cover columns 1..{B}, got {sorted(cols)}")
        for key, v in mstep.items():
            if not (1 <= v <= 100):
                raise FortranRunError(f"mstep{key}={v} out of [1,100]")

        _, seq = _expected_op_universe(algo, K, B, mstep)
        obs = Counter()
        for o in raw_ops:
            scope = (o["loop"], o["chain"], o["col"])
            if scope not in mstep:
                raise FortranRunError(f"op has no MSTEP for loop/chain/col: {o}")
            if not (1 <= o["col"] <= B):
                raise FortranRunError(f"op col out of range 1..{B}: {o}")
            if not (0 <= o["k"] <= K - 1):
                raise FortranRunError(f"op k out of range 0..{K-1}: {o}")
            if not (1 <= o["n"] <= mstep[scope]):
                raise FortranRunError(f"op n out of gate 1..mstep{scope}: {o}")
            obs[(o["loop"], o["chain"], o["n"], o["col"], o["k"],
                 o["op"], o["field"], o["dtype"])] += 1
        want, _ = _expected_op_universe(algo, K, B, mstep)
        if obs != want:
            missing, extra = want - obs, obs - want
            raise FortranRunError(
                f"op multiset != expected universe: {sum(missing.values())} missing "
                f"(e.g. {next(iter(missing), None)}), {sum(extra.values())} extra "
                f"(e.g. {next(iter(extra), None)})")

        # RAW ORDER: each (col,n,k) cell's op rungs must be a CONTIGUOUS block. The
        # physical emission is deterministic but NOT canonical op_seq order (legacy
        # emits the nr update before qr, top before interior); within a cell the
        # field order is not verdict authority — the comparator re-keys every rung
        # by its canonical op_seq. Contiguity is the integrity invariant and it
        # rejects a rung moved out of its cell, a spliced run, or an interleaved
        # second stream. Phase-order + this catch the meaningful reorderings.
        # The cell key includes the OUTER LOOP and chain: the same (col,n,k) recurs
        # once per cloud subcycle, so a global contiguity rule would reject a valid
        # multi-loop stream. Contiguity is required WITHIN a scope.
        seen_cells, prev_cell = set(), None
        for o in raw_ops:
            cell = (o["loop"], o["chain"], o["col"], o["n"], o["k"])
            if cell != prev_cell:
                if cell in seen_cells:
                    raise FortranRunError(f"op records for cell {cell} are not contiguous")
                seen_cells.add(cell)
                prev_cell = cell

        # SCALAR canonical order: op_seq_id OUTER, column lane INNER — the single
        # total order both trees scalarize to (C++ carries a [B] payload per
        # logical record; a column-first order would pick a different first diff).
        ops = tuple(sorted(
            (OpRecord(op_seq_id=(sid := seq[(o["loop"], o["chain"], o["n"], o["k"],
                                             o["op"], o["field"], o["dtype"])]),
                      scalar_seq_id=sid * B + (o["col"] - 1),
                      loop=o["loop"], chain=o["chain"], n=o["n"], col=o["col"], k=o["k"],
                      cell_role=cell_role(o["k"], K), species=species_of(o["op"]),
                      op_id=o["op"], field=o["field"], dtype=o["dtype"], bits=o["bits"])
             for o in raw_ops),
            key=lambda r: r.scalar_seq_id))

    stages = parse_stage(text, version)
    _stage_re = _STAGE_V2 if version >= 2 else _STAGE_V1
    n_stage_raw = sum(1 for line in lines if _stage_re.match(line))
    if evidence_mode == "noninstrumented":
        if n_stage_raw:
            raise FortranRunError(f"noninstrumented run emitted {n_stage_raw} STAGE records")
    else:
        _validate_stages(stages, n_stage_raw, mstep, K, B, version, entry)

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
    _require_names(params, _COMMON_PARAMS, _PARAM, lines, "PARAM")
    localparams = parse_localparam(text)
    _require_names(localparams, _LOCAL_PARAMS, _LOCALPARAM, lines, "LOCALPARAM")
    _validate_domain(fixin, params, localparams, state, precip, B, K)

    def _sha(s):
        return _hashlib.sha256(s.encode()).hexdigest()

    fixture_sha256 = _sha("".join(
        f"{f}:{c}:{k}:{b:08x}" for (f, c, k), b in sorted(fixin.items())))
    parameter_sha256 = _sha("".join(f"{n}:{b:08x}" for n, b in sorted(params.items())))
    local_parameter_sha256 = _sha(
        "".join(f"{n}:{b:08x}" for n, b in sorted(localparams.items())))

    return FortranRun(algorithm=algo, protocol_version=version, entry_boundary=entry, K=K, B=B, mstep=mstep,
                      fixture_sha256=fixture_sha256, parameter_sha256=parameter_sha256,
                      local_parameter_sha256=local_parameter_sha256,
                      ops=ops, stages=stages, state=state, precip=precip, fixin=fixin,
                      params=params, localparams=localparams)


def _require_names(parsed, expected, pattern, lines, label):
    n_raw = sum(1 for line in lines if pattern.match(line))
    if n_raw != len(parsed):
        raise FortranRunError(f"{label}: {n_raw - len(parsed)} duplicate key(s)")
    if set(parsed) != set(expected):
        raise FortranRunError(f"{label} names {sorted(parsed)} != {sorted(expected)}")


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
