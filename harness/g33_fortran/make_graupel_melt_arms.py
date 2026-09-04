#!/usr/bin/env python3
"""G1/G2/G3 -- three ways to stop the graupel melt dividing by an absent density.

`FINDING_thirty_second_step_overflows_v1` established the mechanism: `rhox` is
computed only under `qg > qcrmin .or. brs > brs_min` and clamped to [100, 900],
so the only route to infinity is it not being computed -- while the melt asks
`qg > 0.`. At the failing cell `qg/brs = 899.9997`, so the density is at the top
of the valid range and merely was not calculated.

That leaves three defensible branches, and the owner review asks for them to be
COMPARED rather than for one to be assumed:

    G1  align the melt's existence test with the density's -- skip the melt
        where rhox was not computed. The submitted freeze-lift request. Trace
        graupel stays, unmelted, and its latent heat and rain-mass transfer are
        skipped with it.
    G2  recompute rhox from POST-melt mass where mass and volume remain positive.
        This skips the division on a complete melt and changes partial melts;
        it is not the pre-melt counterfactual (G4).
    G3  a complete-melt branch. `pgmlt` is already capped at `-qg`, so where it
        takes that bound the cell melts entirely: set qg and brs to zero
        directly and never divide.

ANCHORED ON TEXT, NOT LINE NUMBERS. The arm-C attempt that preceded this cut
from `if (itimestep .eq. 1)` to the first `endif`, which is inside a nested
`if`, and produced a kernel that did not compile. Every edit here is matched
against an exact multi-line anchor and refuses unless it appears exactly once.
"""
import argparse
import hashlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE.parent.parent / "host/KIM-meso_v1.0/phys/module_mp_kdm6.F"

#: `brs_min`, `rho_min` and `rho_max` are LOCAL to `ProgB_param` (its lines
#: 3654-3657), so they are not in scope at the melt. Each arm that needs one
#: declares it beside `kdm62D`'s own locals -- and the generator checks the
#: value against ProgB_param's, because two copies of a threshold that disagree
#: would make the arms answer a different question than the one asked.
DECL_ANCHOR = "   real                               :: gfac, sfac\n"
DECL_ADD = ("   real                               :: gfac, sfac\n"
            "   real, parameter :: melt_brs_min = 1.e-15   ! = ProgB_param's brs_min\n"
            "   real, parameter :: melt_rho_min = 100.     ! = ProgB_param's rho_min\n"
            "   real, parameter :: melt_rho_max = 900.     ! = ProgB_param's rho_max\n")

#: The melt's existence test, and the division it leads to. Both are anchors.
MELT_OPEN = "            if(qrs(i,k,3).gt.0.) then\n"
DIVIDE = "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"

#: G3 does not reorder anything -- the base ALREADY updates the mass before the
#: volume (F:1416 then F:1419). That order is what makes `qrs(i,k,3).le.0.` mean
#: "this cell melted completely" instead of being dead code inside a block the
#: melt opened on `qrs(i,k,3).gt.0.`. So it is a property of the BASE that G3
#: depends on, and an unchecked dependency is the kind that breaks silently: a
#: revision moving the mass update below the divide would still pass every
#: anchor here and every line-count budget, and emit a G3 whose first branch
#: can never be taken.
MASS_UPDATE = "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n"

G1_OPEN = ("            if(qrs(i,k,3).gt.qcrmin .or. brs(i,k).gt.melt_brs_min) then\n"
           "! G1: the SAME existence test ProgB_param uses before computing rhox.\n"
           "! Where the density was not computed, the melt does not run either.\n")

#: WHAT G2 ACTUALLY IS, corrected. It was described as computing the density
#: at the failing cell from `qg/brs = 899.9997` and continuing the melt. It does
#: not, and cannot: this text replaces the DIVIDE, which sits AFTER the mass
#: update at F:1416, and in the measured window the melt is complete, so
#: `qrs(i,k,3)` is already 0 by the time G2's guard is reached. G2 removes the
#: defect by SKIPPING, like G1, by a different route.
#:
#: And it is not confined to the defect. Wherever the melt is PARTIAL, G2
#: recomputes `rhox` from the POST-melt mass, which is a different density than
#: the pre-melt one ProgB_param supplied -- so it perturbs every melting cell.
#: That is why its 5 s digest differs from legacy while G1 and G3 are
#: bit-identical, and why it is not the targeted counterfactual it was named as.
#: The pre-melt counterfactual is G4 below.
G2_DIVIDE = (
    "! G2: recompute the density from the POST-melt mass, with ProgB_param's\n"
    "! own clamp. NOTE this is not a pre-melt density: the mass update at\n"
    "! F:1416 has already run, so on a complete melt qg is 0 here and this\n"
    "! guard is false. It changes every PARTIALLY melting cell.\n"
    "              if(qrs(i,k,3).gt.0. .and. brs(i,k).gt.0.) then\n"
    "                rhox(i,k) = min(melt_rho_max,max(melt_rho_min,qrs(i,k,3)/brs(i,k)))\n"
    "              endif\n"
    "              if(rhox(i,k).gt.0.) then\n"
    "                brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
    "              endif\n")

