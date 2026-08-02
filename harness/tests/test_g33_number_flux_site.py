"""The number-flux and ice-mstep sites must stay OUT of the decision stream.

`falln` and `mstep_i` are kernel locals, so reaching them needs an overlay site.
The four-case decision protocol's record universe is a v14 contract with the C++
mirror, and its Fortran parser rejects any unrecognised `G33F` line outright — so
these emissions live under their own macro, which the decision-bundle build never
defines. These tests hold that separation in place.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "g33_fortran"))
import g33_fortran_bindings as fb          # noqa: E402
import make_fortran_overlay as mo          # noqa: E402
import g33_fortran_dump as fd              # noqa: E402

NUMBER_MACRO = "KDM6_G33_NUMBER_DUMP"
DUMP_MACRO = "KDM6_G33_FORTRAN_DUMP"
REFINE = ROOT / "g33_fortran" / "refine_build.sh"
DECISION = ROOT / "g33_fortran" / "fortran_build.sh"


@pytest.fixture(scope="module")
def overlay():
    src = (ROOT.parent / "host/KIM-meso_v1.0/phys/module_mp_kdm6.F")
    if not src.exists():
        pytest.skip("pinned reference tree not present (host/** is gitignored)")
    return mo.build_overlay("legacy", src.read_text()).splitlines()


def _guard_of(lines, needle):
    """The macro whose #ifdef encloses the line containing `needle`, or None if
    it is emitted unconditionally — which is a different defect from not being
    emitted at all, so they are not reported as the same thing."""
    for i, ln in enumerate(lines):
        if needle in ln and not ln.startswith("#"):
            for j in range(i, -1, -1):
                if lines[j].startswith("#ifdef"):
                    return lines[j].split()[1]
                if lines[j] == "#endif":
                    break                # closed before reaching an opener
            return None                  # emitted, but under no guard
    raise AssertionError(f"{needle!r} not emitted at all")


def test_the_new_emissions_sit_under_their_own_macro(overlay):
    assert _guard_of(overlay, "'G33F MSTEPI'") == NUMBER_MACRO
    assert _guard_of(overlay, "'G33F NFLUX'") == NUMBER_MACRO


def test_the_existing_decision_emissions_are_untouched(overlay):
    """A regression here means the decision stream gained or lost records."""
    assert _guard_of(overlay, "'G33F MSTEP',") == DUMP_MACRO
    assert _guard_of(overlay, "'bottom_fall_qr'") == DUMP_MACRO


def test_the_decision_parser_would_REJECT_these_records():
    """This is WHY the separate macro exists, not a style preference: the
    four-case parser raises on any G33F line it does not recognise."""
    for line in ("G33F MSTEPI 1 2 i32 00000003",
                 "G33F NFLUX 1 2 bottom_falln_nr f32 43328F48"):
        assert not any(p.match(line) for p in fd._KNOWN)


def test_an_ice_chain_MSTEP_record_would_have_been_the_wrong_fix():
    """`G33F MSTEP <loop> ice <col> ...` parses -- which is the trap. run.mstep is
    keyed (loop, chain, col) and the semantics validator iterates every scope,
    looking up substep_pre with NO chain, so an ice scope compares ice counts
    against the main chain's records."""
    assert fd._MSTEP_V3.match("G33F MSTEP 1 ice 2 i32 00000003")
    src = (ROOT / "g33_fortran" / "g33_fortran_semantics.py").read_text()
    assert "for loop, chain in scopes:" in src
    assert '_sv(S, "substep_pre", n, "mstep", c, -1, loop)' in src


def test_the_decision_build_never_defines_the_number_macro():
    assert NUMBER_MACRO not in DECISION.read_text()


def test_only_nflux_turns_the_macro_on():
    text = REFINE.read_text()
    assert f"-D{NUMBER_MACRO}" in text
    # the flag that enables it, and the plain --dump path that must not
    assert re.search(r'--nflux\)\s+DUMP=1; NFLUX=1', text)
    assert re.search(r'--dump\)\s+DUMP=1 ;;', text)


def test_the_flux_operands_are_operands_not_a_product():
    """Forming falln*den*delz*dtcld in Fortran would bury the unit reasoning in
    an expression nobody reviews. The analysis forms it; the kernel emits parts."""
    names = [f for f, _ in fb.SURFACE_NUMBER_FIELDS]
    assert names == ["bottom_falln_nr", "bottom_falln_ni",
                     "nflux_den", "nflux_delz", "nflux_dtcld"]
    exprs = dict(fb.SURFACE_NUMBER_FIELDS)
    assert exprs["bottom_falln_nr"] == "falln(i,kts,1)"    # rain number
    assert exprs["bottom_falln_ni"] == "falln(i,kts,2)"    # ice number
    assert all("*" not in e for e in exprs.values())
