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


def _stream(precision="f32", *, B=2, K=2, end=True, schema=2, prec=True,
            forcing=("rho", "delz"), initial=True, fixture="fx", algo="legacy",
            mode="rezero", nsplit=12, dtcld=25.0):
    out = [f"G33P BEGIN {schema} precision {precision} source_precision f32 "
           f"fixture {fixture} algorithm {algo} mode {mode} "
           f"{nsplit} 1 1 {300.0/nsplit:.6f} {dtcld:.6f} {B} {K}"]
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


def test_rho_without_delz_is_refused():
    with pytest.raises(pr.ProbeError, match="must be together"):
        pr.read(_stream(forcing=("rho",)))


def test_prec_must_cover_species_1_2_3_over_the_columns():
    s = _stream().replace("G33P PREC 2 1   0.0000000000000000E+000\n", "")
    with pytest.raises(pr.ProbeError, match="species 1/2/3"):
        pr.read(s)


def test_an_initial_state_over_different_cells_is_refused():
    s = _stream().replace("G33P INITIAL th 1 0", "G33P INITIAL th 9 0")
    with pytest.raises(pr.ProbeError, match="INITIAL covers different"):
        pr.read(s)


def test_a_grid_disagreeing_with_the_header_is_refused():
    lines = _stream(B=2, K=2).splitlines()
    lines[0] = lines[0][:-3] + "3 2"        # header now claims B=3
    with pytest.raises(pr.ProbeError, match="header declares"):
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
