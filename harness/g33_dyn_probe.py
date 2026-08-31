#!/usr/bin/env python3
"""Write the dynamics stage-probe overlay, and read what it dumps.

Freeze-lift `REQUEST_freeze_lift_dyn_first_write_probe.md`, granted 2026-08-30.
The canonical `dyn_em/solve_em.F` is never edited: this reads it, verifies its
SHA against the pin, inserts `#ifdef KDM6_G33_DYN_DUMP`-guarded emission at
unique whole-line anchors and writes a throw-away patched copy -- the same
protocol 5.1 rule `g33_fortran/make_fortran_overlay.py` follows for the
microphysics.

    g33_dyn_probe.py overlay <canonical.F> <out_overlay.F>
    g33_dyn_probe.py first-difference   <np1_dump_dir> <np4_dump_dir>
    g33_dyn_probe.py halo-vs-reference  <np1_dump_dir> <np4_dump_dir>
    g33_dyn_probe.py halo-content       <np4_dump_dir>

WHY BENCH_END ANCHORS. Every phase in the RK loop ends with a `BENCH_END(<name>)`
macro on a line of its own, and each name occurs once in the file. A multi-line
CALL has no unique last line; its timer does. Anchoring on the timer puts the
probe exactly at the end of the phase it names, and a drift in the file makes
the anchor missing rather than silently misplaced.

WHY ONLY THE FIRST RK STAGE. The request's prediction is that the first
difference appears at or before `rk_tendency` in the first step, so the probe
covers `itimestep == 1 .AND. rk_step == 1`. That is also what keeps the dump at
about 320 MB per run: `rk_step == 1` runs exactly one acoustic sub-step, so the
twelve anchors fire twelve times and not fifty-six.

WHY PATCH BOUNDS NAME THE FILE. Each rank needs its own file and the rank id
would mean adding `wrf_get_myproc` to a USE list -- a change outside the
`#ifdef`. `ips/ipe/jps/jpe` are already in scope and are unique per rank.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

#: The canonical file this overlay is authorized against (request, Scope).
PIN = "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f"

#: i windows the probe writes: 16 columns either side of each 4x1 patch
#: boundary (59, 117, 176), plus the eastern lateral-boundary zone.
WINDOWS = [(43, 75), (101, 133), (160, 192), (214, 234)]

#: Field groups the probe can dump. STATE is the prognostic set; HALO is what
#: `HALO_EM_A` actually exchanges, read from the Registry
#: (`8:ru,rv,rw,ww,php,alt,al,p,muu,muv,mut,rho`) and NOT intersecting STATE --
#: a probe that watched only STATE around the exchange would be blind to a halo
#: defect; TEND is what `rk_tendency` writes. Kind: M mass-level 3-D, Z
#: vertically staggered 3-D, S 2-D.
#:
#: GROUP 4 IS THE INPUT SET OF ONE STENCIL, dumped over the memory window so the
#: HALO copies come too. `calc_ww_cp` builds `divv(i,k)` at the last owned mass
#: column from one column EAST: `muu(i+1)` -- which is `0.5*(mup+mub)(i+1) +
#: (i)` -- times `u(i+1)` over `msfuy(i+1)`. Those four arrays are the whole of
#: what a 4x1 cut can carry into `ww`: the `rdy` half of the same expression
#: reads `j+1`, and j is not decomposed here, so it sits at owned i on every
#: rank. If all four match bitwise the mechanism is refuted, because the rest of
#: the expression is the same operations on owned data in the same order.
GROUPS = {
    1: [("u_2", "M", "X"), ("t_2", "M", "M"), ("ph_2", "Z", "M"),
        ("w_2", "Z", "M"), ("mu_2", "S", "M")],
    2: [("ru", "M", "X"), ("rv", "M", "Y"), ("rw", "Z", "M"), ("ww", "Z", "M"),
        ("php", "Z", "M"), ("alt", "M", "M"), ("al", "M", "M"), ("p", "M", "M"),
        ("rho", "M", "M"), ("muu", "S", "X"), ("muv", "S", "Y"),
        ("mut", "S", "M")],
    3: [("ru_tend", "M", "X"), ("rv_tend", "M", "Y"), ("rw_tend", "Z", "M"),
        ("ph_tend", "Z", "M"), ("t_tend", "M", "M"), ("mu_tend", "S", "M")],
    4: [("u_2", "M", "X"), ("mu_2", "S", "M"), ("mub", "S", "M"),
        ("msfuy", "S", "X")],
}

#: Groups dumped over the MEMORY window (halo copies included) rather than owned
#: cells: 2 asks whether the exchange delivered, 4 asks whether what a stencil
#: READS at the patch edge is stale.
HALO_WINDOW = (2, 4)

#: `grid%` prefixed, except the tendencies the Registry declares as i1 locals.
LOCAL = {"rw_tend", "ph_tend", "t_tend", "mu_tend"}

#: (stage id, groups, anchor line, where). Stage 0 is the timestep entry and
#: stage 1 the entry of EACH RK stage -- `Runge_Kutta_loop: DO rk_step = ...` is
#: the latter, so without stage 0 a difference made before the loop is unseen.
#: 31 and 32 straddle the halo exchange: without the "before" dump there is no
#: way to separate "the halo arrived wrong" from "the halo was right and a later
#: stencil diverged".
ANCHORS = [
    (0, (1, 4), "   Runge_Kutta_loop:  DO rk_step = 1, rk_order", "before"),
    (1, (1, 4), "   Runge_Kutta_loop:  DO rk_step = 1, rk_order", "after"),
    (2, (1, 2), "BENCH_END(step_prep_tim)", "after"),
    (31, (2,), '#    include "HALO_EM_A.inc"', "before"),
    (32, (2,), '#    include "HALO_EM_A.inc"', "after"),
    (4, (1,), "BENCH_END(set_phys_bc_tim)", "after"),
    (5, (1, 3), "BENCH_END(rk_tend_tim)", "after"),
    (6, (1, 2, 3), "BENCH_END(relax_bdy_dry_tim)", "after"),
    (7, (1, 2), "BENCH_END(small_step_prep_tim)", "after"),
    (8, (1,), "BENCH_END(advance_uv_tim)", "after"),
    (9, (1,), "BENCH_END(spec_bdy_uv_tim)", "after"),
    (10, (1,), "BENCH_END(advance_mu_t_tim)", "after"),
    (11, (1,), "BENCH_END(advance_w_tim)", "after"),
    (12, (1,), "BENCH_END(small_step_finish_tim)", "after"),
]

#: The overlay defines the macro itself, so the build needs no flag and
#: `configure.wrf` is not touched -- it is outside the granted scope. The
#: `#ifdef` still earns its place: it marks every added line so the audit below
#: can prove the overlay adds nothing else, and emission is gated a SECOND time
#: on the dump environment, which is what makes B and C the same executable.
DEFINE = "#define KDM6_G33_DYN_DUMP\n"

CALL = """#ifdef KDM6_G33_DYN_DUMP
{calls}#endif
"""

HELPER = """#ifdef KDM6_G33_DYN_DUMP

