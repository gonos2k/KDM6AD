#!/usr/bin/env python3
"""The mapping fixture must be able to FAIL — public CI, no build.

`boundary_mapping_v1` exists because the two arithmetic fixtures are degenerate in
exactly the places the wrapper->kernel adapter can go wrong. A fixture that cannot
distinguish a correct adapter from a broken one is worse than no fixture: it reports
PASS either way.

So these tests do not check the adapter. They check the FIXTURE — that for each
mapping mistake the adapter could plausibly make, the fixture's own values differ
under the mistake. Each mutation is applied to the authority's bits, in Python,
exactly as the driver's pack would consume them; if a mutation produced identical
bits, the corresponding real bug would be invisible and this file says so.

The mistakes modelled are the ones the kernel-entry adapter actually performs:

    t    = th * pii            dropping pii            (P0-5)
    k    = km - k              a K-flip                (orientation)
    (i,k) indexing             a column transposition  (pack layout)
    qci  = [qc, qi, 0]         swapping the two        (species index)
    qrs  = [qr, qs, qg]        rotating them
    nci  = [nc, ni, nccn]      swapping/rotating
    sea  = xland >= 1.5        an inverted mask        (P0-6)
    ncmin  land vs sea         the wrong constant      (P0-6)
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fixture_v1 as gfx        # noqa: E402

FIXTURE = "boundary_mapping_v1"


def _f32(hexs):
    return struct.unpack(">f", bytes.fromhex(hexs))[0]


@pytest.fixture(scope="module")
def authority():
    return gfx.load_fixture(FIXTURE)[1]


def _grid(authority, name):
    """(col, k) -> value, in the manifest's own top_first layout."""
    B, K = authority["B"], authority["K"]
    vals = authority["fields"][name]
    assert len(vals) == B * K, f"{name} is not a B*K field"
    return {(c, k): _f32(vals[c * K + k]) for c in range(B) for k in range(K)}


# ── the degeneracies this fixture exists to remove ────────────────────────────

def test_pii_is_not_unity_anywhere(authority):
    """With pii == 1 everywhere, `t = th` and `t = th*pii` are the same program."""
    pii = _grid(authority, "pii")
    assert all(v != 1.0 for v in pii.values())
    th = _grid(authority, "th")
    # the mutation: drop pii from the conversion
    correct = {c: th[c] * pii[c] for c in th}
    dropped = dict(th)
    assert correct != dropped, "dropping pii must change every recorded t"
    assert all(correct[c] != dropped[c] for c in correct), (
        "some cell survives dropping pii — that cell cannot catch the bug")


def test_land_and_sea_are_both_present(authority):
    """`xland >= 1.5` is only exercised if both sides of it occur."""
    xland = [_f32(x) for x in authority["xland"]]
    sea = [x >= 1.5 for x in xland]
    assert any(sea) and not all(sea), f"xland={xland} does not mix land and sea"
    # an inverted mask must change WHICH columns are sea
    assert [not s for s in sea] != sea


def test_ncmin_land_and_sea_differ(authority):
    """With them equal, selecting the wrong one is unobservable."""
    p = authority["common_parameters"]
    assert p["ncmin_land"] != p["ncmin_sea"]
    assert _f32(p["ncmin_land"]) != _f32(p["ncmin_sea"])


def test_the_entry_clamp_has_something_to_do(authority):
    """kdm62D pads negatives and caps ni at 1e6 (F:822-839).

    On arithmetic_multisubcycle_v1 that clamp changes 0 of 180 cells, measured — so
    those fixtures cannot tell a working clamp from a deleted one. Here it must fire.
    """
    neg = {n: [v for v in _grid(authority, n).values() if v < 0]
           for n in ("qc", "qi", "qr", "qs", "qg", "nr", "nc", "brs" if
                     "brs" in authority["fields"] else "bg")}
    assert any(neg.values()), f"no negative prognostic to pad: {neg}"
    ni = _grid(authority, "ni")
    assert any(v > 1.0e6 for v in ni.values()), "nothing above the ni cap"
    assert all(v >= 0 for v in ni.values()), "the ni cap test needs a positive value"


def test_nccn_is_distinct_per_column(authority):
    """The wrapper replaces nccn with a height profile. Distinct per column and flat
    in k means the overwrite is unmistakable in the record: k-dependence appears, and
    the column ordering must survive it."""
    nccn = _grid(authority, "nccn")
    B, K = authority["B"], authority["K"]
    per_col = {c: {nccn[(c, k)] for k in range(K)} for c in range(B)}
    assert all(len(s) == 1 for s in per_col.values()), "nccn must be flat in k"
    assert len({s.pop() for s in per_col.values()}) == B, "columns must differ"


# ── orientation and pack mutations ───────────────────────────────────────────

@pytest.mark.parametrize("name", ["pii", "rho", "delz", "th", "qc", "qr", "qi",
                                  "qs", "qg", "nc", "ni", "nr", "bg"])
def test_a_k_flip_changes_the_field(authority, name):
    """Every field except the two anchors must vary in k, or a flipped adapter
    reproduces the correct bits and the orientation claim is untested."""
    K = authority["K"]
    g = _grid(authority, name)
    flipped = {(c, k): g[(c, K - 1 - k)] for (c, k) in g}
    assert g != flipped, f"{name} is symmetric in k — a K-flip is invisible"


@pytest.mark.parametrize("name", ["pii", "rho", "delz", "th", "qc", "qr", "qi",
                                  "qs", "qg", "nc", "ni", "nr", "bg", "nccn"])
def test_a_column_transposition_changes_the_field(authority, name):
    B = authority["B"]
    g = _grid(authority, name)
    rolled = {(c, k): g[((c + 1) % B, k)] for (c, k) in g}
    assert g != rolled, f"{name} is uniform across columns — a swap is invisible"


#: The kernel adapter's species packs, and the mistakes that would keep the SHAPE
#: valid while putting a field in the wrong slot.
_PACKS = {
    "qci": ["qc", "qi"],              # third slot is a literal 0
    "qrs": ["qr", "qs", "qg"],
    "nci": ["nc", "ni", "nccn"],
}


@pytest.mark.parametrize("pack,members", sorted(_PACKS.items()))
def test_every_species_slot_is_distinguishable(authority, pack, members):
    """Two slots holding equal values would make swapping them a no-op."""
    grids = {m: _grid(authority, m) for m in members}
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            assert grids[a] != grids[b], (
                f"{pack}: {a} and {b} are equal, so swapping them is invisible")


def test_the_third_qci_slot_is_not_accidentally_a_real_field(authority):
    """qci(:,:,3) is a literal 0 in the adapter. If some fixture field happened to be
    all-zero, writing it there instead would go unnoticed."""
    for name in authority["fields"]:
        g = _grid(authority, name) if len(authority["fields"][name]) == \
            authority["B"] * authority["K"] else None
        if g is None:
            continue
        assert any(v != 0.0 for v in g.values()), f"{name} is all zero"
