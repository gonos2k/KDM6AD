#!/usr/bin/env python3
"""The graupel-melt arm generator, which had no tests at all.

It edits a FROZEN kernel by textual anchor, so every way it can be wrong is a
way it can emit a plausible file that means something other than the arm asked
for. Three such ways are already closed in the generator and pinned here:

  * an anchor that matches twice (or not at all) -- `_once`
  * a threshold copied from a scope that is not ProgB_param's -- `_check_constants`
  * a base whose mass update stops preceding the volume update, which would
    make g3's complete-melt branch unreachable -- `_mass_update_precedes_divide`

The structural half runs anywhere: it drives the checks with SYNTHETIC text, so
it does not need the gitignored reference tree. Only the tests that generate a
real arm are gated on the host file being present.
"""
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "g33_fortran"))
import make_graupel_melt_arms as mg      # noqa: E402

DECLS = ("  real, parameter   :: rho_min = 100.\n"
         "  real, parameter   :: rho_max = 900.\n"
         "  real, parameter   :: brs_min = 1.e-15\n")
ORDERED = DECLS + mg.MASS_UPDATE + mg.DIVIDE


# ── the anchor-count check ───────────────────────────────────────────────────

def test_an_anchor_that_matches_twice_is_refused():
    """Two matches means `str.replace` would edit both, and the second site is
    not one anyone looked at."""
    with pytest.raises(SystemExit) as e:
        mg._once(mg.DIVIDE + mg.DIVIDE, mg.DIVIDE, "divide")
    assert "2 times" in str(e.value)


def test_an_anchor_that_matches_nothing_is_refused():
    with pytest.raises(SystemExit) as e:
        mg._once("nothing here\n", mg.DIVIDE, "divide")
    assert "0 times" in str(e.value)


def test_a_single_match_is_accepted():
    mg._once(ORDERED, mg.DIVIDE, "divide")


# ── the threshold check ──────────────────────────────────────────────────────

def test_a_threshold_that_disagrees_with_the_base_is_refused():
    """The arms declare their own copies; a copy that differs would make the
    arm answer a different question than the one asked."""
    with pytest.raises(SystemExit) as e:
        mg._check_constants(DECLS.replace("rho_max = 900.", "rho_max = 800."))
    assert "rho_max" in str(e.value)


def test_two_declarations_of_one_threshold_are_refused():
    """With more than one, the first match is an arbitrary choice among scopes
    and the arm could run on the other one."""
    with pytest.raises(SystemExit) as e:
        mg._check_constants(DECLS + "  real, parameter   :: rho_min = 250.\n")
    assert "2 declarations" in str(e.value)


def test_the_same_threshold_written_differently_is_still_the_same():
    """`100.` and `100.0` are one threshold. A string comparison called them
    different, which fails a correct base."""
    mg._check_constants(DECLS.replace("rho_min = 100.", "rho_min = 100.0"))


def test_a_missing_threshold_is_refused():
    with pytest.raises(SystemExit):
        mg._check_constants(DECLS.replace("brs_min = 1.e-15", "unrelated = 1."))


# ── the order g3 depends on ──────────────────────────────────────────────────

def test_g3_is_refused_when_the_mass_update_stops_preceding_the_divide():
    """g3 tests `qrs(i,k,3).le.0.` to mean "melted completely". That is only
    reachable because the base updates the mass first. Reverse the order and
    the branch is dead code inside a block opened on `qrs(i,k,3).gt.0.` -- and
    every anchor and every line-count budget still passes, so nothing else
    would have caught it."""
    reversed_ = DECLS + mg.DIVIDE + mg.MASS_UPDATE
    with pytest.raises(SystemExit) as e:
        mg._mass_update_precedes_divide(reversed_)
    assert "dead code" in str(e.value)


def test_the_ordered_base_is_accepted():
    mg._mass_update_precedes_divide(ORDERED)


