

"""The v2 manifest schema as a CLOSED tagged union (owner §8)."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_manifest as rm  # noqa: E402


def _real_manifest():
    store = Path.home() / "kdm6ad-g33m-migrate/number-003.bundles"
    m = next(store.glob("*/manifest.json"), None)
    if m is None:
        pytest.skip("decision-grade bundle not on this host")
    return json.loads(m.read_text())


def _arm(m):
    return next(a for a in m["analyses"] if a.get("analysis") == "arm_stream")


def test_the_REAL_bundles_still_validate():
    assert rm.validate(_real_manifest()) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: _arm(m).update(arm="anything"), "is not one of"),
    (lambda m: _arm(m).update(runtime_argv="not-a-list"), "must be a list of str"),
    (lambda m: _arm(m).update(runtime_argv=["9", "rezero", "3", "inverted"]),
     "contradicts nsplit"),
    (lambda m: _arm(m).update(runtime_argv=["12", "rezero", "3", "x2"]),
     "contradicts arm"),
])
def test_an_ARM_STREAM_entry_must_MATCH_the_run_it_names(mutate, expect):
    """`arm` was any truthy string and `runtime_argv` any truthy value. The
    argv is what RAN and the fields are what the manifest SAYS: recording both
    without comparing them lets an entry describe a different run than the one
    it names (owner §8.1)."""
    m = _real_manifest()
    mutate(m)
    bad = rm.validate(m)
    assert any(expect in b for b in bad), bad


def test_an_UNKNOWN_derived_analysis_kind_is_REFUSED():
    """Anything not "arm_stream" was accepted as a derived analysis, so a typo
    shipped as a new kind (owner §8.2). Added rather than renamed, so the
    minimum-set rule is not what catches it."""
    m = _real_manifest()
    extra = copy.deepcopy(next(a for a in m["analyses"]
                               if a.get("analysis") == "matched_closure"))
    extra["analysis"] = "matched_clsoure"
    extra["file"] = "n12.rezero.typo.json"
    m["analyses"].append(extra)
    assert any("unknown derived analysis" in b for b in rm.validate(m))


def test_an_INSTRUMENTED_bundle_must_carry_the_instrumented_analyses():
    """`instrumented: true` needed only a non-empty `analyses`, which a single
    arm_stream satisfies while carrying none of them (owner §8.3)."""
    m = _real_manifest()
    m["analyses"] = [a for a in m["analyses"] if a.get("analysis") == "arm_stream"]
    assert any("missing the analyses that make it instrumented" in b
               for b in rm.validate(m))


def test_the_TWO_statements_about_the_BINARY_must_agree():
    """The executable digest is recorded in build_artifacts AND inside
    build_provenance, and nothing compared them. Two statements about the same
    binary that are never checked against each other are one statement and one
    decoration (owner §8.4)."""
    m = _real_manifest()
    for a in m["build_artifacts"]:
        if a["file"] == "g33_refine_driver":
            a["sha256"] = "f" * 64
    assert any("names two different binaries" in b for b in rm.validate(m))


def test_DERIVED_ANALYSES_matches_the_PRODUCER_registry():
    """Declared in the manifest module because the producer imports it, so
    drift has to be a test failure rather than a silently widened union."""
    import g33_refine_experiment as xp
    assert set(rm.DERIVED_ANALYSES) == set(xp.ANALYSES) | {"metric_trajectory"}
    assert set(rm.REQUIRED_WHEN_INSTRUMENTED) == set(xp.ANALYSES)
