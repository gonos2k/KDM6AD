"""The stage registry is the ONE authority, and the tables really derive from it.

Stage order, container id, chain and emitting backend used to be six tables in
five modules. Every protocol step that added a stage put them out of step in a
different way, and each failure surfaced somewhere other than the omission:

* a renumbered `_STAGE_MAJOR` silently reordered the op ladder,
* an undeclared container id failed two steps later at "OP_SEQ_MAP has no entry",
* a missing `_STAGE_CHAIN` row reported "non-comparator stage" about a stage the
  schema does define.

Unifying them is only worth something if the consumers keep deriving. A test that
compares two literal tables passes just as well when someone re-hardcodes one, so
these check the derivation and the invariants that make the registry meaningful,
not the values.
"""
import os
import re
import sys

import pytest

_H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _H)
sys.path.insert(0, os.path.join(_H, "g33_fortran"))

import g33_expectation as expectation          # noqa: E402
import g33_fortran_dump as fortran_dump        # noqa: E402
import g33_fourcase_comparator as comparator   # noqa: E402
import g33_normalize as normalize              # noqa: E402
import g33_schema as schema                    # noqa: E402
import gateb_g33m_check                         # noqa: E402


def test_execution_order_is_a_contiguous_ranking_of_the_compared_stages():
    """The order is a RANK, and the op ladder reads it as one.

    Gaps or duplicates would still sort, so nothing would fail — the ladder would
    just rank two stages equal or leave a hole where a stage used to be.
    """
    orders = [sp.execution_order for sp in expectation.STAGES if sp.compared]
    assert sorted(orders) == list(range(len(orders))), orders


def test_uncompared_stages_carry_no_execution_order():
    """`op` and `substep_post` are ranked through the op ladder, not the stage
    order. Giving them a real order would put them in a sequence they do not
    belong to; the sentinel makes that a visible choice."""
    for sp in expectation.STAGES:
        if not sp.compared:
            assert sp.execution_order == -1, sp.name


def test_names_are_unique():
    names = [sp.name for sp in expectation.STAGES]
    assert len(names) == len(set(names))
    assert set(names) == set(expectation.STAGE_BY_NAME)


def test_container_suffixes_are_unique_where_present():
    """Two stages sharing a container id would file each other's records into one
    container, which is how `container_id`'s old `.get(..., "outer_post_micro")`
    fallback lost stages silently."""
    tails = list(expectation.container_suffixes().values())
    assert len(tails) == len(set(tails)), tails


def test_the_comparator_derives_its_order_and_membership():
    assert comparator._STAGE_MAJOR == schema.stage_major()
    assert tuple(comparator._STAGES) == schema.compared_stages()


def test_the_overlay_stage_list_derives():
    assert tuple(expectation.CPP_OVERLAY_STAGES) == schema.cpp_overlay_stages()


def test_the_fortran_parser_derives_its_chain_map():
    assert fortran_dump._STAGE_CHAIN == schema.stage_chains()


def test_the_normalizer_still_agrees_with_the_registry():
    """`normalize` decides which records reach the comparator at all, so a
    divergence here DROPS stages rather than misranking them.

    The relationship is exact, not a containment: normalize compares every stage
    the registry marks compared, less `final_output`, which is whole-step
    cumulative precipitation and travels its own path. Asserting a subset would
    pass just as well against an empty list, which is the failure being guarded.
    """
    assert (set(normalize._COMPARATOR_STAGES)
            == set(schema.compared_stages()) - set(normalize._NOT_COMPARED))
    assert set(normalize._NOT_COMPARED) == {"final_output"}


def test_every_schema_stage_with_semantic_fields_is_registered():
    """The schema's field lists and the registry are separate on purpose — fields
    genuinely differ per stage — but a stage that has fields and no registry row
    has no order, no container and no chain."""
    missing = set(schema._SEMANTIC_STAGE_FIELDS) - set(expectation.STAGE_BY_NAME)
    assert not missing, missing


def test_every_registered_compared_stage_is_known_to_the_schema():
    unknown = {sp.name for sp in expectation.STAGES
               if sp.compared} - set(schema._SEMANTIC_STAGE_FIELDS)
    assert not unknown, unknown


def test_final_output_is_compared_but_not_emitted_by_the_overlay():
    """A standing asymmetry, asserted so that "fixing" it has to be deliberate:
    `final_output` is the whole-step cumulative precipitation, compared from the
    run's output rather than from a stage record."""
    sp = expectation.STAGE_BY_NAME["final_output"]
    assert sp.compared and not sp.cpp_emitted and sp.container_suffix is None


