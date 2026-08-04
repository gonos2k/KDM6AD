"""The precision probe is a protocol, not a side-channel (owner priority 2).

Two hazards it closes: an f64 stream and an f32 one were the same text with
different numbers, so nothing structurally stopped a reader mixing them; and a
truncated probe stream looked like a complete one.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_probe_read as pr  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402


def _stream(precision="f32", *, B=2, K=2, end=True, schema=3, prec=True,
            forcing=("rho", "delz", "pii"), initial=True, fixture="fx", algo="legacy",
            mode="rezero", nsplit=12, dtcld=25.0, tiles=None, ntile=1, loops=1):
    # schema 3 carries the TILE VECTOR: `ntile` alone cannot tell (2,1) from
    # (1,2), and `ncmin` makes those two decompositions disagree (owner §8.1).
    tiles = tiles or ",".join(["1"] * ntile)
    out = [f"G33P BEGIN {schema} precision {precision} source_precision f32 "
           f"fixture {fixture} algorithm {algo} mode {mode} tiles {tiles} "
           f"{nsplit} {loops} {ntile} {300.0/nsplit:.6f} {dtcld:.6f} {B} {K}"]
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
    with pytest.raises(pr.ProbeError, match="different records"):
        pr.compare(pr.read(_stream("f32", B=2)), pr.read(_stream("f64", B=3)),
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
    a = pr.read(_stream("f64", ntile=2, tiles="1,1"))
    b = pr.read(_stream("f64", algo="conservative", ntile=2, tiles="1,1"))
    pr.compare(a, b, "variant")                       # same decomposition: fine
    c = pr.read(_stream("f64", algo="conservative", ntile=2, tiles="2,0"))
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
