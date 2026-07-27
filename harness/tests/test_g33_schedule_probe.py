"""Two-pass schedule discovery (public CI — no build).

The C++ contract must declare loops/mstepmax before the run, but mstep is only
knowable BY running. These tests pin the way out: pre-declare to the algorithm's own
ceiling, read back what the run actually did, derive the exact schedule in Python,
and require a second run to reproduce it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_derived as gd              # noqa: E402
import g33_expectation as ge          # noqa: E402
import g33_schedule_probe as sp       # noqa: E402

BASE = {"case_id": "abc-fourcase_v1", "pair_id": "abc-legacy", "backend": "cpp",
        "algorithm": "legacy", "B": 3, "K": 4, "loops": 1,
        "mstepmax_main": [1], "mstepmax_ice": [1], "species_scope": ["qr", "nr"],
        "qcrmin": 1e-8, "dtcld": 100.0,
        "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}


def _probe(scopes):
    """{(loop, chain): mstep vector} -> a probe reading that ran to completion."""
    return {k: {"mstep": v, "n_seen": max(v)} for k, v in scopes.items()}


# ---- the probe contract ------------------------------------------------------

def test_probe_declares_the_algorithms_own_ceiling_not_a_guess():
    s = sp.probe_schedule(BASE, 3)
    assert s["mstepmax_main"] == [gd.MSTEP_RANGE[1]] * 3
    assert s["mstepmax_ice"] == [gd.MSTEP_RANGE[1]] * 3
    assert s["loops"] == 3


def test_probe_contract_is_small_enough_to_seal():
    # the whole point of a bounded over-declaration: every reachable container is
    # pre-declared, and the cost stays the same order as a real bundle
    recs = ge.expected_records(sp.probe_schedule(BASE, 3))
    containers = {(r.get("outer_loop"), r.get("chain"), r.get("n")) for r in recs}
    assert len(containers) < 400


def test_a_probe_artifact_can_never_be_evidence():
    case = sp.probe_case_id("fourcase_v1")
    assert sp.is_probe(case)
    with pytest.raises(sp.ProbeError):
        sp.assert_not_evidence(case)
    sp.assert_not_evidence("fourcase_v1")        # a real case id is untouched


# ---- the derivation ----------------------------------------------------------

@pytest.mark.parametrize("x,want", [
    (0.0, 1), (0.99, 1), (1.0, 2), (1.49, 2), (1.5, 2), (1.99, 2), (2.0, 3),
])
def test_mstep_relation_is_floor_x_plus_one(x, want):
    # nint(x+0.5) == floor(x+1) for x >= 0; the threshold is x >= m-1, not m-0.5
    assert sp.derive_mstep([x], 1.0) == [want]


def test_derivation_is_clamped_to_the_contract_range():
    lo, hi = gd.MSTEP_RANGE
    assert sp.derive_mstep([-5.0, 1e9], 1.0) == [lo, hi]


# ---- sealing -----------------------------------------------------------------

def test_sealed_schedule_is_the_per_loop_column_maximum():
    probe = _probe({(1, "main"): [1, 5, 9], (2, "main"): [1, 2, 10],
                      (3, "main"): [1, 1, 7]})
    s = sp.sealed_schedule(dict(BASE), probe)
    assert s["loops"] == 3 and s["mstepmax_main"] == [9, 10, 7]


def test_a_chain_that_emits_nothing_seals_as_the_neutral_one():
    # the ice chain under species_scope=[qr, nr] produces no containers at all;
    # deriving anything larger would be inventing evidence
    s = sp.sealed_schedule(dict(BASE), _probe({(1, "main"): [1, 1, 1]}))
    assert s["mstepmax_ice"] == [1]


def test_a_probe_that_stopped_early_cannot_be_sealed():
    # its own mstep says 9 substeps; it wrote 4. Sealing that would produce a
    # contract the evidence run could never satisfy.
    probe = {(1, "main"): {"mstep": [1, 5, 9], "n_seen": 4}}
    with pytest.raises(sp.ProbeError, match="did not complete"):
        sp.sealed_schedule(dict(BASE), probe)


def test_a_partial_chain_cannot_be_sealed():
    probe = _probe({(1, "main"): [1], (2, "main"): [1], (1, "ice"): [1]})
    with pytest.raises(sp.ProbeError, match="partial chain"):
        sp.sealed_schedule(dict(BASE), probe)


def test_non_contiguous_outer_loops_are_refused():
    probe = _probe({(1, "main"): [1], (3, "main"): [1]})
    with pytest.raises(sp.ProbeError, match="not 1..N"):
        sp.sealed_schedule(dict(BASE), probe)


# ---- the reproduce gate ------------------------------------------------------

def test_evidence_must_reproduce_the_probe_schedule_exactly():
    probe = _probe({(1, "main"): [1, 5, 9]})
    sp.assert_reproduced(probe, _probe({(1, "main"): [1, 5, 9]}))
    with pytest.raises(sp.ProbeError):
        sp.assert_reproduced(probe, _probe({(1, "main"): [1, 5, 8]}))


def test_a_scope_appearing_in_only_one_run_is_a_finding():
    probe = _probe({(1, "main"): [1]})
    with pytest.raises(sp.ProbeError, match="scopes"):
        sp.assert_reproduced(probe, _probe({(1, "main"): [1], (2, "main"): [1]}))