def test_an_absent_mass_update_is_refused_before_the_order_is_asked():
    with pytest.raises(SystemExit) as e:
        mg._mass_update_precedes_divide(DECLS + mg.DIVIDE)
    assert "0 times" in str(e.value)


# ── the arm selector ─────────────────────────────────────────────────────────

def test_the_known_arms_are_exactly_what_the_selector_accepts():
    """This test has now been broken twice by an arm becoming real -- first g4,
    then g5. Pinning the set makes the next one a deliberate edit rather than a
    surprise failure."""
    import inspect
    src = inspect.getsource(mg.arm)
    assert '("g1", "g2", "g3", "g4", "g5")' in src, "the accepted set moved"


def test_an_unknown_arm_is_refused_rather_than_returning_the_base():
    """Returning the unedited base for an unknown name would produce a file
    that compiles, runs, and is silently the legacy arm."""
    with pytest.raises(SystemExit) as e:
        mg.arm("g99")
    assert "unknown arm" in str(e.value)


# ── generation, which needs the gitignored reference tree ────────────────────

pytestmark_host = pytest.mark.skipif(
    not mg.BASE.is_file(),
    reason="pinned reference tree not present (host/** is gitignored)")


@pytestmark_host
@pytest.mark.parametrize("name", ["g1", "g2", "g3"])
def test_each_arm_edits_the_base_and_only_a_little(name):
    import difflib
    base = mg.BASE.read_text().splitlines()
    got = mg.arm(name).splitlines()
    added = sum(1 for x in difflib.unified_diff(base, got, n=0, lineterm="")
                if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in difflib.unified_diff(base, got, n=0, lineterm="")
                  if x.startswith("-") and not x.startswith("---"))
    assert added and removed, f"{name} changed nothing"
    assert added + removed <= 20, f"{name}: {added}/{removed} is not a melt-block edit"


@pytestmark_host
@pytest.mark.parametrize("name", ["g1", "g2", "g3"])
def test_every_arm_declares_the_thresholds_beside_the_kernels_own_locals(name):
    """They are local to `ProgB_param` and not in scope at the melt."""
    src = mg.arm(name)
    for c in ("melt_brs_min", "melt_rho_min", "melt_rho_max"):
        assert f":: {c} =" in src, f"{name} does not declare {c}"


@pytestmark_host
def test_the_three_arms_are_different_files():
    srcs = {n: mg.arm(n) for n in ("g1", "g2", "g3")}
    assert len(set(srcs.values())) == 3, "two arms generated identical source"


# ── g4's volume cannot go negative (measured, not argued) ────────────────────

def test_the_g4_volume_update_is_floored_at_zero_in_the_source():
    """The clamp makes the volume REMOVED inconsistent with the volume PRESENT.

    `rho` is clamped to [100, 900], so for a particle denser than `rho_max` the
    melt removes `pgmlt/900` of volume while the cell only holds `qg0/raw`,
    which is less. The bulk volume goes negative -- a state that has no meaning
    and that `ProgB_param` would then divide by.
    """
    src = mg.G4_TXN
    line = [L for L in src.splitlines()
            if "brs(i,k) =" in L and "melt_bg0" in L and "melt_rho" in L]
    assert len(line) == 1, "the partial-melt volume update moved"
    assert line[0].strip().startswith("brs(i,k) = max(0.,"), \
        f"the volume update is not floored: {line[0].strip()}"


