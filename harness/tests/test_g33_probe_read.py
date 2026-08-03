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


def _stream(precision="f32", *, B=2, K=2, end=True, schema=1, prec=True,
            forcing=("rho", "delz"), initial=True):
    out = [f"G33P BEGIN {schema} precision {precision} source_precision f32 {B} {K}"]
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
    s = _stream(B=2, K=2).replace("G33P BEGIN 1 precision f32 source_precision f32 2 2",
                                  "G33P BEGIN 1 precision f32 source_precision f32 3 2")
    with pytest.raises(pr.ProbeError, match="header declares"):
        pr.read(s)


def test_a_three_digit_exponent_without_the_E_still_parses():
    """Fortran ES formatting drops the `E` at three digits (5.3e-316 printed as
    `5.2679749487822913-316`). Archived streams predate the widened format."""
    assert pr._f("5.2679749487822913-316") == pytest.approx(5.2679749487822913e-316)


def test_a_non_finite_value_is_refused():
    s = _stream().replace("G33P STATE th 1 0   1.0000000000000000E+000",
                          "G33P STATE th 1 0   NaN")
    with pytest.raises(pr.ProbeError, match="non-finite"):
        pr.read(s)


def test_two_streams_at_the_SAME_precision_are_not_a_pair():
    """A precision comparison needs two precisions; comparing f32 with f32 would
    report 'no difference' as if it meant something."""
    with pytest.raises(pr.ProbeError, match="two different precisions"):
        pr.compare(pr.read(_stream("f32")), pr.read(_stream("f32")))


def test_a_valid_precision_pair_compares():
    pr.compare(pr.read(_stream("f32")), pr.read(_stream("f64")))


def test_streams_over_different_records_are_not_comparable():
    with pytest.raises(pr.ProbeError, match="different records"):
        pr.compare(pr.read(_stream("f32", B=2)), pr.read(_stream("f64", B=3)))