G3_DIVIDE = (
    "! G3: a complete melt needs no division. pgmlt is capped at -qrs(i,k,3),\n"
    "! so when it takes that bound the cell melts entirely and the volume goes\n"
    "! with the mass. A PARTIAL melt needs a density; rhox can still be absent\n"
    "! inside the threshold window, where this arm leaves volume unchanged.\n"
    "              if(qrs(i,k,3).le.0.) then\n"
    "                brs(i,k) = 0.\n"
    "              else if(rhox(i,k).gt.0.) then\n"
    "                brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
    "              endif\n")


#: CONTAINMENT, and why g4 reuses `rhox`. Where ProgB_param computed it, it
#: ALSO rewrote `brs` to `qg/rhox` (F:3680), and nothing touches `qg` or `brs`
#: between that call (F:1325) and the melt -- so `rhox` already IS the pre-melt
#: density and reusing it is bit-exact with legacy. Recomputing `qg/brs` there
#: instead agrees to within 1 ULP (measured: 191151 of 200000 f32 draws exact,
#: worst relative 7.6e-08), which is a change this arm has no reason to make
#: outside its own window.
#:
#: THE NEGATIVE VOLUME IS A WINDOW-ONLY HAZARD, narrower than first recorded.
#: Outside the window ProgB_param left `brs = qg/rhox`, so
#: `brs + pgmlt/rhox = (qg+pgmlt)/rhox >= 0` for ANY density and ANY melt
#: fraction -- the states that looked dangerous cannot reach the melt, because
#: that normalisation removes them. INSIDE the window `brs` was never
#: normalised, and a particle far above `rho_max` removes `pgmlt/900` from a
#: volume holding much less: qg 1e-9 over brs 1e-16 gives -5.55e-13 at a half
#: melt. Hence the floor, for that reason and not the wider one.
#: A raw density above 900 is not necessary below tiny(f32): the recomputation
#: divides by max(bg0,tiny), so qg0=5e-37, bg0=1e-39, a=0.3 uses rho_c=100
#: and floors at raw rho0 about 500. For positive bg0 and a partial melt the
#: real-arithmetic condition is a*rho0 >= rho_c WITH that denominator bound;
#: f32 boundary cases require evaluating the actual rounded candidate.
#: G4 replaces the whole transaction -- the three state updates AND the divide --
#: because the counterfactual it tests needs the PRE-melt mass, and by the time
#: the divide runs the mass update has already consumed it. G2 was named as this
#: experiment and is not it.
#:
#: On a COMPLETE melt G4 and G3 both explicitly set brs=0. This follows from
#: their branch code, without assuming an in-band density or an exact quotient.
#: Nine partial window occurrences have since been measured; G3 leaves volume
#: unchanged there when rhox is absent. See FINDING_melt_arm_g5_and_number_policy_v1.
TXN_ANCHOR = (
    "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n"
    "              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)\n"
    "              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)\n"
    "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n")

G4_TXN = (
    "! G4: the pre-melt mass and volume decide the density, and a complete melt\n"
    "! takes the volume with the mass instead of dividing.\n"
    "              melt_qg0 = qrs(i,k,3)\n"
    "              melt_bg0 = brs(i,k)\n"
    "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n"
    "              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)\n"
    "              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)\n"
    "              if(qrs(i,k,3).le.0.) then\n"
    "                brs(i,k) = 0.\n"
    "              else\n"
    "! g4: rhox already IS the pre-melt density where ProgB_param computed it,\n"
    "! so reuse it -- recomputing differs by up to 1 ULP for no reason.\n"
    "                if(rhox(i,k).gt.0.) then\n"
    "                  melt_rho = rhox(i,k)\n"
    "                else\n"
    "                  melt_rho = min(melt_rho_max,max(melt_rho_min,           &\n"
    "                             melt_qg0/max(melt_bg0,tiny(melt_bg0))))\n"
    "                endif\n"
    "! A bulk volume cannot be negative; only inside the window can it go there.\n"
    "                brs(i,k) = max(0.,melt_bg0 + (pgmlt(i,k)/melt_rho))\n"
    "              endif\n")

