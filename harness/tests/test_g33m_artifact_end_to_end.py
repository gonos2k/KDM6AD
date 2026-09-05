#!/usr/bin/env python3
"""RUN the artifact generator — public CI, no build.

Every test around this generator was structural: they read its source and asserted it
did not contain a second first-divergence algorithm, did not read a previous
result.json, called the shared loader. All of that passed while
`bundle["algorithms"][algo]` — a name deleted by the loader extraction — sat in the
per-algorithm summary and raised NameError the moment the function ran. CI was green
and the generator was unrunnable.

Reading source cannot catch that. Only execution can, so this executes it.

The four-case tree is synthetic: a C++ bundle from test_g33_bundle_io's builder and two
Fortran bundles from test_g33_fortran_bundle_io's, around the checked-in legacy and
conservative sample streams. The verdict such a tree produces is not the point — the
point is that main() completes and the artifact it writes has the fields a reader
depends on.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))
sys.path.insert(0, str(Path(__file__).parent))
import g33_fixture_v1 as gfx                    # noqa: E402
import make_g33m_evidence_artifact as gen       # noqa: E402
import test_g33_bundle_io as tcpp               # noqa: E402
import test_g33_fortran_bundle_io as tfor       # noqa: E402

CONS_SAMPLE = Path(__file__).parent / "data" / "g33_conservative_sample.g33f"


def _fourcase_tree(tmp_path: Path) -> Path:
    """A four-leg evidence tree laid out the way the generator expects."""
    ev = tmp_path / "evidence"
    ev.mkdir()
    tcpp._bundle(ev / "cpp-bundle")
    tfor._bundle(ev / "fortran-legacy", algo="legacy")
    # The conservative leg needs a genuine conservative stream: the op universe differs
    # between the variants, so the parser refuses a relabelled legacy one — correctly.
    cons = tfor._bundle(ev / "fortran-conservative", algo="conservative",
                        sample=CONS_SAMPLE)
    assert cons.is_dir()
    return ev


def test_the_generator_actually_runs(tmp_path, monkeypatch, capsys):
    """main() to completion, on a real tree, through the real loader."""
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "artifact.json"
    monkeypatch.setattr(sys, "argv", [
        "make_g33m_evidence_artifact.py",
        "--evidence", str(ev),
        "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested",          # a synthetic tree carries no external anchors
        "--out", str(out)])
    rc = gen.main()
    assert rc in (0, None), f"generator exited {rc}"
    assert out.is_file(), "no artifact written"
    art = json.loads(out.read_text())
    # the fields a reader depends on, including the ones the NameError sat behind
    for key in ("schema_version", "verdict", "attested", "anchored", "reason", "per_algorithm",
                "comparison_boundary", "admissibility", "evidence_tier",
                "first_divergence", "intra_backend_carry_proof",
                "cross_backend_difference_propagation", "fixture"):
        assert key in art, f"artifact lacks {key}"
    for algo in ("legacy", "conservative"):
        per = art["per_algorithm"][algo]
        # exactly the two the stale `bundle` name guarded
        assert "mstep_range" in per and isinstance(per["mstep_range"], list)
        assert "probe_lineage" in per and isinstance(per["probe_lineage"], dict)


def test_an_unanchored_run_is_labelled_debug(tmp_path, monkeypatch):
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested", "--out", str(out)])
    gen.main()
    art = json.loads(out.read_text())
    assert art["evidence_tier"] == "debug"
    assert art["attested"] is False


def test_unanchored_without_the_flag_is_refused(tmp_path, monkeypatch):
    """A decision artifact from unanchored evidence would assert `attested` about
    something nothing checked."""
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--out", str(out)])
    assert gen.main() == 2
    assert not out.exists()


def test_a_wrapper_fortran_leg_is_not_comparison_admissible(tmp_path, monkeypatch):
    """AGREEING is not being at the KERNEL (owner P0-2).

    The committed samples are wrapper-boundary runs and the C++ leg declares the kernel
    as a structural fact about the port, so this tree is MIXED — which is exactly the
    dt=300 configuration that reported an nccn divergence. Neither question is
    admissible on it: not the kernel one (the Fortran legs are not there) and not the
    wrapper contract either (the C++ leg cannot be).

    Four legs agreeing on the WRAPPER boundary turns out to be unreachable, because the
    C++ declaration is not a run property. That is a stronger guarantee than the test I
    first wrote assumed.
    """
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested", "--out", str(out)])
    gen.main()
    art = json.loads(out.read_text())
    assert set(art["comparison_boundary"].values()) == {
        "kdm6_wrapper_input_v1", "kdm62d_kernel_entry_v1"}
    assert art["admissibility"]["boundary"] is False
    assert art["admissibility"]["overall"] is False
    assert art["wrapper_mapping_admissible"] is False
    # and the mixture is refused as evidence, not reported as a divergence
    assert art["verdict"] == "INVALID_EVIDENCE"
    assert "same problem" in art["reason"]


def test_an_unmeasured_precondition_is_named_not_omitted(tmp_path, monkeypatch):
    """A missing row reads as satisfied to anyone scanning the JSON, so the conditions
    that are not yet measured say `null` rather than being absent (owner P0-2.3)."""
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested", "--out", str(out)])
    gen.main()
    adm = json.loads(out.read_text())["admissibility"]
    for unmeasured in ("scalar_parameter_identity", "cross_tree_initialization_identity",
                       "stage_program_points", "dynamic_aux_identity"):
        assert unmeasured in adm, f"{unmeasured} omitted rather than declared unmeasured"
        assert adm[unmeasured] is None
    # and a not-yet-measured condition can never make `overall` true
    assert adm["overall"] is False


def test_a_vacuous_propagation_row_says_so(tmp_path, monkeypatch):
    """The old single carry_proof reported `identical: true, records: 0` — the SHA256 of
    the empty string on both sides — for the bridge where the two backends agreed
    everywhere. Nothing-to-nothing is not a finding, and the row now labels itself."""
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested", "--out", str(out)])
    gen.main()
    art = json.loads(out.read_text())
    for algo, spans in art["cross_backend_difference_propagation"].items():
        for span, row in spans.items():
            assert "vacuous" in row, f"{algo} {span} does not say whether it compared anything"
            if row["differing_records"] == 0:
                assert row["vacuous"] is True


def test_the_intra_carry_proof_covers_the_whole_carried_state(tmp_path, monkeypatch):
    """12 carried fields x B columns x K levels, per leg per bridge. A proof over an
    empty set is the one thing this must not accept."""
    ev = _fourcase_tree(tmp_path)
    out = tmp_path / "a.json"
    monkeypatch.setattr(sys, "argv", [
        "x", "--evidence", str(ev), "--fixture-id", gfx.DEFAULT_FIXTURE_ID,
        "--allow-unattested", "--out", str(out)])
    gen.main()
    _, auth = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    want = 12 * auth["B"] * auth["K"]
    proofs = json.loads(out.read_text())["intra_backend_carry_proof"]
    assert proofs, "no intra-backend carry proof at all"
    for leg, spans in proofs.items():
        for span, row in spans.items():
            assert row["records"] == want, f"{leg} {span}: {row['records']} != {want}"
            assert row["identical"] is True, f"{leg} {span} carry is not exact"
