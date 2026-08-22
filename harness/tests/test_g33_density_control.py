#!/usr/bin/env python3
"""The density-profile control, and the falsification it exists to run.

LOCAL ONLY (needs gfortran + the gitignored host reference tree).

`G33-NUMBER-001` explains number creation by a measure mismatch whose residual is

    R_N = (den(lower) - den(upper)) * delz(upper) * dn

so the mechanism's density dependence is what can be WRONG, and the way to attack
it is to perturb the density profile and check the forbidden outcomes: flat must
give zero, inverted must flip the sign, doubled contrast must double it.

The perturbation is applied in the DRIVER, to the forcing it builds, so the
kernel and the fixture are both untouched -- the experiment stays inside the
freeze.

What this file guards is not the physics but the experiment's own validity:

  - the control must not perturb the default path (or every committed stream
    silently changes meaning),
  - a mistyped arm must be REFUSED, not silently run as `as-is` (which would
    report the unperturbed numbers and read as a FAILED falsification),
  - `uniform` must actually flatten the density (otherwise the zero residual is
    evidence of nothing),
  - and the published ratios must still come out.
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_matched_closure as mc  # noqa: E402
import g33_number_transport as nt  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)

ARMS = ("as-is", "uniform", "inverted", "x2")


@pytest.fixture(scope="module")
def driver():
    """One --nflux build for the whole module: XFER is what the matched closure
    reads, and building it four times over would cost four times as much for the
    same binary."""
    with tempfile.TemporaryDirectory(prefix="g33-rho.") as td:
        out = Path(td) / "build"
        b = subprocess.run(["bash", str(BUILD), str(out),
                            "--fixture=g33_fixture_multisubcycle_v1",
                            "--algo=legacy", "--nflux"],
                           capture_output=True, text=True, cwd=REPO)
        assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
        yield out / "g33_refine_driver"


def _run(driver, arm=None):
    argv = [str(driver), "12", "rezero", "3"] + ([arm] if arm else [])
    p = subprocess.run(argv, capture_output=True, text=True)
    assert p.returncode == 0, f"{arm}: driver crashed:\n{p.stderr}"
    return p.stdout


@pytest.fixture(scope="module")
def streams(driver):
    return {arm: _run(driver, arm) for arm in ARMS}


#: sha256 of the G33R stream from `n12 rezero`, as it stood BEFORE the density
#: control existed — taken from the committed bundle
#: kdm6ad-g33m-refine/full-legacy-dtcld/n12.rezero.txt. Pinned as a constant so
#: the regression does not depend on that bundle being present on the host.
BASELINE_G33R_SHA256 = \
    "51403c1d7ca488acb74947b5ec90765a63e673e8cc2638c26e7f90154c249f6c"

#: The SAME baseline as it stood before the driver began recording the land mask
#: and the fixture id. It is kept, not replaced: those thirteen records are
#: instrumentation, and the way to say so is to show the stream without them is
#: unchanged BIT FOR BIT rather than to retire the attestation and assert it.
PRE_INSTRUMENT_G33R_SHA256 = \
    "247cab0a9662d5df7d5960149ec1db435e38d946d251ebd6ab691297c52bde67"

#: The records added since. Named here so a THIRD one cannot be waved through
#: by the same argument without being written down.
INSTRUMENT_PREFIXES = ("G33R FIXTURE", "G33R FORCING xland")


def _g33r_sha(text):
    body = "".join(l + "\n" for l in text.splitlines() if l.startswith("G33R"))
    return hashlib.sha256(body.encode()).hexdigest()


def test_the_default_and_an_explicit_as_is_agree(driver, streams):
    """Argument-handling consistency: passing the arm explicitly must not differ
    from omitting it. This is NOT the non-invasiveness test -- both sides are the
    same post-change binary (owner §6)."""
    assert _run(driver) == streams["as-is"]


def test_the_default_path_still_matches_the_PRE_CHANGE_baseline(driver):
    """Non-invasiveness, against a pinned baseline rather than against itself.

    Comparing the new default to the new explicit `as-is` shows only that the
    argument is handled consistently -- both are the same binary with
    rho_mode = 0, so the comparison cannot detect a regression introduced by the
    change itself. What answers that is the SHA of the stream as it stood before
    the control existed."""
    assert _g33r_sha(_run(driver)) == BASELINE_G33R_SHA256, (
        "the no-argument G33R stream no longer matches the pre-change baseline")


def test_the_new_records_are_INSTRUMENTATION_and_nothing_else(driver):
    """The stream minus the land mask and the fixture id is the pre-change one.

    A changed baseline can be explained away; this is the explanation as a
    measurement. If any of the thirteen new records carried a value the run
    would otherwise not have had -- or if adding them had perturbed anything --
    the remainder would not hash to the byte string the archive was attested
    against.
    """
    kept = [l for l in _run(driver).splitlines()
            if l.startswith("G33R")
            and not l.startswith(INSTRUMENT_PREFIXES)]
    body = "".join(l + "\n" for l in kept)
    assert hashlib.sha256(body.encode()).hexdigest() == \
        PRE_INSTRUMENT_G33R_SHA256, (
            "removing the instrumentation records does not reproduce the "
            "pre-change stream -- the change was not instrumentation")


def test_a_density_arm_ACTUALLY_CHANGES_the_G33R_state(driver, streams):
    """The other half of the same contract: if an arm left the state identical to
    baseline, every prediction below would be trivially satisfied by an
    intervention that never fired."""
    for arm in ("uniform", "inverted", "x2"):
        assert _g33r_sha(streams[arm]) != BASELINE_G33R_SHA256, \
            f"{arm} did not change the state — the intervention did not fire"


def test_a_mistyped_arm_is_refused_not_silently_run_as_is(driver):
    """`case default` falling through to rho_mode = 0 would make `uniforn` emit
    the UNPERTURBED numbers -- which in a falsification test reads as "the
    prediction failed", the most expensive possible way to be wrong."""
    for bad in ("uniforn", "UNIFORM", "invert", "x3", ""):
        p = subprocess.run([str(driver), "12", "rezero", "3", bad],
                           capture_output=True, text=True)
        assert p.returncode != 0, f"{bad!r} was accepted"