CONTAINS

!  G3.3-M dynamics stage probe. Host-associated: it reads `grid`, the patch
!  bounds and `rk_step` from solve_em and writes nothing back. Emission is
!  conditional on the macro AND on KDM6_G33_DYN_DUMP_DIR being set, so the
!  instrumented binary with no dump environment must be byte-identical to the
!  canonical one -- which is the acceptance gate.
   SUBROUTINE g33_dyn_stage ( stage, grp )
      IMPLICIT NONE
      INTEGER, INTENT(IN) :: stage, grp
      INTEGER, PARAMETER  :: nwin = {nwin}
      INTEGER, PARAMETER  :: win(2,nwin) = RESHAPE( (/ {win} /), (/ 2, nwin /) )
      INTEGER, SAVE       :: un = -1
!  NEWUNIT hands back a NEGATIVE unit number, so the sign of `un` cannot stand
!  in for "opened" -- testing it that way armed nothing and wrote a zero-byte
!  file. `armed` says it instead.
      LOGICAL, SAVE       :: asked = .FALSE., armed = .FALSE.
      CHARACTER(LEN=512)  :: dir, fn
      INTEGER             :: st, w, i0, i1, ju, ku, iu

!  The first step's first RK stage only: that is what the request predicts about,
!  and rk_step 1 takes exactly one acoustic sub-step, which bounds the dump.
      IF ( grid%itimestep /= 1 ) RETURN
