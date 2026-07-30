#!/usr/bin/env python3
"""Each backend against the FIXTURE, not against the other — public CI, no build.

`M_F(x) == M_C(x)` passes when both adapters are wrong the same way, and both were
written from the same source reading by the same person in the same week. So the fixture
computes its own expectation and each leg is held to it separately (owner §3):

    M_F(x) == M_expected(x)
    M_C(x) == M_expected(x)

Agreement between the two legs only means something after that.

Uses the committed samples, which are WRAPPER-boundary runs and therefore carry no
`kernel_call_input` — the driver only emits it on the kernel path. What they do carry is
`kernel_after_entry_clamp`, which the overlay emits on both boundaries, so the padding
half is checkable here and the mapping half is checked against the fixture directly.
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))
import g33_fixture_v1 as gfx            # noqa: E402
import g33_fortran_dump as fd           # noqa: E402
import g33_kernel_expectation as kx     # noqa: E402

SAMPLES = {
    "legacy": Path(__file__).parent / "data" / "g33_legacy_sample.g33f",
    "conservative": Path(__file__).parent / "data" / "g33_conservative_sample.g33f",
}


def _run(algo):
    _, authority = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    text = SAMPLES[algo].read_text()
    return authority, fd.parse_fortran_run(text, algo, authority["K"], authority["B"])


def _snapshot(run, stage, loop=0):
    return {(k[4], k[5], k[6]): v[1] for k, v in run.stages.items()
            if k[2] == stage and k[0] == loop}


# ── the transcription itself ──────────────────────────────────────────────────

def test_the_expectation_is_a_pure_function_of_the_fixture():
    """No backend output anywhere in its inputs, or it is not independent."""
    src = (ROOT / "g33_kernel_expectation.py").read_text()
    for forbidden in ("g33_fortran_dump", "g33_bundle_io", "g33_normalize",
                      "stages", "verify_"):
        assert forbidden not in src, f"the expectation reads {forbidden}"


def test_dropping_the_exner_factor_changes_the_expectation():
    """`t = th * pii` is the only arithmetic at this boundary, so if the expectation
    cannot tell it from `t = th` it certifies nothing about the mapping."""
    _, authority = gfx.load_fixture("boundary_mapping_v1")
    want = kx.expected_call_input(authority)
    K = authority["K"]
    for c in range(authority["B"]):
        for k in range(K):
            th = kx.f32(authority["fields"]["th"][c * K + k])
            assert want[("t", c + 1, k)] != kx.bits(th), (
                f"col{c+1} k{k}: t equals th, so the Exner factor is untested here")


def test_the_padding_is_a_closed_world():
    """A clamp that quietly touched qv or t would be a defect, so the fields the padding
    must NOT change are named rather than left to the absence of a rule."""
    assert not (set(kx._PADDING) & set(kx.UNCHANGED_BY_PADDING))
    # every field the call input carries is accounted for, one way or the other
    _, authority = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    fields = {name for name, _c, _k in kx.expected_call_input(authority)}
    assert fields == set(kx._PADDING) | set(kx.UNCHANGED_BY_PADDING), (
        f"unaccounted: {fields ^ (set(kx._PADDING) | set(kx.UNCHANGED_BY_PADDING))}")


# ── each leg against the expectation ──────────────────────────────────────────

def _ignore(run):
    import g33_schema as schema
    return kx.allowed_to_differ(run.entry_boundary, schema.KERNEL_ENTRY)


@pytest.mark.parametrize("algo", sorted(SAMPLES))
def test_the_padding_snapshot_matches_the_independent_replay(algo):
    """`kernel_after_entry_clamp` recomputed from the fixture, per leg.

    On the arithmetic fixture nothing is out of band, so the padding is the identity and
    this checks that the snapshot is the fixture's own state — which is where a K-flip or
    a column transposition in the SNAPSHOT (as opposed to in the call) would show.

    `nccn` is excluded on a WRAPPER stream because the wrapper rewrites it from a height
    profile; that exclusion is itself checked below, in both directions.
    """
    authority, run = _run(algo)
    got = _snapshot(run, "kernel_after_entry_clamp")
    assert got, "the sample carries no kernel_after_entry_clamp"
    want = kx.expected_after_padding(kx.expected_call_input(authority))
    ig = _ignore(run)
    bad = kx.compare(got, want, ignore=ig)
    assert not bad, (
        f"{algo}: {len(kx.compare(got, want, limit=0, ignore=ig))} cells differ from "
        f"the independent replay, e.g. {bad}")


@pytest.mark.parametrize("algo", sorted(SAMPLES))
def test_the_wrapper_changes_nccn_AND_ONLY_nccn(algo):
    """The wrapper allowed-change set as a CLOSED WORLD (owner §6.2 / PR D).

    "We found an nccn difference" and "nccn is the only difference there is" are
    different statements, and only the second constrains the wrapper. Both directions are
    required: every other field must arrive as the fixture supplied it, and nccn must
    actually have been rewritten — a wrapper that left it alone is equally a finding.
    """
    import g33_schema as schema
    authority, run = _run(algo)
    assert run.entry_boundary == schema.WRAPPER_INPUT, "sample is not a wrapper run"
    got = _snapshot(run, "kernel_after_entry_clamp")
    want = kx.expected_after_padding(kx.expected_call_input(authority))

    # 1. nothing outside the allowed set differs
    assert not kx.compare(got, want, ignore=kx.WRAPPER_MAY_CHANGE)
    # 2. and the allowed field DID change — otherwise the exclusion is hiding nothing
    #    and the profile is not being applied at all
    changed = [k for k in want if k[0] in kx.WRAPPER_MAY_CHANGE and got[k] != want[k]]
    assert len(changed) == len(
        [k for k in want if k[0] in kx.WRAPPER_MAY_CHANGE]), (
        "the wrapper left some nccn cells at the fixture value, so the height profile "
        "is not being applied everywhere")


def test_both_legs_match_the_same_expectation_not_merely_each_other():
    """The point of the whole file: agreement is checked AFTER each leg is anchored."""
    authority, legacy = _run("legacy")
    _, cons = _run("conservative")
    want = kx.expected_after_padding(kx.expected_call_input(authority))
    a = _snapshot(legacy, "kernel_after_entry_clamp")
    b = _snapshot(cons, "kernel_after_entry_clamp")
    ig = _ignore(legacy)
    assert not kx.compare(a, want, ignore=ig) and not kx.compare(b, want, ignore=ig)
    assert a == b        # and only now does this mean something


# ── the mutations the expectation must catch ──────────────────────────────────

def test_a_mangled_expectation_is_caught():
    """If the comparison cannot fail, the tests above certify nothing. Perturb the
    expectation and require the real snapshot to disagree with it."""
    authority, run = _run("legacy")
    got = _snapshot(run, "kernel_after_entry_clamp")
    want = kx.expected_after_padding(kx.expected_call_input(authority))
    ig = _ignore(run)
    assert not kx.compare(got, want, ignore=ig)

    K = authority["K"]
    # a K-flip
    flipped = {(f, c, K - 1 - k): b for (f, c, k), b in want.items()}
    assert kx.compare(got, flipped, ignore=ig), "a K-flip is invisible on this fixture"
    # a column roll
    B = authority["B"]
    rolled = {(f, (c % B) + 1, k): b for (f, c, k), b in want.items()}
    assert kx.compare(got, rolled, ignore=ig), "a column roll is invisible on this fixture"
    # qc and qi swapped
    swapped = dict(want)
    for (f, c, k) in list(want):
        if f == "qc":
            swapped[("qc", c, k)] = want[("qi", c, k)]
            swapped[("qi", c, k)] = want[("qc", c, k)]
    assert kx.compare(got, swapped, ignore=ig), "swapping qc and qi is invisible on this fixture"


def test_the_nccn_band_is_the_source_band():
    """A floor instead of a band, or the wrong bound, is the kind of transcription error
    this module exists to make checkable — pin the values against the source lines."""
    assert (kx.NCCN_MIN, kx.NCCN_MAX) == (1.0e8, 2.0e10)   # F:859
    assert kx.NI_MAX == 1.0e6                              # F:862
    # and the band must actually be a band
    assert kx._PADDING["nccn"](1.0) == kx.NCCN_MIN
    assert kx._PADDING["nccn"](1.0e30) == kx.NCCN_MAX
    assert kx._PADDING["ni"](1.0e30) == kx.NI_MAX
    assert kx._PADDING["ni"](-1.0) == 0.0
