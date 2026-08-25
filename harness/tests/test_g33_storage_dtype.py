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


# --- the class is DECLARED, and the undeclarable is refused (priority 6) -----

def test_every_declared_override_LOOKS_like_the_cast_it_claims_to_be():
    """The regex is kept, demoted to a cross-check. It must never be the thing
    that DECIDES -- the forms it does not match are exactly the ones that would
    be misclassified -- but a declaration it disagrees with is worth surfacing."""
    for expr, cls in fb.STORAGE_OVERRIDES.items():
        assert cls in fb.STORAGE_CLASSES, (expr, cls)
        assert fb._LOOKS_PINNED.match(expr.strip()), (
            f"{expr!r} is declared {cls} and does not look like a narrowing "
            f"cast -- one of the two is wrong")


@pytest.mark.parametrize("expr", [
    "real(dend(i,k)*qrs(i,k,1), kind=4)",      # the standard's other spelling
    "real(dend(i,k)*qrs(i,k,1), real32)",      # a named kind
    "dble(dend(i,k)*qrs(i,k,1))",              # widening, equally undeclared
    "int(mstep(i), 8)",
])
def test_an_UNDECLARED_conversion_is_refused_not_assumed(expr):
    """The risk was never the two casts already in the table -- it was the next
    binding, written in a form the pattern does not match and silently called a
    default real. Deciding by pattern cannot catch that; refusing what it
    cannot read can."""
    with pytest.raises(KeyError, match="declare it in STORAGE_OVERRIDES"):
        fb.storage_class("f32", expr)


def test_a_plain_expression_is_still_a_DEFAULT_REAL_without_ceremony():
    """The rule is about the ABSENCE of a construct, so the 200-odd ordinary
    bindings need no declaration and none was added."""
    assert fb.storage_class("f32", "dend(i,k)*qrs(i,k,1)") == "default_real"
    assert not fb.STORAGE_OVERRIDES.keys() - {
        e for _w, _f, _d, e in fb.all_bindings()}, \
        "an override names an expression no binding uses"


def test_EXACTLY_the_declared_expressions_carry_a_conversion():
    """Measured over the whole table rather than asserted: if a new binding
    arrives with a cast and no declaration, this is where it shows up -- and
    `storage_class` refuses it either way."""
    carriers = {e for _w, _f, _d, e in fb.all_bindings()
                if fb._CONVERSION.search(e)}
    assert carriers == set(fb.STORAGE_OVERRIDES), \
        sorted(carriers ^ set(fb.STORAGE_OVERRIDES))


def test_the_binding_tables_know_exactly_the_arms_the_driver_emits():
    """`FIELD_EXPR` and `XFER_SITES` were the two arm registries anchored to
    nothing.

    Adding the melt arms needed five separate registrations, and only some
    failed at edit time. `_ALGOS` and `NUMBER_TRANSFER_METRIC` are each pinned
    to the driver's own `ALGOTAG` vocabulary in both directions, so a missing
    arm fails there immediately. These two were not: a partial `FIELD_EXPR`
    entry passed every table check and then died much later inside schema
    validation, on a `QR_OUTFLOW` key that had nothing to do with the edit.

    Same invariant, same source of truth -- the driver, not a constant here.
    """
    driver = (Path(__file__).resolve().parents[1]
              / "g33_fortran" / "g33_refine_driver.f90").read_text()
    emitted = set(re.findall(r"ALGOTAG = '([a-z_0-9]+)'", driver))
    assert emitted, "no ALGOTAG assignments found; the cascade moved"
    for name, table in (("FIELD_EXPR", fb.FIELD_EXPR),
                        ("XFER_SITES", fb.XFER_SITES)):
        assert emitted == set(table), (
            f"{name}: only the driver knows: {sorted(emitted - set(table))}; "
            f"only the table knows: {sorted(set(table) - emitted)}")


def test_an_arm_missing_from_a_binding_table_is_caught_here_not_later():
    """The guard above must fail for the reason it claims. Dropping one arm
    from a COPY of the table has to be visible as a set difference -- otherwise
    the assertion is shape-checking, not membership-checking."""
    driver = (Path(__file__).resolve().parents[1]
              / "g33_fortran" / "g33_refine_driver.f90").read_text()
    emitted = set(re.findall(r"ALGOTAG = '([a-z_0-9]+)'", driver))
    holed = dict(fb.FIELD_EXPR)
    holed.pop("melt_g1")
    assert emitted != set(holed)
    assert sorted(emitted - set(holed)) == ["melt_g1"]