def test_the_unfloored_arithmetic_goes_negative_only_inside_the_window():
    """The floor is not decoration, and its reach is narrower than first
    recorded.

    OUTSIDE the window `ProgB_param` computed `rhox` and rewrote
    `brs = qg/rhox` (F:3680), so `brs + pgmlt/rhox = (qg+pgmlt)/rhox >= 0` for
    ANY density and ANY melt fraction. The states that look dangerous cannot
    reach the melt: that normalisation removes them. INSIDE the window `rhox`
    was never computed and `brs` was never normalised, and there a particle far
    above `rho_max` removes `pgmlt/900` from a volume holding far less.
    """
    f32 = np.float32
    rmin, rmax = f32(100.), f32(900.)

    # outside: normalised by ProgB_param, never negative
    for raw in (f32(2000.), f32(5000.), f32(50.)):
        qg = f32(1e-9)
        rhox = min(rmax, max(rmin, raw))
        brs_norm = f32(qg / rhox)                    # what ProgB_param leaves
        for frac in (0.5, 0.99, 1.0):
            v = f32(brs_norm + f32(f32(-qg * f32(frac)) / rhox))
            assert v >= 0, f"outside the window went negative at raw={raw}"

    # inside: not normalised, and it does go negative
    for qg, brs in ((f32(1e-9), f32(1e-16)), (f32(1e-10), f32(1e-16))):
        rho = min(rmax, max(rmin, f32(qg / brs)))
        v = f32(brs + f32(f32(-qg * f32(0.5)) / rho))
        assert v < 0, f"expected negative inside the window at qg={qg}"
        assert max(f32(0.), v) == 0


def test_g4_reuses_rhox_so_it_is_bit_exact_with_legacy_outside_the_window():
    """`rhox` already IS the pre-melt density -- ProgB_param computed it at
    F:1325 and nothing touches `qg` or `brs` before the melt at F:1400 -- so
    reusing it makes the expression literally legacy's. Recomputing `qg/brs`
    instead agrees only to within 1 ULP, which is a change this arm has no
    reason to make where its window does not apply."""
    src = mg.G4_TXN
    assert "melt_rho = rhox(i,k)" in src, "g4 no longer reuses rhox"
    assert "if(rhox(i,k).gt.0.) then" in src, "the reuse is not guarded on rhox"


def test_g4_can_floor_a_partial_melt_at_in_band_subnormal_volume():
    """The tiny denominator defeats the claimed raw-rho > 900 necessity."""
    f32 = np.float32
    q0, b0, a = f32(5e-37), f32(1e-39), f32(0.3)
    tau = np.finfo(f32).tiny
    pg = f32(-q0 * a)
    q1 = f32(q0 + pg)
    rho_c = min(f32(900), max(f32(100), f32(q0 / max(b0, tau))))
    g4 = max(f32(0), f32(b0 + f32(pg / rho_c)))
    g5 = f32(b0 * f32(q1 / q0))
    assert 100 < f32(q0 / b0) < 900
    assert b0 < tau and rho_c == f32(100)
    assert q1 > 0 and g4 == 0 and g5 > 0


def test_subnormal_admissible_volume_exists_without_being_unique():
    """qg=500*eta admits five positive f32 volumes; qg<100*eta admits none."""
    f32 = np.float32
    eta = np.nextafter(f32(0), f32(1))
    qg = f32(500) * eta
    candidates = [f32(n) * eta for n in range(1, 7)]
    admissible = [b for b in candidates if 100 <= f32(qg / b) <= 900]
    assert admissible == candidates[:5]
    # The largest possible density below 100*eta uses the smallest volume.
    assert f32((f32(99) * eta) / eta) < 100


def test_a_complete_melt_inside_the_clamp_lands_on_zero_at_f32():
    """g3 and g4 are the same statement there, and this is the arithmetic
    rather than the algebra: the measured operands give exactly 0.0f."""
    f32 = np.float32
    qg0, bg0 = f32(8.29644e-13), f32(9.21827e-16)
    rho = min(f32(900.), max(f32(100.), f32(qg0 / bg0)))
    assert f32(bg0 + f32(f32(-qg0) / rho)) == f32(0.0)


# ── g5 refuses the state it cannot answer (owner review 4.2) ────────────────

