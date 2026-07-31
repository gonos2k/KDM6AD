"""A stage that claims to mirror a reconciled dump must sit at that dump.

Four placement defects in this protocol have had one shape: the two backends
record instants that are not the same instant, and nothing fails, because both
instants are real program points. Existing guards cover part of it —
test_g33_overlay_orientation catches a K-flip, the Fortran anchor landmark
catches an off-by-one occurrence index — but nothing checked the C++ side's own
claim.

The fourth defect was exactly that gap. `micro_post_freeze`'s comment said it
sat on the reconciled `postfreeze` dump; the code sat 25 lines earlier, ahead of
`working.brs = pre2.progb.bg`. It reported `brs` as 8.8% divergent at every level
of one column, and the difference healed completely at the next stage — because
the Fortran side records after `ProgB_param` has rewritten `brs` in place. The
comment was right and the code was somewhere else.

So the mirror relationship is declared here and checked mechanically. The
`kdm6_dump_state_substep(state, "tag")` calls are the reconciled points: the
pinned Fortran writes `fort_substep_<tag>.bin` at the corresponding place and
says so in its own comments, which is why these are the sites worth reusing
rather than establishing new ones.
"""
import pathlib
import re

import pytest

OVERLAY = (pathlib.Path(__file__).resolve().parents[1]
           / "g33_overlay" / "coordinator.cpp.overlay")

#: G3.3 stage -> the substep-dump tag it mirrors. A state stage recorded at a
#: point with no reconciled counterpart does not belong here; it belongs in a
#: discussion about whether that point can be corresponded at all.
MIRRORS = {
    "micro_post_melt": "postmelt",
    "micro_post_freeze": "postfreeze",
    "micro_pre_state_update": "prestate",
    "micro_post_state_update": "poststateupdate",
}

#: How far the G33 emission may sit from the dump it mirrors. Wide enough for the
#: `#endif` and the block's own comment header, narrow enough that another
#: statement — an assignment to the state being recorded, say — cannot fit
#: between them unnoticed.
MAX_LINES = 20


def _lines():
    return OVERLAY.read_text().split("\n")


def _find(pattern):
    return [i for i, ln in enumerate(_lines()) if re.search(pattern, ln)]


@pytest.mark.parametrize("stage,tag", sorted(MIRRORS.items()))
def test_the_stage_sits_at_the_dump_it_mirrors(stage, tag):
    dumps = _find(rf'kdm6_dump_state_substep\([^,]+,\s*"{tag}"\)')
    assert len(dumps) == 1, f'expected exactly one "{tag}" substep dump, found {len(dumps)}'
    opens = _find(rf'Outer g33\("{stage}"')
    assert len(opens) == 1, f"expected exactly one {stage} container, found {len(opens)}"

    gap = opens[0] - dumps[0]
    assert 0 < gap <= MAX_LINES, (
        f"{stage} opens at line {opens[0] + 1} but the `{tag}` dump it mirrors is at "
        f"line {dumps[0] + 1} (gap {gap}). It must follow the dump, closely: anything "
        f"in between runs before the record and makes it a different instant from the "
        f"Fortran side's.")


@pytest.mark.parametrize("stage,tag", sorted(MIRRORS.items()))
def test_nothing_executable_sits_between_the_dump_and_the_record(stage, tag):
    """The gap may hold guards and comments — not statements.

    This is the specific failure: `working.brs = pre2.progb.bg` between the two
    meant the record was taken before a value the Fortran side had already
    rewritten.
    """
    lines = _lines()
    d = _find(rf'kdm6_dump_state_substep\([^,]+,\s*"{tag}"\)')[0]
    o = _find(rf'Outer g33\("{stage}"')[0]
    offenders = []
    for i in range(d + 1, o):
        s = lines[i].strip()
        if not s or s.startswith("//") or s.startswith("#") or s in ("{", "}"):
            continue
        offenders.append((i + 1, s))
    assert not offenders, (
        f"{stage}: executable code between the `{tag}` dump and the record — the "
        f"record is then taken at a different instant than the dump it claims to "
        f"mirror:\n" + "\n".join(f"  line {n}: {s}" for n, s in offenders))


def test_every_state_mirroring_stage_is_declared():
    """A new state stage added at a dump site must be listed, or it is unchecked."""
    opened = set(re.findall(r'Outer g33\("([a-z_]+)"', OVERLAY.read_text()))
    dump_tags = set(re.findall(r'kdm6_dump_state_substep\([^,]+,\s*"([a-z_]+)"\)',
                               OVERLAY.read_text()))
    # Stages named after a dump tag are mirrors whether or not they say so.
    implied = {s for s in opened if any(s.endswith(t) or t in s for t in dump_tags)}
    assert implied <= set(MIRRORS), (
        f"stage(s) {sorted(implied - set(MIRRORS))} look like dump mirrors but are "
        f"not declared in MIRRORS, so nothing checks where they sit")