def _rho(stream):
    """{(loop, col): [rho by level]} from the pre-sedimentation stage records."""
    out = {}
    for call in nt.calls(stream):
        for (lp, col, k), rec in call["outer_pre_sed"].items():
            out.setdefault((lp, col), {})[k] = rec["rho"]
    return {key: [v[k] for k in sorted(v)] for key, v in out.items()}


def test_uniform_actually_flattens_the_density(streams):
    """Without this, `uniform` giving a zero residual is evidence of nothing --
    an arm that did nothing at all would also give zero."""
    base, flat = _rho(streams["as-is"]), _rho(streams["uniform"])
    assert base and set(base) == set(flat)
    for key, col in base.items():
        assert max(col) - min(col) > 0, f"{key}: fixture density is already flat"
        assert len(set(flat[key])) == 1, f"{key}: uniform arm is not uniform"


def test_inverted_reverses_the_density_gradient(streams):
    """The sign prediction is about the GRADIENT, so the arm has to actually
    reverse it rather than merely rescale."""
    for key, col in _rho(streams["as-is"]).items():
        inv = _rho(streams["inverted"])[key]
        assert (col[-1] - col[0]) * (inv[-1] - inv[0]) < 0, f"{key}: not inverted"


def test_x2_doubles_the_contrast(streams):
    for key, col in _rho(streams["as-is"]).items():
        got = _rho(streams["x2"])[key]
        assert (got[-1] - got[0]) == pytest.approx(2 * (col[-1] - col[0]), rel=1e-5)


def _nr(stream):
    a = mc.analysis(stream)
    rows = {c: a[f"main/nr/{c}"] for c in (1, 2, 3)}
    for c, r in rows.items():
        assert r["usable"], f"col {c}: mass control failed -- {r['reason']}"
    return rows


def test_the_process_is_still_running_in_every_arm(streams):
    """The control that makes `uniform` mean something: an arm that stopped the
    sedimentation would also create no number."""
    base = _nr(streams["as-is"])
    for arm in ARMS:
        for c, r in _nr(streams[arm]).items():
            assert r["surface_out"] == pytest.approx(base[c]["surface_out"],
                                                     rel=0.10), \
                f"{arm} col {c}: surface outflow moved by more than 10%"


