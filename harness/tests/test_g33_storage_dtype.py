"""What a field MEANS and how many bytes the build gave it are two questions.

D6 separated them for the STAGE family and left the op ladder on the old
answer: `_emit_lines` picked its Z edit descriptor and its emitted label from
the SCHEMA dtype, which is the semantic one. At the reference precision the two
agree, so the divergence had nowhere to appear -- and under -fdefault-real-8 it
appears as an eight-byte default real written through `Z8.8`, which is the
wrong-number path D6 exists to close (owner priority 1).

The two directions a single label gets wrong are BOTH present in one rung:

    mul_dend_q        dend(i,k)*qrs(i,k,1)         default real -> widens
    shadow_falk_f32   real(<same expr>,4)          explicit KIND -> does not

so neither "promote every schema-f32" nor "promote none" is the rule. The
EXPRESSION decides, `storage_class` reads it, and this pins that it keeps doing
so -- including the property the archive depends on: at f32 nothing moves.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))
import g33_fortran_bindings as fb        # noqa: E402
import g33_schema as schema              # noqa: E402
import make_fortran_overlay as mo        # noqa: E402
import g33_number_transport as nt        # noqa: E402


@pytest.fixture(autouse=True)
def _restore_real_kind():
    """The generator is a one-shot program and keeps `_REAL_KIND` in module
    state. A test that sets it must put it back, or the next one measures the
    build this one asked for."""
    was = mo._REAL_KIND
    yield
    mo._REAL_KIND = was


def test_every_binding_in_the_table_has_a_storage_class():
    """Asked of the WHOLE table, not of the bindings one generation happens to
    reach: an f64 build is where the classes first matter, so a binding behind
    an untaken branch would be classified for the first time in the run that
    publishes it."""
    got = fb.all_bindings()
    assert len(got) > 200, "the scan found almost nothing -- it is not scanning"
    for where, field, dtype, expr in got:
        assert fb.storage_class(dtype, expr) in fb.STORAGE_CLASSES, \
            f"{where}.{field}"


def test_the_two_directions_a_single_label_gets_wrong():
    rungs = {f: (dt, e) for f, dt, e in fb.QR_FALK}
    assert rungs["mul_dend_q"][0] == rungs["shadow_falk_f32"][0] == "f32", \
        "both are semantically f32; that is what makes the label ambiguous"
    assert fb.storage_class(*rungs["mul_dend_q"]) == "default_real"
    assert fb.storage_class(*rungs["shadow_falk_f32"]) == "real32"
    # ...and the double-precision rung is fixed at eight bytes in both builds,
    # because the build script passes -fdefault-double-8 with -fdefault-real-8.
    assert fb.storage_class(*rungs["mul_work1"]) == "real64"


def test_an_unknown_dtype_is_refused_rather_than_defaulted():
    with pytest.raises(KeyError):
        fb.storage_class("f16", "qrs(i,k,1)")


#: The tail of an emitted op line: '<op_id>', '<field>', '<label>', <expr>
_EMITTED = re.compile(r"'(\w+)', '(\w+)', '(\w+)', ")
#: ...and the Z edit descriptor that governs how wide it prints.
_ZWIDTH = re.compile(r",Z(\d+)\.\d+\)'\)")


def _labels(real_kind, algo="legacy", role="INTERIOR", species="qr"):
    """field -> (emitted label, hex digits) for one op ladder at one build."""
    mo._REAL_KIND = real_kind
    out = {}
    for line in mo._emit_lines(algo, role, species, "pre"):
        if not line.lstrip().startswith("write"):
            continue
        _op, field, label = _EMITTED.search(line).groups()
        out[field] = (label, int(_ZWIDTH.search(line).group(1)))
    return out


def test_at_f32_every_label_is_the_schema_dtype_it_always_was():
    """The archive property. 42 committed streams and the pinned
    non-invasiveness baseline were produced by the old emitter, so the f32
    output has to be what it was, character for character."""
    got = _labels("f32")
    want = {f: dt for op in schema.ops_for_species("legacy", "INTERIOR", "qr")
            for f, dt in schema.op_fields("legacy", "INTERIOR", op)}
    for field, (label, width) in got.items():
        assert label == want[field], field
        assert width == nt.HEX_WIDTH[label], field


def test_at_f64_a_default_real_widens_and_a_pinned_one_does_not():
    got = _labels("f64")
    assert got["mul_dend_q"] == ("f64", 16), "a default real is eight bytes here"
    assert got["shadow_falk_f32"] == ("f32", 8), \
        "an explicit real(...,4) is four bytes whatever the default real is"
    assert got["mul_work1"] == ("f64", 16), "double precision, unchanged"
    # Nothing anywhere may declare a width its payload cannot carry.
    for field, (label, width) in got.items():
        assert width == nt.HEX_WIDTH[label], field


def test_the_f64_ladder_no_longer_writes_a_wide_value_through_a_narrow_field():
    """The defect itself, as a property rather than as one example: no rung may
    be labelled f32 unless its expression pinned it there."""
    mo._REAL_KIND = "f64"
    for algo in sorted(fb.FIELD_EXPR):
        for role in ("TOP", "INTERIOR"):
            for op_id in fb.FIELD_EXPR[algo][role]:
                for field, dtype, expr in fb.FIELD_EXPR[algo][role][op_id]:
                    if mo._storage(dtype, expr) == "f32":
                        assert fb.storage_class(dtype, expr) == "real32", \
                            f"{algo}/{role}/{op_id}.{field} is narrow by accident"


def test_the_archived_samples_still_pass_the_strict_shape_check():
    """The reader half. Three real streams, ~17k checked records between them:
    a strictness that rejected any of these would be rejecting the archive."""
    total = 0
    for p in sorted((ROOT / "tests" / "data").glob("*.g33f")):
        widths = {}
        for line in p.read_text().splitlines():
            if line.startswith("G33F") and (
                    fam := nt._family(line)) in nt.CHECKED_SHAPES:
                nt._shape(line, fam, widths)
                total += 1
    assert total > 10_000, f"only {total} records reached the checker"