#: G4 alone needs mutable scalars. Kept OUT of the shared declaration so g1, g2
#: and g3 still generate the exact bytes their measurements were taken on.
DECL_G4 = ("   real :: melt_qg0, melt_bg0, melt_rho\n")

#: The budget is "not more than a melt-block edit", and g4's melt-block edit is
#: legitimately larger -- it rewrites the transaction rather than one line.
MAX_EDIT = {"g1": 20, "g2": 20, "g3": 20, "g4": 30, "g5": 30}


#: A ZERO POST-MELT VOLUME HAS NO ANSWER, so g5 refuses instead of inventing one.
#:
#: The first version of this guard tested `b0 > 0` -- the INPUT -- and a sweep
#: over the subnormal grid found 14 states it lets through: with `b0` near the
#: smallest subnormal (1.4e-45), `b0 * (q+/q0)` UNDERFLOWS to zero at a half
#: melt, so `qg+ > 0` arrives with `b+ = 0` anyway. The window's own `qg` runs
#: 1e-43 to 1e-40 on the measured column, which is exactly that region.
#:
#: `b+ = b0 * (q+/q0)` is exact when `b0 > 0`. When `b0 = 0` and the melt is
#: PARTIAL it returns 0 with `q+ > 0` -- the same `qg > 0, bg = 0` state g4's
#: floor produced, reached a different way, and no finite density satisfies it.
#: The state is reachable: the window admits `brs <= brs_min` and nothing
#: excludes `brs = 0` exactly.
#:
#: Four policies are available -- fail, skip like g1, reconstruct with a chosen
#: trace density, or promote to a complete melt -- and they are not equivalent
#: in mass or number. Choosing one is the owner's, so this arm FAILS LOUDLY: an
#: `error stop` naming the cell. A diagnostic that quietly picks a density hides
#: the very case it was built to find.
#:
#: g5 is the window-only transaction the review asked for, and it is the arm
#: that makes g4's floor unnecessary rather than safe.
#:
#: OUTSIDE the window `rhox` is positive and the expression is legacy's, to the
#: bit. INSIDE it the volume is scaled by the MASS FRACTION:
#:
#:     b+ = b0 * (q+ / q0)
#:
#: which preserves q+/b+ = q0/b0 in real arithmetic for positive operands.
#: Rounded products can underflow; the result guard below refuses nonpositive
#: volume while mass remains. It also preserves an inadmissible raw density,
#: so fewer zero candidates do not establish a production remedy. The earlier
#: 50000-draw result (0 negatives, relative density drift <=1e-5) is sample-scoped.
G5_TXN = (
    "! G5: legacy exactly where rhox exists; inside the window scale the volume\n"
    "! by the mass fraction, which preserves the pre-melt density.\n"
    "              melt_qg0 = qrs(i,k,3)\n"
    "              melt_bg0 = brs(i,k)\n"
    "              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)\n"
    "              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)\n"
    "              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)\n"
    "              if(rhox(i,k).gt.0.) then\n"
    "                brs(i,k) = melt_bg0 + (pgmlt(i,k)/rhox(i,k))\n"
    "              else if(qrs(i,k,3).le.0.) then\n"
    "                brs(i,k) = 0.\n"
    "              else\n"
    "                brs(i,k) = melt_bg0*(qrs(i,k,3)/melt_qg0)\n"
    "! THE RESULT DECIDES, NOT THE INPUT. b0 > 0 is not enough: b0 * (q+/q0)\n"
    "! UNDERFLOWS to zero when b0 is near the smallest subnormal, leaving\n"
    "! qg+ > 0 with b+ = 0 -- no finite density satisfies it. Guarding b0 alone\n"
    "! missed that; this guards what was actually produced.\n"
    "                if(brs(i,k).le.0.) then\n"
    "                  write(*,*) 'G33 G5 UNDEFINED partial melt zero volume', &\n"
    "                             i, k, melt_qg0, melt_bg0, qrs(i,k,3)\n"
    "                  error stop 'g5: partial melt leaves positive mass, zero volume'\n"
    "                endif\n"
    "              endif\n")