!  Stage 0 sits ABOVE the RK loop, where `rk_step` has not been assigned yet, so
!  it must not be tested there -- doing so silently dropped every stage-0 record.
      IF ( stage /= 0 .AND. rk_step /= 1 ) RETURN

      IF ( .NOT. asked ) THEN
         asked = .TRUE.
         CALL GET_ENVIRONMENT_VARIABLE( 'KDM6_G33_DYN_DUMP_DIR', dir, STATUS=st )
         IF ( st == 0 .AND. LEN_TRIM(dir) > 0 ) THEN
            WRITE( fn, '(A,A,I0,A,I0,A,I0,A,I0,A)' ) TRIM(dir), '/g33dyn_i', &
                   ips, '-', ipe, '_j', jps, '-', jpe, '.bin'
            OPEN( NEWUNIT=un, FILE=TRIM(fn), FORM='UNFORMATTED', ACCESS='STREAM', &
                  STATUS='REPLACE', ACTION='WRITE', IOSTAT=st )
            armed = ( st == 0 )
         END IF
      END IF
      IF ( .NOT. armed ) RETURN

!  Mass points stop one short of the staggered end in each direction; writing to
!  the memory bound instead would compare memory the model never set, and two
!  runs can differ there without the model differing at all.
      ju = MIN( jpe, jde-1 )
      ku = MIN( kpe, kde-1 )
      iu = MIN( ipe, ide-1 )

      DO w = 1, nwin
!  Groups 2 and 4 are dumped over the MEMORY window, clipped to the domain, so a
!  rank's halo copies come too -- that is the only way to ask whether the halo
!  arrived wrong (2) or was read stale (4). Everything else is owned cells.
         IF ( {halowin} ) THEN
            i0 = MAX( MAX( ims, ids ), win(1,w) )
            i1 = MIN( MIN( ime, ide-1 ), win(2,w) )
         ELSE
            i0 = MAX( ips, win(1,w) )
            i1 = MIN( iu, win(2,w) )
         END IF
         IF ( i0 > i1 ) CYCLE
         WRITE(un) stage, grp, i0, i1, jps, ju, kps, ku, ips, iu
         SELECT CASE ( grp )
{cases}         END SELECT
      END DO
      FLUSH(un)
   END SUBROUTINE g33_dyn_stage

