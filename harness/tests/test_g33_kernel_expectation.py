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


# ── what kdm6init BUILT, cross-tree (owner §1.1) ──────────────────────────────

def test_the_initialization_constants_are_recorded_and_broadcast():
    """`I` in y = K(x; theta, I). kdm6init builds these and kdm62D reads them, so two
    legs can agree on every call ARGUMENT and still solve different problems."""
    import g33_fortran_bindings as fb
    authority, run = _run("legacy")
    got = _snapshot(run, "kernel_init_constants")
    names = {n for n, _c, _k in got}
    assert names == {n for n, _dt, _e in fb.INIT_CONSTANTS}
    # each is a scalar broadcast over the grid, so every cell of a given name agrees
    for name in names:
        vals = {b for (n, _c, _k), b in got.items() if n == name}
        assert len(vals) == 1, f"{name} is not constant across the grid: {vals}"
    assert len(got) == len(names) * authority["B"] * authority["K"]


def test_ele2_is_excluded_because_it_is_not_a_kdm6init_product():
    """fconst.h groups it with F32Consts for convenience, but the Fortran computes it
    inside kdm62D at :1601 — after this snapshot — so recording it read 0x00000000 on the
    Fortran side against the real value on the C++ side. A difference in WHEN, not in
    WHAT, and including it would manufacture a divergence out of the instrumentation."""
    import g33_fortran_bindings as fb
    import g33_schema as schema
    assert "ele2" not in {n for n, _d, _e in fb.INIT_CONSTANTS}
    assert "ele2" not in schema.semantic_stage_fields("kernel_init_constants")


def test_the_f32_stepwise_value_is_what_the_fortran_produces():
    """fconst.h exists because a double-then-demote differs by 1 ULP from gfortran's
    REAL(4) stepwise evaluation — its own comment cites pidnc as 0x4402E653 stepwise
    versus 0x4402E652 demoted, measured as the step-45 divergence seed. So pin that the
    Fortran really does produce the stepwise value; if it ever produced the other one,
    the C++ port would be matching the wrong target."""
    _, run = _run("legacy")
    got = _snapshot(run, "kernel_init_constants")
    pidnc = {b for (n, _c, _k), b in got.items() if n == "pidnc"}
    assert pidnc == {0x4402E653}, (
        f"pidnc is {pidnc}, not the f32-stepwise 0x4402E653 that fconst.h targets")


# ── the auxiliary the microphysics consumes (owner §1.3) ──────────────────────

def test_the_micro_auxiliary_bundle_is_recorded_per_outer_loop():
    """The 12 prognostics are not the whole input to the microphysics.

    `x_F == x_C` with `a_F != a_C` gives `M(x, a_F) != M(x, a_C)`, so "the sedimentation
    output matched" was consistent with the seed being in the auxiliary calculation rather
    than in the microphysics arithmetic. The bundle is recorded now, so the comparator can
    see it instead of the reason string asserting past it.
    """
    import g33_fortran_bindings as fb
    authority, run = _run("legacy")
    names = {n for n, _d, _e in fb.MICRO_CALL_AUX}
    assert len(names) == 19, f"expected the 19-field ProgB bundle, got {len(names)}"
    per_loop = {}
    for k, v in run.stages.items():
        if k[2] == "micro_call_aux":
            per_loop.setdefault(k[0], set()).add(k[4])
    assert per_loop, "no micro_call_aux records"
    for loop, got in sorted(per_loop.items()):
        assert got == names, f"loop {loop} carries {got ^ names}"


def test_the_auxiliary_is_recorded_where_the_consumer_reads_it():
    """The anchor is the 4th of seven identical `slope_kdm6` continuation lines.

    Requiring a unique line would have meant anchoring on the nearby `! pihmf:` comment,
    which sits INSIDE the do-loops — injecting a whole-K emission there produced nested
    loops over i and k and would not compile. An occurrence index says which of the seven,
    and still fails loudly if the count changes.
    """
    import g33_fortran_bindings as fb
    anchor = fb.MICRO_CALL_AUX_ANCHOR
    assert isinstance(anchor, tuple), "the anchor must carry its occurrence index"
    line, (n, total) = anchor
    assert (n, total) == (3, 7)
    assert "pidn0g" in line and "pvtg" in line, (
        "the anchor should be the slope_kdm6 call that consumes the bundle, so a source "
        "change that moves the consumer breaks the anchor rather than silently relocating "
        "the snapshot")


# ── the last thing produced, bound to the last thing returned (owner §1.5) ────

def test_the_returned_th_is_bound_to_the_final_t():
    """`t` was excluded from the final-state binding because it is not a COPY — the
    state carries `th` and the pack-out computes `th = t/pii`. Excluding it entirely
    left the last thing the kernel produced unbound to the last thing it returned, so a
    defect in the conversion was invisible to every check.

    It is checked as the CONVERSION now, and this test perturbs one cell by 1 ULP to
    confirm the check can fail — an assertion that cannot fail certifies nothing.
    """
    import dataclasses
    import g33_fortran_semantics as sem
    _, run = _run("legacy")
    assert sem.verify_semantics(run) is True

    state = dict(run.state)
    cell = ("th", 1, 0)
    state[cell] = state[cell] ^ 1                 # one ULP
    with pytest.raises(sem.SemanticError, match="final th not bound"):
        sem.verify_semantics(dataclasses.replace(run, state=state))


def test_the_normalizer_refuses_a_run_with_no_boundary():
    """The decision identity stopped defaulting a missing boundary to the wrapper, but
    the normalizer still did — the contract enforced at one end and quietly supplied at
    the other, so a run could reach the decision path carrying a boundary it never
    declared (owner §3.4)."""
    import dataclasses
    import g33_normalize as nz
    _, run = _run("legacy")
    assert nz.from_fortran_run(run)["problem"]["entry_boundary"]
    with pytest.raises(nz.NormalizeError, match="no usable comparison boundary"):
        nz.from_fortran_run(dataclasses.replace(run, entry_boundary=""))
