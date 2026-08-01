"""The owner layer must not be able to become the tool's verdict.

Every test here is about a way that could happen: by writing `verdict`, by
applying to an artifact nobody adjudicated, or by the module shipping an opinion
of its own.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_owner_adjudication as oa   # noqa: E402

ARTIFACT = ROOT / "evidence" / "g33m_v14_fourcase_result.json"


@pytest.fixture
def artifact():
    return json.loads(ARTIFACT.read_text())


@pytest.fixture
def signed(artifact):
    """A filled-in adjudication. The VALUES are this test's, not the project's —
    it needs something well-formed to check the mechanism against."""
    a = oa.template(artifact)
    a["owner_adjudication"].update({
        "status": "closed", "classification": "TEST_ONLY",
        "conservative_only_seed": False,
        "exact_multisubcycle_cross_tree_parity": False,
        "reference_parity_domain": "test", "thermo_policy_selection": "open",
        "meteorological_materiality": "unmeasured"})
    return a


def test_the_module_ships_no_adjudication_of_its_own():
    """The owner review's classification is a recommendation, not an issued
    verdict. A default in this file would put the tool's words in the owner's
    mouth, which is the substitution the module exists to prevent."""
    src = (ROOT / "g33_owner_adjudication.py").read_text()
    assert "SHARED_MULTI_SUBCYCLE" not in src
    assert all(v is None for k, v in
               oa.template({}).get("owner_adjudication", {}).items()
               if k != "bound_to")


def test_the_gate_never_writes_an_adjudication():
    """If the gate could produce one, a rerun could invent a judgment nobody
    made — and, being machine-written, it would look exactly like one somebody
    did."""
    gate = (ROOT / "gateb_g33m_check.py").read_text()
    assert "owner_adjudication" not in gate


def test_the_committed_artifact_carries_no_adjudication_yet(artifact):
    """Guards against this landing pre-signed. Adjudication is the owner's, and
    the review issued a recommendation, not a verdict."""
    assert "owner_adjudication" not in artifact


def test_attach_leaves_the_automatic_verdict_untouched(artifact, signed):
    out = oa.attach(artifact, signed)
    assert out["verdict"] == artifact["verdict"] == "INCONCLUSIVE"
    assert out["legacy_first_divergence"] == artifact["legacy_first_divergence"]


def test_there_is_no_code_path_from_an_adjudication_to_the_verdict(artifact):
    """A `verdict` key inside the adjudication must not reach the artifact's own
    `verdict` — the closest thing to a real forgery attempt."""
    a = oa.template(artifact)
    a["owner_adjudication"]["verdict"] = "PASS_C4"
    with pytest.raises(ValueError, match="unrecognised field"):
        oa.attach(artifact, a)


def test_an_unbound_adjudication_is_rejected(artifact, signed):
    """An adjudication sitting next to the evidence would keep applying after a
    regeneration that moved the first divergence, and would then read as though a
    human had reviewed a result nobody had seen."""
    del signed["owner_adjudication"]["bound_to"]
    assert any("bound_to" in p for p in oa.problems(signed, artifact))
    with pytest.raises(ValueError):
        oa.attach(artifact, signed)


@pytest.mark.parametrize("field", oa.BINDING_FIELDS)
def test_a_changed_input_manifest_detaches_the_adjudication(artifact, signed, field):
    """Different legs, different fixture, or a different verifier means the human
    reviewed a different result."""
    moved = json.loads(json.dumps(artifact))
    moved["provenance"][field] = "0" * 64
    bad = oa.problems(signed, moved)
    assert any(field in p for p in bad), bad


def test_a_moved_first_divergence_detaches_the_adjudication(artifact, signed):
    """The strongest case: same inputs, same verifier, but the result changed.
    The artifact digest catches what the manifest list cannot."""
    moved = json.loads(json.dumps(artifact))
    moved["legacy_first_divergence"]["identity"][6] = "cpm"
    assert any("artifact_sha256" in p for p in oa.problems(signed, moved))


def test_a_changed_verdict_detaches_the_adjudication(artifact, signed):
    moved = json.loads(json.dumps(artifact))
    moved["verdict"] = "PASS_MECHANISM"
    assert any("verdict" in p for p in oa.problems(signed, moved))


def test_the_binding_ignores_the_adjudication_itself(artifact, signed):
    """The digest must exclude the attached adjudication, or binding would be
    circular and no adjudication could ever match."""
    attached = oa.attach(artifact, signed)
    assert oa.artifact_digest(attached) == oa.artifact_digest(artifact)
    assert not oa.problems(signed, attached)


def test_an_incomplete_adjudication_is_rejected(artifact):
    """A missing scope line is a judgment with an unstated domain — exactly the
    over-extension the review warns against."""
    a = oa.template(artifact)
    a["owner_adjudication"].pop("reference_parity_domain")
    assert any("reference_parity_domain" in p for p in oa.problems(a, artifact))


def test_a_template_is_well_formed_but_unsigned(artifact):
    """It must bind correctly so the owner only has to fill in judgments, while
    every judgment field is None so an unfilled template is never mistaken for a
    decision."""
    t = oa.template(artifact)
    assert not [p for p in oa.problems(t, artifact) if "bound_to" in p]
    assert all(t["owner_adjudication"][f] is None for f in oa.REQUIRED_FIELDS)


def test_the_cli_round_trips_and_refuses_a_moved_artifact(tmp_path, artifact, signed):
    """End to end, because the owner uses the CLI and not the functions: generate,
    fill, validate, then move the artifact and watch it detach with a nonzero exit."""
    art = tmp_path / "a.json"
    art.write_text(json.dumps(artifact))
    adj = tmp_path / "adj.json"

    t = json.loads(json.dumps(oa.template(json.loads(art.read_text()))))
    t["owner_adjudication"].update(signed["owner_adjudication"])
    t["owner_adjudication"]["bound_to"] = oa.binding_for(artifact)
    adj.write_text(json.dumps(t))
    assert oa._main([str(art), "--check", str(adj)]) == 0

    moved = json.loads(json.dumps(artifact))
    moved["legacy_first_divergence"]["identity"][6] = "cpm"
    art.write_text(json.dumps(moved))
    assert oa._main([str(art), "--check", str(adj)]) == 1
