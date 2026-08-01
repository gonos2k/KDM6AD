"""Exactly one result artifact is decision-valid, and every artifact says so.

`attested: true` is a claim about the BUNDLES a run consumed — that their
manifests, commits and fixture matched their anchors. It says nothing about
whether the run's CONCLUSION still stands. Two artifacts in this repo had
`attested: true` alongside a conclusion that had been withdrawn in a markdown
finding: the v10 result asserts that Picons and the saturation adjustment are
excluded, which its own records could not support because the Fortran stage was
injected after the wrong ProgB call. A human reading the findings sees the
retraction; a script reading artifacts does not.

So decision validity is its own machine-readable field, and this test is what
makes it a contract rather than a convention.
"""
import json
import pathlib

import pytest

EVIDENCE = pathlib.Path(__file__).resolve().parents[1] / "evidence"
INDEX = EVIDENCE / "RESULT_INDEX.json"

STATUSES = {"current", "superseded", "withdrawn"}


def _results():
    return sorted(EVIDENCE.rglob("*result*.json"))


def _index():
    return json.loads(INDEX.read_text())


def test_every_result_declares_its_decision_validity():
    missing = []
    for p in _results():
        sup = json.loads(p.read_text()).get("supersession")
        if not isinstance(sup, dict) or "valid_for_decision" not in sup:
            missing.append(p.relative_to(EVIDENCE).as_posix())
    assert not missing, (
        f"result artifact(s) with no machine-readable decision validity: {missing}. "
        f"A reader that takes `attested` for validity would treat a withdrawn "
        f"conclusion as evidence.")


@pytest.mark.parametrize("path", _results(), ids=lambda p: p.name)
def test_status_and_validity_agree(path):
    sup = json.loads(path.read_text())["supersession"]
    assert sup["status"] in STATUSES, f"unknown status {sup['status']!r}"
    assert sup["valid_for_decision"] is (sup["status"] == "current"), (
        "only a `current` artifact may be decision-valid")
    if sup["status"] == "withdrawn":
        assert sup.get("withdrawal_reason"), (
            "a withdrawn artifact must say WHY, in the artifact — the reason is "
            "what a later reader needs and it is not in the file otherwise")
    if sup["status"] != "current":
        assert sup.get("superseded_by"), "a non-current artifact must name its successor"


def test_exactly_one_result_is_current():
    current = [p.name for p in _results()
               if json.loads(p.read_text())["supersession"]["status"] == "current"]
    assert len(current) == 1, f"expected exactly one current result, found {current}"


def test_the_index_agrees_with_the_artifacts():
    idx = _index()
    on_disk = {p.name: json.loads(p.read_text())["supersession"]["status"]
               for p in _results()}
    assert idx["current_decision_result"] in on_disk
    assert on_disk[idx["current_decision_result"]] == "current"

    listed = {pathlib.Path(e["file"]).name: e["status"] for e in idx["superseded"]}
    non_current = {n: s for n, s in on_disk.items() if s != "current"}
    assert listed == non_current, (
        f"index and artifacts disagree; index says {listed}, disk says {non_current}")


def test_named_successors_exist():
    names = {p.name for p in _results()}
    for p in _results():
        succ = json.loads(p.read_text())["supersession"].get("superseded_by")
        if succ:
            assert succ in names, f"{p.name} names a successor that is not here: {succ}"
