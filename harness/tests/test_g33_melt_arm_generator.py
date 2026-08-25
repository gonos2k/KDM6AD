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

def test_an_unknown_arm_is_refused_rather_than_returning_the_base():
    """Returning the unedited base for an unknown name would produce a file
    that compiles, runs, and is silently the legacy arm."""
    with pytest.raises(SystemExit) as e:
        mg.arm("g5")
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


def test_the_unfloored_arithmetic_really_does_go_negative():
    """The floor is not defensive decoration. Reproduced at the reference
    precision, since this is an f32 kernel."""
    f32 = np.float32
    qg0 = f32(1e-12)
    for raw, frac in ((f32(2000.), 0.5), (f32(5000.), 0.5), (f32(1000.), 0.95)):
        bg0 = f32(qg0 / raw)
        pgmlt = f32(-qg0 * f32(frac))
        rho = min(f32(900.), max(f32(100.), f32(qg0 / bg0)))
        unfloored = f32(bg0 + f32(pgmlt / rho))
        assert unfloored < 0, f"expected negative at raw={raw} frac={frac}"
        assert max(f32(0.), unfloored) == 0


def test_a_complete_melt_inside_the_clamp_lands_on_zero_at_f32():
    """g3 and g4 are the same statement there, and this is the arithmetic
    rather than the algebra: the measured operands give exactly 0.0f."""
    f32 = np.float32
    qg0, bg0 = f32(8.29644e-13), f32(9.21827e-16)
    rho = min(f32(900.), max(f32(100.), f32(qg0 / bg0)))
    assert f32(bg0 + f32(f32(-qg0) / rho)) == f32(0.0)