def _once(text: str, anchor: str, what: str) -> None:
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(f"{what}: anchor matched {n} times, expected 1")


def _check_constants(text: str) -> None:
    """The arms' copies must equal ProgB_param's, or they answer another question.

    Two assumptions are checked rather than relied on. That each threshold is
    declared EXACTLY ONCE: with more than one declaration the first match is an
    arbitrary choice among scopes, and comparing against the wrong scope's value
    would pass while the arm ran on another. And the values are compared as
    NUMBERS -- `100.` and `100.0` are the same threshold, and a comparison that
    calls them different fails a correct base.
    """
    import re
    for name, mine in (("brs_min", "1.e-15"), ("rho_min", "100."), ("rho_max", "900.")):
        found = re.findall(rf"::\s*{name}\s*=\s*([0-9.eEdD+-]+)", text)
        if len(found) != 1:
            raise SystemExit(
                f"{name}: {len(found)} declarations in the base, expected 1 -- "
                f"cannot tell which scope the arms should match")
        if float(found[0].replace("d", "e").replace("D", "e")) != float(mine):
            raise SystemExit(f"{name} is {found[0]} in ProgB_param and {mine} here")


def _mass_update_precedes_divide(text: str) -> None:
    """G3's `qrs(i,k,3).le.0.` branch is only reachable if the mass update
    already ran; see MASS_UPDATE."""
    _once(text, MASS_UPDATE, "graupel mass update")
    if text.index(MASS_UPDATE) > text.index(DIVIDE):
        raise SystemExit(
            "the graupel mass update no longer precedes the volume update, so "
            "g3's complete-melt branch would be dead code; the base moved")


def arm(name: str) -> str:
    """The kernel source for one arm, from the pinned base.

    The NAME is checked before the base is opened. A bad argument should be a
    bad argument on every host, not a FileNotFoundError wherever the reference
    tree is absent -- which is everywhere but the owner's machine.
    """
    if name not in ("g1", "g2", "g3", "g4", "g5"):
        raise SystemExit(f"unknown arm {name!r}; expected g1, g2, g3, g4 or g5")
    text = BASE.read_text()
    _check_constants(text)
    _once(text, MELT_OPEN, "melt open")
    _once(text, DIVIDE, "melt divide")
    _once(text, DECL_ANCHOR, "kdm62D locals")
    text = text.replace(DECL_ANCHOR,
                        DECL_ADD + (DECL_G4 if name in ("g4", "g5") else ""))
    if name == "g1":
        return text.replace(MELT_OPEN, G1_OPEN)
    if name == "g2":
        return text.replace(DIVIDE, G2_DIVIDE)
    if name == "g3":
        _mass_update_precedes_divide(text)
        return text.replace(DIVIDE, G3_DIVIDE)
    if name == "g4":
        _once(text, TXN_ANCHOR, "melt transaction")
        return text.replace(TXN_ANCHOR, G4_TXN)
    if name == "g5":
        _once(text, TXN_ANCHOR, "melt transaction")
        return text.replace(TXN_ANCHOR, G5_TXN)
    raise AssertionError(f"unreachable: {name!r} passed the name check")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arm", choices=["g1", "g2", "g3", "g4", "g5"])
    ap.add_argument("--out", type=pathlib.Path, required=True)
    a = ap.parse_args()
    src = arm(a.arm)
    a.out.write_text(src)
    print(f"  {a.arm}: {a.out}  sha {hashlib.sha256(src.encode()).hexdigest()[:16]}")
    # THE EDIT MUST HAVE CHANGED SOMETHING, AND ONLY A LITTLE. A positional
    # zip() comparison counts every line after an insertion as changed -- it
    # reported 3001 for a three-line edit. difflib aligns them.
    import difflib
    base = BASE.read_text().splitlines()
    got = src.splitlines()
    added = removed = 0
    for line in difflib.unified_diff(base, got, n=0, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"): added += 1
        elif line.startswith("-") and not line.startswith("---"): removed += 1
    if added == removed == 0:
        raise SystemExit(f"{a.arm}: the edit changed nothing")
    cap = MAX_EDIT[a.arm]
    if added + removed > cap:
        raise SystemExit(f"{a.arm}: {added} added / {removed} removed is more "
                         f"than a melt-block edit (cap {cap}); check the anchors")
    print(f"       +{added} / -{removed} lines against the base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