def test_flattening_the_density_removes_the_number_creation(streams):
    """The sharpest of the three: the prediction is an exact zero, not a
    magnitude.

    What survives is compared against the CURRENT per-call control, via
    `mc.control()`, rather than recomputing the superseded aggregate form
    `control_tolerance(calls * 8, |surface_out|)` -- which is the pre-§6 shape:
    a flat operation count that ignores mstep and K, and a scale of |F| alone
    (owner P0-3). And the verdict is a SCREENING result, not a roundoff
    certificate: the operation count is a floor and the capped, branching kernel
    is not a straight-line summation."""
    base = _nr(streams["as-is"])
    for c, r in _nr(streams["uniform"]).items():
        assert abs(r["residual"]) < 1e-4 * abs(base[c]["residual"])
        assert r["control"]["max_ratio"] <= 1.0, \
            f"col {c}: leftover exceeds the per-call screening threshold"


def test_inverting_the_density_flips_the_sign_of_the_creation(streams):
    """Predicted -1. Not exactly, because density also sets the fall speed, so
    `dn` is not held fixed -- the tolerance is that second-order effect."""
    base = _nr(streams["as-is"])
    for c, r in _nr(streams["inverted"]).items():
        assert r["residual"] / base[c]["residual"] == pytest.approx(-1, abs=0.05)


def test_doubling_the_density_contrast_doubles_the_creation(streams):
    for c, r in _nr(streams["x2"]).items():
        assert r["residual"] / _nr(streams["as-is"])[c]["residual"] \
            == pytest.approx(2, abs=0.10)


FINDING = ROOT / "evidence" / "FINDING_density_falsification_v1.md"


def test_the_published_ratios_are_the_ones_this_run_produces(streams):
    """The finding quotes -0.9896/+2.0117/... to four decimals. A reader has no
    way to tell a stale table from a current one, and this project's recurring
    defect is exactly that -- a number surviving in prose after the run behind it
    moved. So the PUBLISHED table is what gets checked, against a live build."""
    text = FINDING.read_text().replace("−", "-")     # Unicode minus
    base = _nr(streams["as-is"])
    for arm in ("inverted", "x2"):
        # The finding has TWO tables whose rows start with the arm name -- the
        # predictions and the measurements. Select by shape: the one whose last
        # three cells are numbers.
        published = None
        for ln in text.splitlines():
            if not ln.startswith(f"| `{arm}` |"):
                continue
            cells = [c.strip().strip("*") for c in ln.strip("|").split("|")]
            try:
                published = [float(x) for x in cells[2:5]]
            except ValueError:
                continue
        assert published, f"the finding has no ratio row for {arm}"
        got = [_nr(streams[arm])[c]["residual"] / base[c]["residual"]
               for c in (1, 2, 3)]
        assert published == pytest.approx(got, abs=5e-4), (
            f"{arm}: the finding publishes {published}, this build gives "
            f"{[round(g, 4) for g in got]}")


# ---- owner §5: the arm must be identifiable FROM THE STREAM -------------------

def test_the_stream_header_names_the_density_arm(streams):
    """Handed two raw streams, a reader could not tell `as-is` from `uniform`:
    the arm lived only in the finding, so experiment intent had to be INFERRED
    from the forcing numbers rather than read off the record. Inferring intent is
    exactly what an evidence protocol exists to stop."""
    for arm, text in streams.items():
        got = nt.calls(text)[0]["features"] is not None  # parsed at all
        hdr = next(l for l in text.splitlines()
                   if l.startswith("G33N STREAM_BEGIN"))
        assert hdr.split()[-1] == arm, f"{arm} is not named in its own header"
        assert got


def test_an_unknown_arm_in_a_header_is_refused():
    """A profile the parser does not know must not be read as `as-is`."""
    text = _run_cached_asis()
    bad = text.replace("topout as-is", "topout sideways")
    with pytest.raises(nt.StreamError, match="unknown rho_profile"):
        nt.calls(bad)


_ASIS_CACHE = {}


def _run_cached_asis():
    return _ASIS_CACHE["t"]


@pytest.fixture(autouse=True, scope="module")
def _cache_asis(streams):
    _ASIS_CACHE["t"] = streams["as-is"]


def _mstep_by_call(text):
    """{(call, loop, chain, col): mstep}.

    Keyed by the CALL as well. The first version of this control merged every
    call into one dict whose keys are (loop, chain, col) -- identical across
    calls -- so later calls silently overwrote earlier ones and the "control"
    compared only the last call. It passed while `inverted` was in fact changing
    a sub-step count in call 1.
    """
    return {(i, *k): v for i, c in enumerate(nt.calls(text), 1)
            for k, v in c["mstep"].items()}