def test_g5_refuses_a_partial_melt_from_zero_volume():
    """`b+ = b0 * (q+/q0)` returns 0 when `b0 = 0`, leaving `qg > 0` with
    `bg = 0` -- the same inconsistency g4's floor produced, reached another
    way, and no finite density satisfies it. The window admits `brs <= brs_min`
    and nothing excludes `brs = 0` exactly, so the state is reachable."""
    src = mg.G5_TXN
    assert "error stop" in src, "g5 does not refuse; it may emit qg>0 with bg=0"
    assert "UNDEFINED partial melt" in src, "the refusal does not name the case"
    # The guard tests the RESULT. An input guard (`melt_bg0.gt.0.`) was the
    # first version and it let the underflow case through -- see
    # test_g5_guards_the_produced_volume_not_the_input.
    assert "if(brs(i,k).le.0.) then" in src


def test_the_zero_volume_partial_melt_really_is_inconsistent():
    """Arithmetic, not assertion: the proportional form gives exactly zero."""
    f32 = np.float32
    qg0, bg0 = f32(5e-10), f32(0.0)
    for frac in (0.1, 0.5, 0.9):
        pg = f32(-qg0 * f32(frac))
        qg1 = f32(qg0 + pg)
        assert qg1 > 0
        assert f32(bg0 * f32(qg1 / qg0)) == 0.0


def test_g5_still_answers_the_defined_cases():
    """The refusal must not swallow the branch it was added beside."""
    f32 = np.float32
    qg0, bg0 = f32(5e-10), f32(5e-13)          # positive volume
    pg = f32(-qg0 * f32(0.5))
    qg1 = f32(qg0 + pg)
    b1 = f32(bg0 * f32(qg1 / qg0))
    assert b1 > 0
    assert abs(float(qg1 / b1) - float(qg0 / bg0)) / float(qg0 / bg0) < 1e-5


def test_g5_guards_the_produced_volume_not_the_input():
    """`b0 > 0` is not enough. `b0 * (q+/q0)` UNDERFLOWS to zero when `b0` is
    near the smallest subnormal, so `qg+ > 0` arrives with `b+ = 0` anyway --
    which is the state the guard exists to refuse, reached past a guard that
    only looked at the input."""
    src = mg.G5_TXN
    assert "if(brs(i,k).le.0.) then" in src, "g5 guards the input, not the result"
    assert "error stop" in src


def test_the_underflow_really_produces_the_forbidden_state():
    """Arithmetic, at the reference precision, in the window's own range."""
    f32 = np.float32
    bg0 = f32(1e-45)                      # near the smallest subnormal
    for qg0, frac in ((f32(9.949e-44), 0.5), (f32(1e-40), 0.5), (f32(1e-40), 0.9)):
        qg1 = f32(qg0 + f32(-qg0 * f32(frac)))
        assert qg1 > 0
        assert f32(bg0 * f32(qg1 / qg0)) == 0.0, "expected underflow to zero"


def test_the_invariant_holds_wherever_g5_does_not_refuse():
    """Over the grid the review specifies: subnormal to qcrmin, zero to
    brs_min, melt fractions 0 to 1. Every state g5 accepts satisfies
    (qg+ > 0) <=> (b+ > 0)."""
    f32 = np.float32
    tiny = np.finfo(np.float32).tiny
    refused = accepted = 0
    for qg0 in (f32(1e-45), f32(1e-43), f32(1e-40), tiny, f32(1e-30), f32(1e-9)):
        for bg0 in (f32(1e-45), f32(1e-30), f32(1e-15),
                    f32(qg0 / f32(900.)), f32(qg0 / f32(100.))):
            for frac in (0.0, 1e-7, 0.1, 0.5, 0.9, 1.0):
                qg1 = f32(qg0 + f32(-qg0 * f32(frac)))
                b1 = f32(0.) if qg1 <= 0 else f32(bg0 * f32(qg1 / qg0))
                if qg1 > 0 and b1 <= 0:
                    refused += 1           # g5 error-stops here
                else:
                    accepted += 1
                    assert (qg1 > 0) == (b1 > 0)
                    assert 0 <= b1 <= max(float(bg0), 0.0)
    assert refused > 0 and accepted > 0
