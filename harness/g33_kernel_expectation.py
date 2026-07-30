#!/usr/bin/env python3
"""What the kernel SHOULD have been called with, computed from the fixture alone.

Every cross-backend check so far asks whether the two legs agree:

    M_F(x) == M_C(x)

which passes when both adapters are wrong the same way. That is not a remote
possibility — both were written from the same source reading, by the same person, in the
same week. So the fixture needs an expectation of its own:

    M_F(x) == M_expected(x)
    M_C(x) == M_expected(x)

and only then does agreement between them mean anything.

Two mappings are checked, and both are computed here from the raw fixture words with no
reference to any backend's output:

  wrapper -> kernel call arguments   `t = f32(th * pii)`, `brs = bg`, the rest identity
  entry padding                      the exact clamps at module_mp_kdm6.F:850-864

Deliberately NOT a re-derivation of the reference in general — it is a transcription of
two small, closed, fully specified transforms. Anything larger belongs in the replay
machinery, which works from dumped operands rather than from a second implementation.
"""
from __future__ import annotations

import struct

#: `nccn` is clamped into a band, not floored (module_mp_kdm6.F:859), and `ni` is capped
#: at 1e6 (:862). Written as the source writes them so the transcription is checkable by
#: eye against those lines.
NCCN_MIN, NCCN_MAX = 1.0e8, 2.0e10
NI_MAX = 1.0e6


def f32(word: str) -> float:
    """A fixture hex word as the float32 the Fortran `transfer` produces."""
    return struct.unpack(">f", bytes.fromhex(word))[0]


def bits(value: float) -> int:
    """Round to float32 and return the raw bits, which is what the streams carry."""
    return struct.unpack(">I", struct.pack(">f", value))[0]


def _fl32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def expected_call_input(authority: dict) -> dict:
    """(field, col, k) -> bits, for the 15 `kernel_call_input` records.

    col is 1-based and k is TOP-FIRST, matching the streams. The manifest's field arrays
    are already top-first and laid out row-major over (col, k).
    """
    B, K = authority["B"], authority["K"]
    F = authority["fields"]

    def cell(name, c, k):
        return f32(F[name][c * K + k])

    out = {}
    for c in range(B):
        for k in range(K):
            # THE ONE COMPUTATION. Everything else at this boundary is a copy or a
            # rename, so this is the only place a mapping can be arithmetically wrong —
            # and with pii == 1 (as in both arithmetic fixtures) dropping it is
            # invisible, which is why boundary_mapping_v1 exists.
            t = _fl32(cell("th", c, k) * cell("pii", c, k))
            direct = {
                "qv": cell("qv", c, k), "qc": cell("qc", c, k),
                "qi": cell("qi", c, k), "qr": cell("qr", c, k),
                "qs": cell("qs", c, k), "qg": cell("qg", c, k),
                "nc": cell("nc", c, k), "ni": cell("ni", c, k),
                "nccn": cell("nccn", c, k), "nr": cell("nr", c, k),
                # a RENAME across the call: the state calls the graupel volume `bg`,
                # the kernel argument is `brs`
                "brs": cell("bg", c, k),
                "p": cell("p", c, k), "rho": cell("rho", c, k),
                "delz": cell("delz", c, k),
                "t": t,
            }
            for name, value in direct.items():
                out[(name, c + 1, k)] = bits(value)
    return out


#: What the entry padding does to each field, as a function of the value. Fields absent
#: from this map must be BITWISE UNCHANGED — the padding is a closed world, and a clamp
#: that quietly touched `qv` or `t` would be a defect the fixture should catch.
_PADDING = {
    "qc": lambda v: max(v, 0.0),                       # F:850
    "qr": lambda v: max(v, 0.0),                       # F:851
    "qi": lambda v: max(v, 0.0),                       # F:852
    "qs": lambda v: max(v, 0.0),                       # F:853
    "qg": lambda v: max(v, 0.0),                       # F:854
    "nr": lambda v: max(v, 0.0),                       # F:855 (nrs(:,:,1))
    "nc": lambda v: max(v, 0.0),                       # F:858 (nci(:,:,1))
    "nccn": lambda v: min(max(v, NCCN_MIN), NCCN_MAX),  # F:859
    "ni": lambda v: min(max(v, 0.0), NI_MAX),          # F:862
    "brs": lambda v: max(v, 0.0),                      # F:864
}
UNCHANGED_BY_PADDING = ("qv", "t", "p", "rho", "delz")


def expected_after_padding(call_input: dict) -> dict:
    """Apply the entry padding to a recorded `kernel_call_input`.

    Takes the RECORDED call input rather than the fixture, so a padding mismatch is
    attributed to the padding and not to the mapping that produced its input — the two
    are separate claims and conflating them would report one failure as the other.
    """
    out = {}
    for (name, col, k), b in call_input.items():
        fn = _PADDING.get(name)
        out[(name, col, k)] = b if fn is None else bits(_fl32(fn(f32("%08x" % b))))
    return out


#: The ONE field the wrapper is authorized to rewrite before calling the kernel: it
#: replaces the incoming nccn with a height-dependent CCN profile
#: (module_mp_kdm6.F:318-329). Everything else must arrive at the kernel exactly as the
#: fixture supplied it, and stating that as a CLOSED WORLD is what turns "we found an
#: nccn difference" into "nccn is the only difference there is".
WRAPPER_MAY_CHANGE = frozenset(("nccn",))


def allowed_to_differ(entry_boundary: str, kernel_entry_id: str) -> frozenset:
    """Which fields may differ from the fixture-derived expectation, by boundary.

    At the kernel entry: none. The adapter's whole job is to hand the kernel the
    fixture's own state, so any difference is an adapter defect.

    At the wrapper input: exactly WRAPPER_MAY_CHANGE. A wrapper that changed anything
    else, or that left nccn alone, would both be findings.
    """
    return frozenset() if entry_boundary == kernel_entry_id else WRAPPER_MAY_CHANGE


def compare(got: dict, want: dict, *, limit: int = 8, ignore=()) -> list:
    """Cells where `got` differs from `want`, plus any key only one side has."""
    bad = [(k, got.get(k), want.get(k)) for k in sorted(got.keys() | want.keys())
           if k[0] not in ignore and got.get(k) != want.get(k)]
    return bad[:limit] if limit else bad
