"""Two-pass schedule discovery (public CI — no build).

The C++ contract must declare loops/mstepmax before the run, but mstep is only
knowable BY running. These tests pin the way out: pre-declare to the algorithm's own
ceiling, read back what the run actually did, derive the exact schedule in Python,
and require a second run to reproduce it.
"""
import struct
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


# ---- the probe stream --------------------------------------------------------

def _f32w(v):
    return struct.pack(">f", v).hex()


def _line(loop, n, field, values, dtype="f32"):
    words = "".join(_f32w(v) for v in values) if dtype == "f32" else None
    hexed = " ".join(words[i:i + 8] for i in range(0, len(words), 8))
    return f"KDM6SCHED {loop} main {n} {field} {dtype} {len(values)} {hexed}"


def _stream(loop, n, *, work1_qr, workn_qr, work1_qs, work1_qg, mstep, dtcld):
    return "\n".join([
        _line(loop, n, "work1_qr", work1_qr), _line(loop, n, "workn_qr", workn_qr),
        _line(loop, n, "work1_qs", work1_qs), _line(loop, n, "work1_qg", work1_qg),
        _line(loop, n, "mstep_native", mstep), _line(loop, n, "dtcld", dtcld),
    ]) + "\n"


def test_a_probe_stream_parses_to_its_scopes():
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[1.0], dtcld=[100.0])
    parsed = sp.parse_sched_stream(raw)
    assert set(parsed) == {(1, "main", 1)}
    assert parsed[(1, "main", 1)]["dtcld"] == [100.0]


@pytest.mark.parametrize("bad", [
    "KDM6SCHED 1 main 1 work1_qr f32 2 3f800000",          # count != words
    "KDM6SCHED 1 main 1 work1_qr f32 1 3f80",               # short word
    "KDM6SCHED 1 main 1 work1_qr f16 1 3f800000",           # unknown dtype
    "KDM6SCHED x main 1 work1_qr f32 1 3f800000",           # non-integer scope
    "KDM6SCHED 1 main",                                      # truncated
])
def test_a_malformed_probe_line_is_a_broken_probe(bad):
    # skipping it would seal a schedule built from whatever survived truncation
    with pytest.raises(sp.ProbeError):
        sp.parse_sched_stream(bad + "\n")


def test_an_empty_stream_is_not_an_empty_schedule():
    with pytest.raises(sp.ProbeError, match="no KDM6SCHED"):
        sp.parse_sched_stream("KDM6ABC 1 legacy fourcase_v1 3 4\nEND\n")


# ---- the independent re-derivation -------------------------------------------

def test_the_producers_mstep_must_match_its_own_operands():
    # x = f32(0.025)*100 = 2.50000004 -> floor(3.5) = 3. NOT 0.02: its f32
    # round-trip is 0.0199999996, so x lands just under the 2.0 switch and gives 2 —
    # the very sensitivity switch_margin() exists to measure.
    ok = _stream(1, 1, work1_qr=[0.025], workn_qr=[0.0], work1_qs=[0.0],
                 work1_qg=[0.0], mstep=[3.0], dtcld=[100.0])
    assert sp.probe_from_stream(ok)[(1, "main")]["mstep"] == [3]

    lying = _stream(1, 1, work1_qr=[0.025], workn_qr=[0.0], work1_qs=[0.0],
                    work1_qg=[0.0], mstep=[2.0], dtcld=[100.0])
    with pytest.raises(sp.ProbeError, match="not what its operands imply"):
        sp.probe_from_stream(lying)


def test_the_uninstrumented_species_are_part_of_the_maximum():
    # work1_qg alone sets mstep here; reading only qr/nr would derive 1 and the
    # cross-check would then reject a run that is perfectly correct
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.025], mstep=[3.0], dtcld=[100.0])
    assert sp.probe_from_stream(raw)[(1, "main")]["mstep"] == [3]


def test_a_probe_missing_an_operand_cannot_be_derived():
    raw = _line(1, 1, "work1_qr", [0.0]) + "\n" + _line(1, 1, "mstep_native", [1.0])
    with pytest.raises(sp.ProbeError, match="missing"):
        sp.probe_from_stream(raw + "\n")


def test_a_non_integral_mstep_is_refused():
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[2.5], dtcld=[100.0])
    with pytest.raises(sp.ProbeError, match="not integral"):
        sp.probe_from_stream(raw)


# ---- the switch margin -------------------------------------------------------

def test_switch_margin_uses_all_four_fall_speeds():
    # x = 1.5 -> m = 2, so the distance to either switch is 0.5
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.015],
                  work1_qg=[0.0], mstep=[2.0], dtcld=[100.0])
    margin = sp.switch_margin(raw)
    assert margin[(1, "main", 1)] == pytest.approx(0.5, abs=1e-5)


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
