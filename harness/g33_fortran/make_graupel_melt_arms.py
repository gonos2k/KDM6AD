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
    G2  compute rhox wherever there is positive mass AND positive volume, with
        the same clamp. At the failing cell that is 899.9997 and the full melt
        proceeds as physics.
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

G2_DIVIDE = (
    "! G2: compute the density here from positive mass and positive volume,\n"
    "! with ProgB_param's own clamp, rather than skipping the melt. At the\n"
    "! failing cell qg/brs is 899.9997, so this is a value the model already\n"
    "! considers valid -- it was simply below the amount thresholds.\n"
    "              if(qrs(i,k,3).gt.0. .and. brs(i,k).gt.0.) then\n"
    "                rhox(i,k) = min(melt_rho_max,max(melt_rho_min,qrs(i,k,3)/brs(i,k)))\n"
    "              endif\n"
    "              if(rhox(i,k).gt.0.) then\n"
    "                brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
    "              endif\n")

G3_DIVIDE = (
    "! G3: a complete melt needs no division. pgmlt is capped at -qrs(i,k,3),\n"
    "! so when it takes that bound the cell melts entirely and the volume goes\n"
    "! with the mass. Only a PARTIAL melt needs a density, and there rhox is\n"
    "! computed by construction.\n"
    "              if(qrs(i,k,3).le.0.) then\n"
    "                brs(i,k) = 0.\n"
    "              else if(rhox(i,k).gt.0.) then\n"
    "                brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
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
    if name not in ("g1", "g2", "g3"):
        raise SystemExit(f"unknown arm {name!r}; expected g1, g2 or g3")
    text = BASE.read_text()
    _check_constants(text)
    _once(text, MELT_OPEN, "melt open")
    _once(text, DIVIDE, "melt divide")
    _once(text, DECL_ANCHOR, "kdm62D locals")
    text = text.replace(DECL_ANCHOR, DECL_ADD)
    if name == "g1":
        return text.replace(MELT_OPEN, G1_OPEN)
    if name == "g2":
        return text.replace(DIVIDE, G2_DIVIDE)
    if name == "g3":
        _mass_update_precedes_divide(text)
        return text.replace(DIVIDE, G3_DIVIDE)
    raise AssertionError(f"unreachable: {name!r} passed the name check")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arm", choices=["g1", "g2", "g3"])
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
    if added + removed > 20:
        raise SystemExit(f"{a.arm}: {added} added / {removed} removed is more "
                         f"than a melt-block edit; check the anchors")
    print(f"       +{added} / -{removed} lines against the base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