def test_uniform_and_x2_leave_the_substep_schedule_UNCHANGED(streams):
    """For these two arms the control holds per call, so they compare over the
    same accumulation count and the same interface universe."""
    base = _mstep_by_call(streams["as-is"])
    assert base
    for arm in ("uniform", "x2"):
        assert _mstep_by_call(streams[arm]) == base, \
            f"{arm} changed the mstep/mstep_i schedule"


def test_inverted_DOES_change_one_substep_count_and_that_is_recorded(streams):
    """Density sets the fall speed and `mstep` is derived from it, so a large
    enough density change can move the schedule -- and inverting the profile
    does, in exactly one place. Asserting the difference rather than tolerating
    it: if a future change made every arm schedule-identical, the finding's scope
    would need to widen, and if it made MORE arms differ, the decomposition's
    matched-interface assumption would break silently."""
    base = _mstep_by_call(streams["as-is"])
    got = _mstep_by_call(streams["inverted"])
    diff = {k: (base[k], got[k]) for k in base if base[k] != got.get(k)}
    assert diff, "inverted no longer changes the schedule — re-scope the finding"
    assert len(diff) == 1, f"more schedule changes than recorded: {diff}"
    (call, loop, chain, col), (was, now) = next(iter(diff.items()))
    assert (chain, col, was, now) == ("main", 3, 3, 2)


# ---- owner §13 P1: the perturbation must stay physical, and change ONE thing --

RHO_MODES = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")


def test_every_arm_leaves_the_density_POSITIVE(driver):
    """`inverted` is `2*mean - den` and `offset-` is `den - 0.10*mean`, so a
    sufficiently stratified column can be driven to zero or below. The kernel
    divides by density throughout, so a non-positive value does not fail -- it
    produces Inf/NaN that would be read as an arm's result.

    Margin is REPORTED, not just asserted: `g33_fixture_boundary_mapping_v1`'s
    `x2` arm reaches 0.12 against an as-is minimum of 0.45, so the guard is
    within a factor of ~4 of firing on a fixture that already exists.
    """
    for mode in RHO_MODES:
        r = subprocess.run([str(driver), "12", "rezero", "3", mode],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{mode}: {r.stderr[-400:]}"
        pre = nt.calls(r.stdout)[0]["outer_pre_sed"]
        lo = min(v["rho"] for v in pre.values())
        assert lo > 0.0, f"{mode} produced a non-positive density: {lo}"


def test_the_driver_REFUSES_rather_than_emitting_a_non_positive_density(driver):
    """The guard is fail-closed. No current fixture trips it -- max/mean is at
    most 1.057 against `inverted`'s threshold of 2.0 -- so this pins the
    CONTRACT: an arm that cannot be built physically must not produce a stream
    at all. Without the guard the run continues and the NaNs look like data."""
    src = (ROOT / "g33_fortran" / "g33_refine_driver.f90").read_text()
    guard = src[src.index("case (5); den(i,k)"):]
    assert "error stop 3" in guard, "the arm builder has no positivity refusal"
    assert ".not. (den(i,k) > 0.0)" in guard, \
        "a `< 0` test would pass NaN through, which is the case that matters"


def test_the_arms_change_the_DENSITY_AND_NOTHING_ELSE(driver):
    """A single-variable intervention is only single-variable if it is measured
    to be. The claim rests on density being the one thing that moved, so every
    other forcing the stream carries is compared bit-for-bit against `as-is`."""
    base = subprocess.run([str(driver), "12", "rezero", "3", "as-is"],
                          capture_output=True, text=True).stdout

    def forcing(stream, name):
        return [l for l in stream.splitlines()
                if l.startswith(f"G33R FORCING {name} ")]

    for mode in RHO_MODES[1:]:
        arm = subprocess.run([str(driver), "12", "rezero", "3", mode],
                             capture_output=True, text=True).stdout
        for name in ("delz", "pii"):
            assert forcing(arm, name) == forcing(base, name), \
                f"{mode} moved {name}, so it is not a density-only intervention"
        assert forcing(arm, "rho") != forcing(base, "rho"), \
            f"{mode} left the density unchanged, so it intervened on nothing"
