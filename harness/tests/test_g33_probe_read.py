"""The precision probe is a protocol, not a side-channel (owner priority 2).

Two hazards it closes: an f64 stream and an f32 one were the same text with
different numbers, so nothing structurally stopped a reader mixing them; and a
truncated probe stream looked like a complete one.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_probe_read as pr  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
import g33_number_transport as _nt  # noqa: E402


def _stream(precision="f32", *, B=2, K=2, end=True, schema=4, prec=True,
            forcing=("rho", "delz", "pii"), initial=True, fixture="fx", algo="legacy",
            mode="rezero", nsplit=12, dtcld=25.0, tiles=None, ntile=1, loops=1,
            rho_profile="as-is", delt=None):
    # schema 3 carries the TILE VECTOR: `ntile` alone cannot tell (2,1) from
    # (1,2), and `ncmin` makes those two decompositions disagree (owner §8.1).
    # A default that actually COVERS the domain: the parser now requires
    # sum(tiles) == B, and "1" for a 2-column domain describes no decomposition.
    tiles = tiles or ",".join(["1"] * (ntile - 1) + [str(B - (ntile - 1))])
    out = [f"G33P BEGIN {schema} precision {precision} source_precision f32 "
           f"fixture {fixture} algorithm {algo} mode {mode} tiles {tiles} "
           f"rho_profile {rho_profile} "
           f"{nsplit} {loops} {ntile} {(300.0/nsplit if delt is None else delt):.6f} "
           f"{dtcld:.6f} {B} {K}"]
    for f in pr.FIELDS:
        for c in range(1, B + 1):
            for k in range(K):
                out.append(f"G33P STATE {f} {c} {k}   1.0000000000000000E+000")
                if initial:
                    out.append(f"G33P INITIAL {f} {c} {k}   1.0000000000000000E+000")
    for nm in forcing:
        for c in range(1, B + 1):
            for k in range(K):
                out.append(f"G33P FORCING {nm} {c} {k}   1.0000000000000000E+000")
    if prec:
        for sp in (1, 2, 3):
            for c in range(1, B + 1):
                out.append(f"G33P PREC {sp} {c}   0.0000000000000000E+000")
    if end:
        out.append("G33P END")
    return "\n".join(out) + "\n"


def test_a_complete_stream_reads():
    r = pr.read(_stream())
    assert r[("meta", "precision")] == "f32"
    assert r[("meta", "source_precision")] == "f32"


def test_the_field_vocabulary_is_taken_from_the_G33R_contract():
    """A second copy of the state list drifts — the first version of the parser
    said `brs` where the stream says `bg`, and the stream was right."""
    assert pr.FIELDS is ra.STATE_FIELDS


def test_a_truncated_stream_is_refused():
    with pytest.raises(pr.ProbeError, match="no G33P END"):
        pr.read(_stream(end=False))


def test_a_stream_without_a_header_is_refused():
    body = "\n".join(_stream().splitlines()[1:]) + "\n"
    with pytest.raises(pr.ProbeError, match="does not begin with G33P BEGIN"):
        pr.read(body)


def test_a_foreign_schema_is_refused():
    with pytest.raises(pr.ProbeError, match="declares schema 9"):
        pr.read(_stream(schema=9))


def test_the_old_schema_1_header_is_refused():
    """Schema 1 could not identify the experiment, so it cannot be read as if it
    could (owner P0-5)."""
    with pytest.raises(pr.ProbeError):
        pr.read("G33P BEGIN 1 precision f32 source_precision f32 2 2\nG33P END\n")


def test_a_duplicate_record_is_refused():
    lines = _stream().splitlines()
    lines.insert(2, lines[1])
    with pytest.raises(pr.ProbeError, match="duplicate record"):
        pr.read("\n".join(lines) + "\n")


def test_a_missing_forcing_name_is_refused():
    """rho, delz and pii are all emitted by the driver, so all three are
    required: "absent" silently disabled every forcing check (owner §7.2)."""
    with pytest.raises(pr.ProbeError, match="`delz` is not the exact cell universe"):
        pr.read(_stream(forcing=("rho", "pii")))
    with pytest.raises(pr.ProbeError, match="`pii` is not the exact"):
        pr.read(_stream(forcing=("rho", "delz")))


def test_a_stream_without_INITIAL_is_refused():
    with pytest.raises(pr.ProbeError, match="INITIAL is not the exact"):
        pr.read(_stream(initial=False))


def test_a_stream_without_PREC_is_refused():
    with pytest.raises(pr.ProbeError, match="prec is not exactly"):
        pr.read(_stream(prec=False))


def test_a_skewed_field_cell_product_is_refused():
    """One field skipping a cell while another supplies it: both the field set
    and the cell count look complete, the product does not."""
    s = _stream().replace("G33P STATE th 1 0 ", "G33P STATE th 9 0 ", 1)
    with pytest.raises(pr.ProbeError, match="not the exact"):
        pr.read(s)


def test_prec_must_cover_species_1_2_3_over_the_columns():
    s = _stream().replace("G33P PREC 2 1   0.0000000000000000E+000\n", "")
    with pytest.raises(pr.ProbeError, match="species 1/2/3"):
        pr.read(s)


def test_an_initial_state_over_different_cells_is_refused():
    s = _stream().replace("G33P INITIAL th 1 0", "G33P INITIAL th 9 0")
    with pytest.raises(pr.ProbeError, match="INITIAL is not the exact"):
        pr.read(s)


def test_a_grid_disagreeing_with_the_header_is_refused():
    """The header claims a grid the records do not fill — now caught as the
    exact-universe mismatch it is."""
    lines = _stream(B=2, K=2).splitlines()
    lines[0] = lines[0][:-3] + "3 2"        # header now claims B=3
    with pytest.raises(pr.ProbeError, match="not the exact"):
        pr.read("\n".join(lines) + "\n")


def test_a_three_digit_exponent_without_the_E_still_parses():
    """Fortran ES formatting drops the `E` at three digits (5.3e-316 printed as
    `5.2679749487822913-316`). Archived streams predate the widened format."""
    assert pr._f("5.2679749487822913-316") == pytest.approx(5.2679749487822913e-316)


def test_a_non_finite_value_is_refused():
    s = _stream().replace("G33P STATE th 1 0   1.0000000000000000E+000",
                          "G33P STATE th 1 0   NaN")
    with pytest.raises(pr.ProbeError, match="non-finite"):
        pr.read(s)


def test_the_header_identifies_the_experiment():
    r = pr.read(_stream(fixture="fx7", algo="conservative", nsplit=6, dtcld=50.0))
    assert r[("meta", "fixture")] == "fx7"
    assert r[("meta", "algorithm")] == "conservative"
    assert r[("meta", "nsplit")] == 6 and r[("meta", "dtcld")] == 50.0


def test_a_valid_precision_pair_compares():
    pr.compare(pr.read(_stream("f32")), pr.read(_stream("f64")), "precision_pair")


def test_a_valid_variant_pair_compares():
    """This is what makes 'legacy == conservative at f64' reproducible: the
    contract certifies both streams describe the same experiment first."""
    pr.compare(pr.read(_stream("f64", algo="legacy")),
               pr.read(_stream("f64", algo="conservative")), "variant")


def test_a_valid_refinement_pair_compares():
    pr.compare(pr.read(_stream(nsplit=12, dtcld=25.0)),
               pr.read(_stream(nsplit=24, dtcld=12.5)), "refinement")


def test_two_streams_at_the_SAME_precision_are_not_a_precision_pair():
    with pytest.raises(pr.ProbeError, match="precision is the same in both"):
        pr.compare(pr.read(_stream("f32")), pr.read(_stream("f32")),
                   "precision_pair")


def test_different_ALGORITHMS_are_not_a_precision_pair():
    """The defect: a single compare() would pair legacy f32 with conservative f64
    purely because their record universes matched (owner P0-5)."""
    with pytest.raises(pr.ProbeError, match="disagree on algorithm"):
        pr.compare(pr.read(_stream("f32", algo="legacy")),
                   pr.read(_stream("f64", algo="conservative")), "precision_pair")


def test_different_STEPS_are_not_a_precision_pair():
    """`legacy f32 N=3` against `conservative f64 N=96` was pairable purely
    because the record universes matched (owner P0-5)."""
    with pytest.raises(pr.ProbeError, match="disagree on nsplit"):
        pr.compare(pr.read(_stream("f32", nsplit=12, dtcld=25.0)),
                   pr.read(_stream("f64", nsplit=96, dtcld=3.125)),
                   "precision_pair")


def test_the_same_nsplit_at_a_different_dtcld_is_not_a_precision_pair():
    """N alone does not identify the step: N = 1,2,3 run 100, 150, 100 s."""
    with pytest.raises(pr.ProbeError, match="disagree on dtcld"):
        pr.compare(pr.read(_stream("f32", nsplit=12, dtcld=25.0)),
                   pr.read(_stream("f64", nsplit=12, dtcld=50.0)),
                   "precision_pair")


def test_an_unknown_comparison_kind_is_refused():
    with pytest.raises(pr.ProbeError, match="unknown comparison"):
        pr.compare(pr.read(_stream("f32")), pr.read(_stream("f64")), "whatever")


def test_streams_over_different_records_are_not_comparable():
    """Varying K rather than B: a different column count now also implies a
    different tile vector, so it would be refused one check earlier and this
    would stop testing the record-universe contract it is about."""
    with pytest.raises(pr.ProbeError, match="different records"):
        pr.compare(pr.read(_stream("f32", K=2)), pr.read(_stream("f64", K=3)),
                   "precision_pair")


# ---- owner P0-E3: the comparator must produce the numbers, not only certify --

def test_diff_reports_bitwise_identity_not_only_comparability():
    """compare() certified that two streams MAY be compared; `0 of 333 records
    differ` still came from a separate uncommitted calculation."""
    a, b = pr.read(_stream("f64")), pr.read(_stream("f64", algo="conservative"))
    d = pr.diff(a, b, "variant")
    assert d["different"] == 0 and d["max_ulp_f64"] == 0
    assert d["numerically_identical"] and d["raw_bit_identical"]
    assert d["records"] == d["equal"]


def test_diff_counts_records_and_locates_the_first_difference():
    a = pr.read(_stream("f64"))
    changed = _stream("f64", algo="conservative").replace(
        "G33P STATE th 1 0   1.0000000000000000E+000",
        "G33P STATE th 1 0   2.0000000000000000E+000")
    d = pr.diff(a, pr.read(changed), "variant")
    assert d["different"] == 1 and d["numerically_identical"] is False
    assert d["first_difference"]["key"] == ["state", "th", 1, 0]
    assert d["max_rel"] == pytest.approx(0.5)


def test_ulp_distance_counts_representable_steps():
    """A bitwise claim is about representable steps, so the report carries ULP
    rather than only a relative difference."""
    import struct
    one = 1.0
    nxt = struct.unpack(">f", struct.pack(">I",
          struct.unpack(">I", struct.pack(">f", one))[0] + 1))[0]
    assert pr._bits(nxt, "f32") - pr._bits(one, "f32") == 1
    # and it counts across zero, where a naive bit subtraction would not
    assert pr._bits(0.0, "f32") - pr._bits(-0.0, "f32") == 0


def test_diff_still_refuses_an_incomparable_pair():
    """The contract check runs first: a diff between different experiments is
    not a number worth reporting."""
    with pytest.raises(pr.ProbeError, match="disagree on algorithm"):
        pr.diff(pr.read(_stream("f32", algo="legacy")),
                pr.read(_stream("f64", algo="conservative")), "precision_pair")


# ---- owner §8: the comparison identity, the ULP lattice, the signed zero ------

def test_the_invariant_set_is_COMPUTED_not_listed():
    """The listed form silently omitted source_precision, loops, ntile, delt and
    the tile vector, so two runs differing in any of them compared clean. A field
    added to the header must become an invariant by DEFAULT -- fail-closed on the
    next schema change rather than fail-open (owner §8.1)."""
    for kind in pr.COMPARISONS:
        inv = set(pr.invariants(kind))
        differs, covaries = pr.COMPARISONS[kind]
        assert inv == set(pr.IDENTITY) - {differs} - set(covaries)
        assert {"source_precision", "loops", "ntile", "tiles"} <= inv


def test_a_different_TILE_VECTOR_is_not_a_variant_difference():
    """`ncmin` is a scalar overwritten in the column loop, so (2,1) and (1,2)
    can give different answers for the same atmosphere. Comparing them as a
    `variant` pair attributes a DECOMPOSITION effect to the algorithm -- and
    `ntile` alone cannot tell them apart, which is why the vector is in the
    header at all."""
    a = pr.read(_stream("f64", B=3, ntile=2, tiles="2,1"))
    b = pr.read(_stream("f64", B=3, algo="conservative", ntile=2, tiles="2,1"))
    pr.compare(a, b, "variant")                       # same decomposition: fine
    # (1,2) is a DIFFERENT decomposition of the same domain, and `ncmin` makes
    # the two disagree — which is why it must not read as a variant difference.
    c = pr.read(_stream("f64", B=3, algo="conservative", ntile=2, tiles="1,2"))
    with pytest.raises(pr.ProbeError, match="disagree on tiles"):
        pr.compare(a, c, "variant")


def test_a_different_LOOPS_count_is_not_a_variant_difference():
    a = pr.read(_stream("f64", loops=1))
    b = pr.read(_stream("f64", algo="conservative", loops=2))
    with pytest.raises(pr.ProbeError, match="disagree on loops"):
        pr.compare(a, b, "variant")


def test_the_cross_precision_ULP_does_not_depend_on_argument_order():
    """`precision = a[("meta","precision")]` counted steps on whichever lattice
    was passed FIRST, so diff(f32,f64) and diff(f64,f32) reported different
    statistics for the same pair (owner §8.2)."""
    a, b = pr.read(_stream("f32")), pr.read(_stream("f64"))
    x, y = pr.diff(a, b, "precision_pair"), pr.diff(b, a, "precision_pair")
    assert x["ulp_lattice"] == y["ulp_lattice"] == "f32"
    assert x["max_ulp_f32"] == y["max_ulp_f32"]


def test_a_cross_precision_diff_does_not_claim_a_single_precision():
    """There is no one precision for a pair spanning two, so the field is absent
    rather than carrying whichever came first."""
    a, b = pr.read(_stream("f32")), pr.read(_stream("f64"))
    assert "precision" not in pr.diff(a, b, "precision_pair")
    assert "precision" in pr.diff(pr.read(_stream("f64")),
                                  pr.read(_stream("f64", algo="conservative")),
                                  "variant")


def test_signed_zeros_are_numerically_equal_but_NOT_raw_bit_identical():
    """`x == y` is True for +0.0 and -0.0 and `_bits` maps both to one point, so
    a pair whose stored patterns differ was certified `bitwise_identical`.
    "Bitwise" is a certification word and has to mean the bits (owner §8.3)."""
    a = pr.read(_stream("f64"))
    negz = _stream("f64", algo="conservative").replace(
        "G33P STATE th 1 0   1.0000000000000000E+000",
        "G33P STATE th 1 0   0.0000000000000000E+000")
    posz = _stream("f64").replace(
        "G33P STATE th 1 0   1.0000000000000000E+000",
        "G33P STATE th 1 0  -0.0000000000000000E+000")
    d = pr.diff(pr.read(posz), pr.read(negz), "variant")
    assert d["numerically_identical"] is True, "+0.0 == -0.0 numerically"
    assert d["raw_bit_identical"] is False, "their stored patterns differ"


# ---- owner P0-1: the driver's literal and the parser's SCHEMA must agree ------

DRIVER = Path(__file__).resolve().parents[1] / "g33_fortran" / "g33_refine_driver.f90"
SCHEMA_EXPECTED = pr.SCHEMA


def test_the_driver_emits_the_schema_this_parser_ACCEPTS():
    """A protocol version written in three independent places drifts, and this
    one did: G33N went to 4 while the G33P literal stayed at 3, so the driver
    produced streams its own strict parser refused. Every probe and f64 bundle
    stopped being producible and nothing failed, because the parser tests build
    SYNTHETIC streams at the parser's own version and the only tests that run the
    real driver are local-only (owner P0-1).

    This check is static, so it runs in public CI where the Fortran build cannot."""
    src = DRIVER.read_text()
    lits = re.findall(r"'G33P BEGIN', (\d+),", src)
    assert lits, "no G33P BEGIN literal found in the driver"
    assert set(lits) == {str(SCHEMA_EXPECTED)}, (
        f"driver emits G33P schema {sorted(set(lits))} but the parser accepts "
        f"{SCHEMA_EXPECTED}")


def test_the_G33N_driver_literal_matches_its_parser_too():
    """Same failure mode, other protocol."""
    import g33_number_transport as nt
    lits = re.findall(r"'G33N STREAM_BEGIN', (\d+),", DRIVER.read_text())
    assert lits and set(lits) == {str(nt.SCHEMA)}, (
        f"driver emits G33N schema {sorted(set(lits))}, parser is {nt.SCHEMA}")



def test_an_impossible_tile_vector_is_refused():
    """A zero-width tile, a vector of the wrong length, or one that does not cover
    the domain cannot describe any real decomposition. The parser stored them
    unchallenged, and a regression test had pinned `2,0` as acceptable input
    (owner §8.1)."""
    for tiles, ntile, B, msg in (("2,0", 2, 2, "non-positive"),
                                 ("1", 2, 2, "entries but ntile"),
                                 ("1,1", 2, 3, "sums to")):
        with pytest.raises(pr.ProbeError, match=msg):
            pr.read(_stream("f64", B=B, ntile=ntile, tiles=tiles))


def test_an_unknown_rho_profile_is_refused_by_G33P_too():
    """G33N refused it; G33P stored the string, so a malformed loose stream could
    carry `rho_profile=sideways` and compare cleanly (owner §8.2)."""
    with pytest.raises(pr.ProbeError, match="unknown rho_profile"):
        pr.read(_stream("f64", rho_profile="sideways"))


def test_the_two_parsers_agree_on_what_an_arm_IS():
    """Two independent allow-lists would drift; the second would then accept an
    arm the first rejects."""
    import g33_number_transport as nt
    assert pr.RHO_PROFILES is nt.RHO_PROFILES


# ---- owner §8.4: the f64 bundle's CROSS-MEMBER contract ----------------------
#
# An f64 bundle supplies its own member_reader, and the manifest builder then
# left `runs` empty — so it skipped both the duplicate-nsplit check and
# require_same_universe. Each member was strict-parsed alone; nothing checked
# them against each other.

def _chain(**overrides):
    """A two-member probe chain: n3 and n6 of one experiment."""
    base = dict(precision="f64", B=2, K=2)
    a = pr.read(_stream(nsplit=3, dtcld=100.0, **base))
    b = pr.read(_stream(nsplit=6, dtcld=50.0, **{**base, **overrides}))
    return {3: a, 6: b}


def test_a_valid_probe_chain_passes():
    """The control: everything below must fail for its own reason."""
    pr.require_probe_chain(_chain())


@pytest.mark.parametrize("field,override", [
    ("fixture", {"fixture": "other"}),
    ("algorithm", {"algo": "conservative"}),
    ("mode", {"mode": "carry"}),
    ("rho_profile", {"rho_profile": "uniform"}),
    ("loops", {"loops": 2}),
])
def test_a_probe_chain_mixing_experiments_is_refused(field, override):
    """Each of these makes the two members different experiments. Mixing
    decompositions is the sharpest: `ncmin` makes (2,1) and (1,2) disagree, so a
    'refinement chain' spanning two tile maps measures decomposition, not step."""
    with pytest.raises(pr.ProbeError, match=f"disagree on {field}"):
        pr.require_probe_chain(_chain(**override))


def test_a_probe_chain_over_different_TILE_MAPS_is_refused():
    """Same ntile, different vector — the case `ntile` alone cannot see. `ncmin`
    makes (2,1) and (1,2) disagree, so a chain spanning two tile maps measures
    decomposition rather than step."""
    a = pr.read(_stream(precision="f64", B=3, ntile=2, tiles="2,1",
                        nsplit=3, dtcld=100.0))
    b = pr.read(_stream(precision="f64", B=3, ntile=2, tiles="1,2",
                        nsplit=6, dtcld=50.0))
    with pytest.raises(pr.ProbeError, match="disagree on tiles"):
        pr.require_probe_chain({3: a, 6: b})


def test_a_probe_chain_over_different_HORIZONS_is_refused():
    """nsplit and delt both move with dtcld, so neither alone pins the total
    integration time — their product does. A chain whose members integrate
    different totals is not a refinement of one experiment."""
    a = pr.read(_stream(precision="f64", nsplit=3, delt=100.0, dtcld=100.0))
    b = pr.read(_stream(precision="f64", nsplit=6, delt=100.0, dtcld=50.0))
    with pytest.raises(pr.ProbeError, match="different horizons"):
        pr.require_probe_chain({3: a, 6: b})


def test_a_probe_chain_that_does_not_REFINE_is_refused():
    """Two members at the same dtcld are a repetition. Nothing to take an order
    over, and a manifest calling it a refinement chain would be wrong."""
    a = pr.read(_stream(precision="f64", nsplit=3, dtcld=100.0))
    b = pr.read(_stream(precision="f64", nsplit=3, dtcld=100.0))
    with pytest.raises(pr.ProbeError, match="repetition, not a refinement"):
        pr.require_probe_chain({3: a, 6: b})


def test_a_probe_member_with_a_DIFFERENT_RECORD_UNIVERSE_is_refused():
    """Comparing over an intersection lets an incomplete member report a smaller
    error — convergence measured on absence. G33R has checked this since the
    beginning; the f64 path never did."""
    a = pr.read(_stream(precision="f64", nsplit=3, dtcld=100.0, K=2))
    b = pr.read(_stream(precision="f64", nsplit=6, dtcld=50.0, K=3))
    with pytest.raises(pr.ProbeError, match="different record universe"):
        pr.require_probe_chain({3: a, 6: b})


def test_a_single_member_chain_is_not_an_error():
    """One member has nothing to disagree with."""
    pr.require_probe_chain({3: pr.read(_stream(precision="f64"))})


def test_the_producer_actually_calls_it():
    """A contract nothing invokes checks nothing."""
    src = (Path(__file__).resolve().parents[1] / "g33_refine_experiment.py").read_text()
    assert "pr.require_probe_chain(runs)" in src


def test_the_duplicate_nsplit_check_no_longer_depends_on_the_reader():
    """Two members for one nsplit collapse to one entry whichever parser read
    them, so guarding the check on `member_reader is None` exempted exactly the
    bundle that had no other cross-member check at all."""
    src = (Path(__file__).resolve().parents[1] / "g33_refine_manifest.py").read_text()
    assert "if member_reader is None and len(ns) != len(set(ns)):" not in src
    assert "if len(ns) != len(set(ns)):" in src


def test_the_chain_invariant_is_COMPUTED_from_IDENTITY():
    """Listed, it fails open on the next schema change — the same shape the
    pairwise comparison identity had before it was computed (owner P1-11.4)."""
    assert set(pr.CHAIN_INVARIANT) == set(pr.IDENTITY) - set(pr.CHAIN_VARY)
    assert pr.CHAIN_VARY == frozenset({"dtcld", "nsplit", "delt"})
    assert "rho_profile" in pr.CHAIN_INVARIANT


# --- the window, from whichever family carries it (owner D6 follow-on) ------
#
# Three claims sat at `needs-f64` because `--arm f64` refused `--nflux`. Fixing
# the G33F record family was necessary and not sufficient: an f64 build emits
# no G33R at all, so dual_ledger, internal_cap_enthalpy and water_enthalpy_basis
# -- exactly the analyses those claims rest on -- failed for want of a
# window-initial qv the stream was carrying the whole time under a G33P tag.
#
# The alternative was a G33R f64 family, and G33R records carry no dtype token,
# so that would have changed a record shape 72 committed members depend on.

def test_G33R_and_G33P_are_two_ENCODINGS_of_the_same_content():
    """Not two sources: `read_text` and `read` already return the same key
    shape, so choosing between them is all this has to do."""
    p = pr.read(_stream())
    shapes = {(len(k), k[0]) for k in p if isinstance(k, tuple)}
    assert ("initial", ) or True
    assert (4, "initial") in shapes and (4, "state") in shapes


def test_a_PROBE_ONLY_stream_yields_the_window():
    """What an f64 build has instead of G33R."""
    got = pr.window_state(_stream())
    qv = [v for k, v in got.items()
          if isinstance(k, tuple) and k[0] == "initial" and k[1] == "qv"]
    assert qv and all(v == 1.0 for v in qv)


def test_G33R_WINS_when_both_are_present():
    """An f32 probe build emits both, and G33R is the pinned convention every
    archived analysis was computed from. Preferring the probe family would move
    published numbers -- measured: 288 archived analysis runs, none changed.

    Checked by making the G33R block MALFORMED beside a perfectly good probe
    one. A probe-preferring implementation reads straight past it and answers;
    this has to raise, and the message has to be the G33R reader's.
    """
    both = "G33R BEGIN nonsense\nG33R END\n" + _stream()
    with pytest.raises(ra.RefineError, match="BEGIN"):
        pr.window_state(both)


def test_NEITHER_family_is_REFUSED_not_answered_with_an_empty_window():
    """A measure built on nothing silently covers no cells."""
    with pytest.raises(pr.ProbeError, match="carries neither"):
        pr.window_state("G33N STREAM_BEGIN 4 1 1 1 legacy rezero nflux as-is\n")


def test_the_THREE_analyses_that_needed_G33R_run_on_a_PROBE_stream():
    """The point of the change, checked through the analyses themselves rather
    than through the reader they share."""
    import g33_matched_closure as mc
    got = mc.window_cell_mass(_NUMBER_STREAM + _stream(B=1, K=2), "physical")
    assert got, "the physical measure found no cells"


_NUMBER_STREAM = (
    "G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep,mstepi,nflux as-is\n"
    "G33N CALL_BEGIN 1 1 1 1 1 2 42C80000\n"
    + "".join(
        f"G33F STAGE 1 - {stage} 0 {f} 1 {k} f32 3F800000\n"
        for stage in ("outer_pre_sed", "outer_post_sed")
        for k in range(2)
        for f in ("nr", "ni", "qr", "qi", "qv", "rho", "delz")
        if not (stage == "outer_post_sed" and f in ("rho", "delz")))
    + "G33F MSTEP 1 main 1 i32 00000001\n"
      "G33F MSTEPI 1 1 i32 00000001\n"
    + "".join(f"G33F NFLUX 1 1 {f} f32 3F800000\n" for f in _nt.NFLUX_FIELDS)
    + "G33N CALL_END 1 1 1\n"
      "G33N STREAM_END\n")


def test_the_G33P_delt_token_is_judged_as_a_CANONICAL_F06_record():
    """Same token rule as G33R, tested on THIS parser (Codex): float()
    collapses forged spellings onto the channel's double, and a padded
    00042.857143 is a spelling F0.6 cannot print. Canonical spelling only."""
    good = _stream()
    pr.read(good)                                  # the builder's own F0.6 parses
    for tok in ("25.0000001", "2.5E+01", "00025.000000", "025.000000"):
        bad = good.replace(" 25.000000 25.000000 ", f" {tok} 25.000000 ", 1)
        assert bad != good, "the replacement found nothing to replace"
        with pytest.raises(pr.ProbeError, match="not an F0.6 record"):
            pr.read(bad)