def test_substep_pre_opens_no_outer_container():
    """It rides the per-substep chain/n container. A container suffix here would
    open a second container for records that already have one."""
    sp = expectation.STAGE_BY_NAME["substep_pre"]
    assert sp.container_suffix is None and sp.chain == "main"


#: The registry accessor each derived table must be built from. Naming the
#: accessor rather than rejecting bracket syntax is what makes this test mean
#: something: `_STAGE_MAJOR = dict(kernel_init_constants=0, ...)` is a hardcoded
#: table that opens with a letter, and a "must not start with `{`" check passes it.
_DERIVED_FROM = [
    ("g33_fourcase_comparator.py", "_STAGE_MAJOR", "stage_major"),
    ("g33_fourcase_comparator.py", "_STAGES", "compared_stages"),
    ("g33_expectation.py", "CPP_OVERLAY_STAGES", "cpp_overlay_stages"),
    ("g33_fortran/g33_fortran_dump.py", "_STAGE_CHAIN", "stage_chains"),
]


@pytest.mark.parametrize("mod,name,accessor", _DERIVED_FROM)
def test_the_derived_tables_are_not_re_hardcoded(mod, name, accessor):
    """The equality tests above pass just as well against a re-pasted literal.

    This one reads the source and requires the binding to CALL the registry. That
    is the failure mode being defended against — someone adds a stage, the derived
    call is inconvenient, and a table goes back in. Six of those is where this
    refactor started, and each was a plausible local edit at the time.
    """
    src = open(os.path.join(_H, mod)).read()
    m = re.search(rf"^{re.escape(name)} = (.+)$", src, re.M)
    assert m, f"{name} not found at module level in {mod}"
    rhs = m.group(1).strip()
    assert f"{accessor}(" in rhs, (
        f"{mod}:{name} no longer calls {accessor}() — it reads `{rhs[:60]}`. "
        f"Derive it from the stage registry rather than restating it.")


# ── supersession is produced, not typed ──────────────────────────────────────
#
# Lives here rather than in test_g33_evidence_index because that module tests the
# INDEX over artifacts; this tests the writer that fills the field the index reads.

def _write_result(tmp_path, result):
    import importlib
    g = importlib.import_module("gateb_g33m_check")
    out = tmp_path / "r.json"
    g._write(out, result)
    import json
    return json.loads(out.read_text())


def test_the_writer_supplies_supersession(tmp_path, monkeypatch):
    """The index requires the field on every artifact and nothing produced it: it
    was typed on by hand after each run, so a regeneration either dropped it or
    reintroduced it from memory. A hand-edited field in a decision artifact is
    indistinguishable from a hand-edited verdict."""
    # A decision-valid result must carry the complete publication contract. The
    # source tree is intentionally dirty while tests run, so pin the identity calls
    # to the values supplied by this synthetic writer fixture.
    monkeypatch.setattr(gateb_g33m_check.vid, "runtime_matches", lambda _runtime: None)
    monkeypatch.setattr(gateb_g33m_check.vid, "semantics_sha256_at",
                        lambda _commit: "b" * 64)
    d = _write_result(tmp_path, {"verdict": "INCONCLUSIVE", "attested": True,
                                 "anchored": True, "decision_valid": True,
                                 "evidence_tier": "decision", "provenance": {
        "verifier_commit": "a" * 40, "verifier_semantics_sha256": "b" * 64,
        "verifier_tree_dirty": False, "verifier_runtime": {"python_version": "3.11.14"}}})
    s = d["supersession"]
    assert s["status"] == "current"
    assert s["valid_for_decision"] is True
    assert s["superseded_by"] is None and s["withdrawal_reason"] is None
    assert "a" * 12 in s["note"] and "b" * 16 in s["note"]


def test_a_debug_only_run_is_not_valid_for_decision(tmp_path):
    """--debug-only exists so a dirty tree can still produce something readable.
    That artifact must never be usable as evidence, and the index reads exactly
    this field to decide."""
    d = _write_result(tmp_path, {"verdict": "INCONCLUSIVE", "debug_only": True,
                                 "provenance": {"verifier_tree_dirty": True}})
    assert d["supersession"]["valid_for_decision"] is False
    assert d["supersession"]["status"] == "current"


def test_an_explicit_supersession_is_never_overwritten(tmp_path):
    """Retiring an artifact is a deliberate edit of the OLD file. The writer fills
    an absence; it must not overrule a withdrawal someone recorded."""
    d = _write_result(tmp_path, {"verdict": "INCONCLUSIVE", "supersession": {
        "status": "withdrawn", "superseded_by": "later.json",
        "valid_for_decision": False, "withdrawal_reason": "placement defect",
        "note": "kept"}, "provenance": {}})
    assert d["supersession"]["status"] == "withdrawn"
    assert d["supersession"]["note"] == "kept"