#endif
"""



def _call(stage: int, grps) -> str:
    return CALL.format(calls="".join(
        f"      CALL g33_dyn_stage ( {stage}, {g} )\n" for g in grps))


def _slice(kind: str) -> str:
    return {"M": "(i0:i1,kps:ku ,jps:ju)",
            "Z": "(i0:i1,kps:kpe,jps:ju)",
            "S": "(i0:i1,        jps:ju)"}[kind]


def _cases() -> str:
    out = []
    for g, fields in sorted(GROUPS.items()):
        out.append(f"         CASE ( {g} )\n")
        for name, kind, _ in fields:
            who = name if name in LOCAL else f"grid%{name}"
            out.append(f"            WRITE(un) REAL( {who}{_slice(kind)}, 4 )\n")
    return "".join(out)


def build(src: str) -> str:
    lines = src.splitlines(keepends=True)
    out, placed = [], {}
    for ln in lines:
        key = ln.rstrip("\n").strip()
        for n, grps, anchor, where in ANCHORS:
            if key != anchor.strip() or where != "before":
                continue
            placed[n] = True
            out.append(_call(n, grps))
        out.append(ln)
        for n, grps, anchor, where in ANCHORS:
            if key != anchor.strip() or where != "after":
                continue
            if n in placed:
                raise SystemExit(f"anchor for stage {n} is not unique: {anchor!r}")
            placed[n] = True
            out.append(_call(n, grps))
    missing = [n for n, _, _, _ in ANCHORS if n not in placed]
    if missing:
        raise SystemExit(f"anchors not found for stages {missing}")

    body = "".join(out)
    tail = "END SUBROUTINE solve_em"
    if body.count(tail) != 1:
        raise SystemExit(f"{tail!r} is not unique")
    win = ", ".join(f"{a}, {b}" for a, b in WINDOWS)
    helper = HELPER.format(
        nwin=len(WINDOWS), win=win, cases=_cases(),
        halowin=" .OR. ".join(f"grp == {g}" for g in HALO_WINDOW))
    return DEFINE + body.replace(tail, helper + tail, 1)


def strip_guarded(text: str) -> str:
    """The overlay with every `KDM6_G33_DYN_DUMP` block removed.

    This is the audit the request promises, and it is stronger than counting
    added lines: if deleting the guarded regions gives the canonical back BYTE
    FOR BYTE, then the overlay adds only guarded lines and changes nothing else.
    Nested conditionals inside a guarded block are counted so the matching
    `#endif` is the one that closes it.
    """
    lines = text.splitlines(keepends=True)
    if lines and lines[0] == DEFINE:
        lines = lines[1:]
    out, depth = [], 0
    for ln in lines:
        s = ln.strip()
        if depth:
            if s.startswith(("#if", "#ifdef", "#ifndef")):
                depth += 1
            elif s.startswith("#endif"):
                depth -= 1
            continue
        if s == "#ifdef KDM6_G33_DYN_DUMP":
            depth = 1
            continue
        out.append(ln)
    if depth:
        raise SystemExit("unbalanced KDM6_G33_DYN_DUMP block in the overlay")
    return "".join(out)



def read_dump(path: Path) -> dict:
    """One rank's file as {(stage, grp, i, owned): {field: array}}.

    OWNERSHIP IS IN THE KEY, not the value: the same global column is owned
    on one rank and a halo copy on its neighbour, and both must survive a
    merge across ranks for `halo_content` and `halo_vs_reference` to be able
    to ask whether they agree.

    THE EMITTER AND THE PARSER LIVE IN ONE FILE because a record layout that
    drifts between them produces numbers that look fine and are not. WRF is
    built with -fconvert=big-endian here, so its stream writes are big-endian.
    """
    import numpy as np
    raw = np.fromfile(path, dtype=np.uint8)
    out, off = {}, 0
    while off < raw.size:
        stage, grp, i0, i1, jps, ju, kps, ku, ips, iu = (
            int(v) for v in raw[off:off + 40].view(">i4"))
        off += 40
        ni, nj, nk = i1 - i0 + 1, ju - jps + 1, ku - kps + 1
        for name, kind, _ in GROUPS[grp]:
            n = ni * nj * (1 if kind == "S" else nk + (1 if kind == "Z" else 0))
            a = raw[off:off + 4 * n].view(">f4")
            off += 4 * n
            a = a.reshape((ni, nj) if kind == "S" else
                          (ni, nk + (1 if kind == "Z" else 0), nj), order="F")
            for c in range(ni):
                i = i0 + c
                rec = out.setdefault((stage, grp, i, ips <= i <= iu), {})
                rec[name] = a[c]
    return out


def _load(d: Path) -> dict:
    """Every rank's records merged on (stage, group, i, owned).

    A KEY IS CLAIMED BY EXACTLY ONE FILE. Two ranks holding the same global
    column with the same ownership flag is not a merge to resolve -- their two
    values can legitimately differ, and `setdefault(...).update(...)` would keep
    whichever file sorted last and report the pair as agreeing. Refuse instead.
    """
    out, owner = {}, {}
    for f in sorted(d.glob("g33dyn_*.bin")):
        for k, v in read_dump(f).items():
            if k in owner:
                raise SystemExit(
                    f"duplicate dump key {k}: written by {owner[k].name} "
                    f"and {f.name}; the two values cannot be merged")
            owner[k], out[k] = f, v
    if not out:
        raise SystemExit(f"no g33dyn_*.bin records under {d}")
    return out


def first_difference(dir_a: Path, dir_b: Path) -> list:
    """Per stage, group and field, the OWNED i columns where the two differ.

    Compared as raw words: one ULP is a difference, which is the point of asking
    where it is first written. Halo copies are excluded here -- the same global
    cell exists owned on one rank and as a halo copy on its neighbour, and
    mixing them would either hide a halo mismatch or invent a difference.
    """
    import numpy as np
    A, B = _load(dir_a), _load(dir_b)
    _require_same_coverage(A, B, dir_a, dir_b)
    rows = []
    for stage, grp in sorted({(s, g) for s, g, _, _ in A}):
        for name, _, _ in GROUPS[grp]:
            hit = [i for (s, g, i, own) in sorted(A)
                   if s == stage and g == grp and own
                   and not np.array_equal(A[(s, g, i, own)][name].view(np.uint32),
                                          B[(s, g, i, own)][name].view(np.uint32))]
            rows.append({"stage": stage, "group": grp, "field": name, "columns": hit})
    return rows


def _require_same_coverage(A: dict, B: dict, dir_a: Path, dir_b: Path) -> None:
    """Both arms must carry the SAME records, or the comparison is not defined.

    An intersection is a fail-open: a stage the emitter never wrote on one arm
    silently leaves that stage out and the run reports no difference there. That
    is not hypothetical -- the first build of this probe dropped stage 0 on both
    arms because its guard tested `rk_step` above the loop that assigns it, and
    only a hand count of the records found it.

    Checked here: the (stage, group) universe against what ANCHORS declares, the
    owned-cell key sets against each other, and the field list per record.
    """
    want = {(st, g) for st, grps, _, _ in ANCHORS for g in grps}
    cols = {i for a, b in WINDOWS for i in range(a, b + 1)}
    want_keys = {(s, g, i) for (s, g) in want for i in cols}
    for tag, D, d in (("A", A, dir_a), ("B", B, dir_b)):
        have = {(s, g) for s, g, _, _ in D}
        if have != want:
            raise SystemExit(
                f"{tag} ({d}) stage/group coverage != ANCHORS: "
                f"missing {sorted(want - have)}, unexpected {sorted(have - want)}")
        # AGAINST THE DECLARED DENOMINATOR, not just against each other. Two arms
        # that drop the SAME record agree, and agreement was the whole test until
        # now (owner review 11): a window missing on both sides passed as "no
        # difference". `ANCHORS` x `WINDOWS` is what the probe promised to write,
        # so it is what a comparison has to find.
        #
        # SCOPE: this closes symmetric omission on the OWNED i axis only. The
        # expected j and k extents, the per-record word count, and the expected
        # set of halo copies are still not checked against a declared value, so
        # two arms that both truncate j, drop a level, or lose one halo direction
        # would still pass here.
        got = {(s, g, i) for (s, g, i, own) in D if own}
        if got != want_keys:
            raise SystemExit(
                f"{tag} ({d}) owned coverage != ANCHORS x WINDOWS "
                f"({len(want_keys)} expected): missing {sorted(want_keys - got)[:8]} "
                f"({len(want_keys - got)}), unexpected {sorted(got - want_keys)[:8]} "
                f"({len(got - want_keys)})")
    for (s, g, i, own) in A:
        want_f = {n for n, _, _ in GROUPS[g]}
        for tag, D in (("A", A), ("B", B)):
            got = set(D[(s, g, i, own)])
            if got != want_f:
                raise SystemExit(
                    f"{tag} record {(s, g, i, own)} fields != GROUPS[{g}]: "
                    f"missing {sorted(want_f - got)}, extra {sorted(got - want_f)}")
    _require_same_payload(A, B, dir_a, dir_b)


def _require_same_payload(A: dict, B: dict, dir_a: Path, dir_b: Path) -> None:
    """The j and k extent of every record, against every other and across arms.

    The i axis is checked against `ANCHORS` x `WINDOWS` above, and that was the
    whole of it until now (owner review 6): two arms that both truncate j, both
    drop a vertical level, or both write a field at the wrong shape agree with
    each other and pass. There is no declared j/k universe to check against --
    the extents come from the domain at run time -- but there is something
    stronger available for free: every record of a given KIND must have the SAME
    shape, in one arm and between arms, because j is not decomposed here and the
    vertical is whole. A truncation shows up as a second shape.
    """
    shapes = {}
    for tag, D in (("A", A), ("B", B)):
        for (s, g, i, own), rec in D.items():
            for name, kind, _ in GROUPS[g]:
                shapes.setdefault(kind, {}).setdefault(rec[name].shape, []).append(
                    (tag, s, g, i, name))
    for kind, byshape in sorted(shapes.items()):
        if len(byshape) > 1:
            detail = "; ".join(f"{sh} e.g. {ex[0]}" for sh, ex in sorted(byshape.items()))
            raise SystemExit(
                f"kind {kind!r} records do not share one shape across {dir_a} and "
                f"{dir_b}: {detail}. A j truncation or a dropped level looks like "
                f"this, and agreeing arms would hide it.")


def halo_content(dump_dir: Path) -> list:
    """Within ONE decomposition: does a rank's halo copy match the owner's value?

    This needs no `np=1` run. If a halo copy differs from the owned value of the
    same global cell after the exchange, the halo arrived wrong; if it matches,
    the exchange did its job and a later difference came from somewhere else.
    """
    import numpy as np
    D = _load(dump_dir)
    rows = []
    for stage, grp in sorted({(s, g) for s, g, _, _ in D}):
        for name, _, _ in GROUPS[grp]:
            bad = [i for (s, g, i, own) in sorted(D)
                   if s == stage and g == grp and not own
                   and (s, g, i, True) in D
                   and not np.array_equal(D[(s, g, i, False)][name].view(np.uint32),
                                          D[(s, g, i, True)][name].view(np.uint32))]
            rows.append({"stage": stage, "group": grp, "field": name, "columns": bad})
    return rows


def halo_vs_reference(ref_dir: Path, dec_dir: Path) -> list:
    """Each rank's HALO copy against the single-patch value at the same global i.

    `first_difference` compares OWNED cells only, and is right to: the same
    global cell is owned on one rank and a halo copy on its neighbour, and
    mixing them either hides a halo mismatch or invents a difference. But the
    input a stencil READS at the patch edge is exactly that halo copy, so
    asking whether it is stale needs this comparison and not that one.

    Per FILE, so the answer is per rank. Two ranks can hold a halo copy of the
    same column, and `_load` merges by global index -- which is what makes it
    the wrong loader for this question.
    """
    import numpy as np
    R = _load(ref_dir)
    rows, skipped = [], set()
    for f in sorted(Path(dec_dir).glob("g33dyn_*.bin")):
        D = read_dump(f)
        for stage, grp in sorted({(s, g) for s, g, _, _ in D}):
            for name, _, _ in GROUPS[grp]:
                cand = [(s, g, i, own) for (s, g, i, own) in sorted(D)
                        if s == stage and g == grp and not own]
                skipped |= {k[:3] for k in cand if (k[0], k[1], k[2], True) not in R}
                bad = [i for (s, g, i, own) in cand
                       if (s, g, i, True) in R
                       and not np.array_equal(
                           D[(s, g, i, own)][name].view(np.uint32),
                           R[(s, g, i, True)][name].view(np.uint32))]
                rows.append({"rank": f.stem.replace("g33dyn_", ""), "stage": stage,
                             "group": grp, "field": name, "columns": bad})
    # A HALO COLUMN THE REFERENCE DOES NOT HOLD IS NOT A MATCH. It was skipped,
    # and a silent skip reads as agreement in a table that only prints
    # disagreements (owner review 11). Report the count so a zero has a
    # denominator.
    if skipped:
        rows.append({"rank": "(skipped)", "stage": -1, "group": -1,
                     "field": "no-reference", "columns": sorted(i for _, _, i in skipped)})
    return rows


SEAMS = (59, 117, 176)


def _report(rows, key: str | None = None) -> None:
    head = f"  {'stage':>5} {'grp':>3} {'field':>8} {'cols':>6}   columns / nearest boundary"
    print(f"  {key:>18}{head}" if key else head)
    for r in rows:
        c = r["columns"]
        if not c:
            continue
        near = min(SEAMS, key=lambda s: min(abs(i - s) for i in c))
        lead = f"  {r[key]:>18}" if key else ""
        print(f"{lead}  {r['stage']:>5} {r['group']:>3} {r['field']:>8} {len(c):>6}   "
              f"{c[:9]}{' ...' if len(c) > 9 else ''}  nearest boundary {near}")


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "first-difference":
        if len(sys.argv) != 4:
            raise SystemExit("first-difference <np1_dump_dir> <np4_dump_dir>")
        print("  np=1 vs np=4, OWNED cells (blank stages agree everywhere)")
        _report(first_difference(Path(sys.argv[2]), Path(sys.argv[3])))
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "halo-vs-reference":
        if len(sys.argv) != 4:
            raise SystemExit("halo-vs-reference <np1_dump_dir> <np4_dump_dir>")
        print("  np=4 HALO copies vs np=1 at the same global column "
              "(blank = the halo a stencil reads there is current)")
        _report(halo_vs_reference(Path(sys.argv[2]), Path(sys.argv[3])), key="rank")
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "halo-content":
        if len(sys.argv) != 3:
            raise SystemExit("halo-content <np4_dump_dir>")
        print("  within np=4: halo copy vs the owner's value (blank = halo is right)")
        _report(halo_content(Path(sys.argv[2])))
        return 0
    argv = sys.argv[2:] if len(sys.argv) >= 2 and sys.argv[1] == "overlay" else sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit(__doc__.splitlines()[0])
    src_path, out_path = Path(argv[0]), Path(argv[1])
    src = src_path.read_text()
    got = hashlib.sha256(src.encode()).hexdigest()
    if got != PIN:
        raise SystemExit(
            f"REFUSED: {src_path} is {got[:16]}, and this overlay is authorized "
            f"against {PIN[:16]}. A different canonical needs a re-read of the "
            f"anchors, not a re-pin.")
    overlay = build(src)
    back = strip_guarded(overlay)
    if back != src:
        raise SystemExit(
            "REFUSED: removing the guarded blocks does not give the canonical "
            "back, so the overlay changes something outside the #ifdef.")
    out_path.write_text(overlay)
    print(f"{out_path}: {len(ANCHORS)} probes, {len(WINDOWS)} i windows, "
          f"canonical {got[:16]}")
    print(f"  audit: guarded blocks removed == canonical, byte for byte "
          f"(1 #define + {len(overlay.splitlines()) - len(src.splitlines()) - 1} guarded lines added)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
