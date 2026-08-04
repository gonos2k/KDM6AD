#!/usr/bin/env python3
"""Write a TEMPORARY G3.3-M instrumentation overlay of a reference Fortran variant.

Protocol §5.1: the canonical Fortran is NEVER edited (frozen). This reads a
canonical microphysics module (legacy `module_mp_kdm6.F` or conservative
`module_mp_kdm6_cons.F`), verifies its SHA against the pin, inserts
`#ifdef KDM6_G33_FORTRAN_DUMP`-guarded op-record emission at unique whole-line
anchors, and writes a throw-away patched copy. Compiled WITHOUT the macro it is
byte-identical behaviour; WITH it, the sed ladder is dumped to stdout.

    make_fortran_overlay.py <canonical.F> <out_overlay.F> [--algo legacy|conservative]

Three responsibilities only: verify the SHA, apply the bindings' patches, write
the output. The field VOCABULARY comes from the public schema
(`g33_schema.op_fields`); the Fortran EXPRESSIONS + anchors come from
`g33_fortran_bindings`. `_validate_against_schema()` asserts the two agree, in
order, for every (role, species, op) in scope — a drift fails here, loudly.

Each emitted line: G33OP <i> <k_topfirst> <n> <op_id>.<field> <dtype> <hex>
(Z8.8 / Z16.16 / Z2.2). Fortran k is bottom-up (kts..kte); we emit k = kte-k.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import g33_schema as schema  # noqa: E402
import g33_fortran_bindings as fb  # noqa: E402

_EMIT = {  # dtype -> (value expr wrapping the operand, Z format width)
    "f32": ("transfer({e}, 0)",   "Z8.8"),
    "f64": ("transfer({e}, 0_8)", "Z16.16"),
    "i32": ("transfer({e}, 0)",   "Z8.8"),
    "u8":  ("merge(1, 0, {e})",   "Z2.2"),
}


def _stage_write(stage, chain, n_expr, field, k_expr, dtype, expr,
                 loop_expr="loop"):
    """protocol v2:
    G33F STAGE <outer_loop> <chain> <stage> <n> <field> <col> <k> <dtype> <hex>
    `loop` is the RUNTIME cloud-subcycle index (kdm62D's `do loop = 1,loops`, which
    encloses every injection point), so records from different outer loops are
    distinguishable instead of collapsing onto loop 1."""
    val, zf = _EMIT[dtype]
    return (f"{fb.IND}write(*,'(A,1X,I0,2(1X,A),1X,I0,1X,A,2(1X,I0),1X,A,1X,{zf})') "
            f"'G33F STAGE', {loop_expr}, '{chain}', '{stage}', {n_expr}, "
            f"'{field}', i, {k_expr}, '{dtype}', {val.format(e=expr)}")


def _stage_block(stage, chain, n_expr, col_fields, whole_k_fields,
                 loop_expr="loop"):
    """An injected whole-K emission loop for a pre-sed stage snapshot. Per-column
    scalars (mstep/gate/dtcld) carry k=-1; whole-K fields carry top-first kte-k."""
    lines = ["#ifdef KDM6_G33_FORTRAN_DUMP", f"{fb.IND}do i = its, ite"]
    for field, dtype, expr in col_fields:
        lines.append(_stage_write(stage, chain, n_expr, field, "-1", dtype, expr,
                                  loop_expr))
    lines.append(f"{fb.IND}  do k = kts, kte")
    for field, dtype, expr in whole_k_fields:
        lines.append(_stage_write(stage, chain, n_expr, field, "kte-k", dtype,
                                  expr, loop_expr))
    lines += [f"{fb.IND}  end do", f"{fb.IND}end do", "#endif"]
    return lines


#: How far after a resolved anchor its landmark may sit. Wide enough for the
#: comment block a dump site carries, narrow enough that the next call site
#: cannot satisfy it.
_LANDMARK_WINDOW = 12


def _cell_stage_block(stage, chain, n_expr, fields, loop_expr="loop"):
    """Emission for an injection point ALREADY INSIDE `do k` / `do i`.

    _stage_block opens its own loops, which at a site like the state update would
    nest a second `do i` inside the live one and emit B*K records per cell. Here
    the surrounding loops supply i and k; only the top-first k = kte-k conversion
    is applied, exactly as the injected-loop form does.
    """
    return ["#ifdef KDM6_G33_FORTRAN_DUMP",
            *[_stage_write(stage, chain, n_expr, f, "kte-k", dt, e, loop_expr)
              for f, dt, e in fields],
            "#endif"]


def _validate_against_schema(algo):
    """Emitted field list MUST equal schema.op_fields(...), in order, for every
    (role, species, op) in scope — ties the bindings to the one schema."""
    for role in ("TOP", "INTERIOR"):
        for species in ("qr", "nr"):
            for op_id in schema.ops_for_species(algo, role, species):
                want = [f for f, _ in schema.op_fields(algo, role, op_id)]
                got = [f for f, _, _ in fb.FIELD_EXPR[algo][role][op_id]]
                if got != want:
                    raise SystemExit(
                        f"schema drift: {algo}/{role}/{op_id} bindings {got} "
                        f"!= schema {want}")
                # dtypes must match too.
                sd = {f: dt for f, dt in schema.op_fields(algo, role, op_id)}
                for f, dt, _ in fb.FIELD_EXPR[algo][role][op_id]:
                    if sd[f] != dt:
                        raise SystemExit(
                            f"dtype drift: {algo}/{role}/{op_id}.{f} bindings {dt} "
                            f"!= schema {sd[f]}")


def _emit_lines(algo, role, species, phase):
    """The op-emission lines for one (role, species) — top-first k = kte-k. Each
    line is  G33FOP <loop> <chain> <n> <col> <k_top> <op_id> <field> <dtype> <hex>,
    where <loop> is the RUNTIME cloud-subcycle index (was a hardcoded literal).
    phase 'pre' emits every field EXCEPT the actual post-update q_post/n_post;
    phase 'post' emits ONLY those (the stored value, read after the update)."""
    body = []
    for op_id in schema.ops_for_species(algo, role, species):
        for field, dtype, expr in fb.FIELD_EXPR[algo][role][op_id]:
            is_post = field in fb.POST_FIELDS
            if (phase == "pre") == is_post:
                continue
            val, zf = _EMIT[dtype]
            body.append(
                f"{fb.IND}write(*,'(A,1X,I0,1X,A,3(1X,I0),1X,A,1X,A,1X,A,1X,{zf})') "
                f"'G33FOP', loop, 'main', n, i, kte-k, "
                f"'{op_id}', '{field}', '{dtype}', {val.format(e=expr)}")
    return ["#ifdef KDM6_G33_FORTRAN_DUMP", *body, "#endif"] if body else []


def _cap_lines(top):
    """Cell-entry capture of fall/falln into scratch temps. The TOP capture also
    emits each column's mstep ONCE (guarded n==1; every column is active at n=1)
    so the parser can derive the active (col,n) universe independently."""
    lines = ["#ifdef KDM6_G33_FORTRAN_DUMP",
             f"{fb.IND}g33_fqb = fall(i,k,1)",
             f"{fb.IND}g33_fnb = falln(i,k,1)"]
    if top:
        lines.append(
            f"{fb.IND}if (n .eq. 1) write(*,'(A,1X,I0,1X,A,1X,I0,1X,A,1X,Z8.8)') "
            f"'G33F MSTEP', loop, 'main', i, 'i32', mstep(i)")
    lines.append("#endif")
    if top:
        # The ICE sub-step count, under its OWN macro and its OWN record name.
        # Not `G33F MSTEP ... 'ice'`: that record is keyed (loop, chain, col) and
        # the four-case semantics validator iterates every (loop, chain) scope,
        # looking up substep_pre by (n, field, col) with NO chain -- so an ice
        # scope would compare ice counts against the main chain's substep_pre and
        # raise. And any unrecognised G33F line is a hard parse error. Keeping
        # this out of KDM6_G33_FORTRAN_DUMP leaves the decision-grade stream
        # byte-for-byte what it was.
        lines += ["#ifdef KDM6_G33_NUMBER_DUMP",
                  f"{fb.IND}if (n .eq. 1) write(*,'(A,1X,I0,1X,I0,1X,A,1X,Z8.8)') "
                  f"'G33F MSTEPI', loop, i, 'i32', mstep_i(i)",
                  "#endif"]
    return lines


def _xfer_lines(chain, mass, num):
    """Emit the bottom cell's ACTUAL capped transfers, once per sub-step.

    Guarded on `k == kts`: that cell's outflow leaves the domain, so it is the
    surface transfer -- and unlike `falln` it is what the kernel really moved.
    Pure emission: no kernel value is read that the next statement does not
    already use, and nothing is written.
    """
    return ["#ifdef KDM6_G33_NUMBER_DUMP",
            f"{fb.IND}if (k .eq. kts) write(*,'(A,3(1X,I0),2(1X,A),2(1X,Z8.8))') "
            f"'G33F XFER', loop, n, i, '{chain}', 'f32', "
            f"transfer({mass}, 0), transfer({num}, 0)",
            "#endif"]


def _cap_inflow_lines(chain, own, inflow, own_n, inflow_n):
    """A cell's OWN outflow beside the inflow it grants the cell below.

    Paired across an interface these give departure and arrival, and their
    difference under the rho*dz measure is the mass the interface destroys.
    """
    return ["#ifdef KDM6_G33_NUMBER_DUMP",
            f"{fb.IND}write(*,'(A,4(1X,I0),2(1X,A),4(1X,Z8.8))') "
            f"'G33F CAPIN', loop, n, i, kte-k, '{chain}', 'f32', "
            f"transfer({own}, 0), transfer({inflow}, 0), "
            f"transfer({own_n}, 0), transfer({inflow_n}, 0)",
            "#endif"]


def _top_lines(chain, removed, removed_n):
    """The top cell's actual removal, emitted BEFORE its update so the pre-update
    content is still there to cap against."""
    return ["#ifdef KDM6_G33_NUMBER_DUMP",
            f"{fb.IND}write(*,'(A,4(1X,I0),2(1X,A),2(1X,Z8.8))') "
            f"'G33F TOPOUT', loop, n, i, kte-k, '{chain}', 'f32', "
            f"transfer({removed}, 0), transfer({removed_n}, 0)",
            "#endif"]


def build_overlay(algo, text):
    """Patched source for `algo`, or SystemExit if any anchor is not present
    EXACTLY once (a source change). Anchors are matched as WHOLE lines."""
    cfg = fb.VARIANTS[algo]
    lines = text.split("\n")

    edits = [(fb.DECL_ANCHOR, "after", fb.DECL_BLOCK),
             (cfg["cap_top"], "after", _cap_lines(top=True)),
             (cfg["cap_int"], "after", _cap_lines(top=False)),
             # pre-sed snapshots at the sub-cycle boundary: outer_pre_sed once
             # BEFORE `do n=1,mstepmax`, substep_pre per-n right AFTER it.
             # after the entry padding, ONCE per kernel call (loop 0) — the clamp is
             # before `do loop = 1,loops`, so the runtime loop index is not in scope
             # the kdm6init-derived module constants, once per run, from inside the
             # module where they are in scope (owner P0-1.1)
             (fb.AFTER_ENTRY_CLAMP_ANCHOR, "before",
              _stage_block("kernel_init_constants", "-", "0", [],
                           fb.INIT_CONSTANTS, loop_expr="0")),
             (fb.AFTER_ENTRY_CLAMP_ANCHOR, "before",
              _stage_block("kernel_after_entry_clamp", "-", "0", [],
                           fb.AFTER_ENTRY_CLAMP, loop_expr="0")),
             (fb.STAGE_ANCHOR, "before",
              _stage_block("outer_pre_sed", "-", "0", [], fb.OUTER_PRE_SED)),
             (fb.STAGE_ANCHOR, "after",
              _stage_block("substep_pre", "main", "n", fb.SUBSTEP_PRE_COL,
                           fb.SUBSTEP_PRE_K)),
             # the outer-loop CAUSAL BRIDGE (owner P0-C1): the sedimentation result
             # at the end of the ice chain, and the state the NEXT outer loop starts
             # from at the end of the loop body. Without them a divergence first
             # visible at loop 2's outer_pre_sed has no attributable origin.
             # the ProgB bundle the micro rates consume, per outer loop
             (fb.MICRO_CALL_AUX_ANCHOR, "after",
              _stage_block("micro_call_progb_aux", "-", "0", [], fb.MICRO_CALL_AUX)),
             # v14 freeze-heat captures: zero per cell in the rate-init loop,
             # base + xlf at the head of the freeze loop, each rate at its own
             # t-store (BEFORE it — the store consumes its operand)
             (fb.FREEZE_ZERO_ANCHOR, "after", fb.FREEZE_ZERO_BLOCK),
             (fb.FREEZE_BASE_ANCHOR, "after", fb.FREEZE_BASE_BLOCK),
             *[(anchor, "before",
                ["#ifdef KDM6_G33_FORTRAN_DUMP", f"            {stmt}", "#endif"])
               for anchor, stmt in fb.FREEZE_CAPTURES],
             # the post-freeze STATE, at the same anchor and after the ProgB
             # bundle — the C++ emits them in that order too
             (fb.MICRO_CALL_AUX_ANCHOR, "after",
              _stage_block("micro_post_freeze", "-", "0", [], fb.MICRO_POST_FREEZE)),
             (fb.MICRO_CALL_AUX_ANCHOR, "after",
              _stage_block("micro_freeze_heat", "-", "0", [], fb.MICRO_FREEZE_HEAT)),
             # the post-D1-melt state, per cell (still inside do k / do i)
             (fb.MICRO_POST_MELT_ANCHOR, "after",
              _cell_stage_block("micro_post_melt", "-", "0", fb.MICRO_POST_MELT)),
             # the EXACT base state_update reads, once per cell, BEFORE the
             # F:2638 branch (the state is unmodified from there to either arm's
             # `!     update`, so one record covers both)
             (fb.MICRO_PRE_STATE_UPDATE_ANCHOR, "before",
              _cell_stage_block("micro_pre_state_update", "-", "0",
                                fb.MICRO_PRE_STATE_UPDATE)),
             # the qr update's operands, in BOTH arms of the F:2638 branch: the
             # rates are scaled per-arm, so the scaled values only exist inside,
             # and every cell takes exactly one arm so each emits exactly once.
             (fb.MICRO_QR_OPERANDS_COLD_ANCHOR, "after",
              _cell_stage_block("micro_qr_operands", "-", "0", fb.MICRO_QR_OPERANDS)),
             (fb.MICRO_QR_OPERANDS_WARM_ANCHOR, "after",
              _cell_stage_block("micro_qr_operands", "-", "0", fb.MICRO_QR_OPERANDS)),
             # the bisection of the micro step: after the state update and its brs
             # re-clamp, before Picons/satadj (F:3032, the sixth ProgB_param call)
             (fb.MICRO_POST_STATE_UPDATE_ANCHOR, "after",
              _stage_block("micro_post_state_update", "-", "0", [],
                           fb.MICRO_POST_STATE_UPDATE)),
             (fb.POST_SED_ANCHOR, "after",
              _stage_block("outer_post_sed", "-", "0", [], fb.OUTER_POST_SED)),
             (fb.POST_MICRO_ANCHOR, "before",
              _stage_block("outer_post_micro", "-", "0", [], fb.OUTER_POST_MICRO)),
             # surface bottom-fall operands, per column, at the accumulation (k=-1;
             # already inside `do i` so no injected loop).
             (fb.SURFACE_ANCHOR, "after",
              ["#ifdef KDM6_G33_FORTRAN_DUMP",
               *[_stage_write("surface", "-", "0", f, "-1", dt, e)
                 for f, dt, e in fb.SURFACE_FIELDS],
               "#endif"]),
             # The surface NUMBER flux, which no driver can reach: falln is a
             # kernel LOCAL (F:719). Operands, not a result -- the same discipline
             # SURFACE_FIELDS follows. Its own macro keeps it out of the
             # decision-grade record universe, whose field set is a v14 contract
             # with the C++ mirror.
             (fb.SURFACE_ANCHOR, "after",
              ["#ifdef KDM6_G33_NUMBER_DUMP",
               *[f"{fb.IND}write(*,'(A,1X,I0,1X,I0,2(1X,A),1X,Z8.8)') "
                 f"'G33F NFLUX', loop, i, '{f}', 'f32', transfer({e}, 0)"
                 for f, e in fb.SURFACE_NUMBER_FIELDS],
               "#endif"])]
    edits += [(a, "after", _xfer_lines(ch, m, n))
              for a, ch, m, n in fb.XFER_SITES]
    edits += [(a, "after", _cap_inflow_lines(ch, c, u, cn, un))
              for a, ch, c, u, cn, un in fb.CAP_SITES]
    edits += [(a, "before", _top_lines(ch, r, rn))
              for a, ch, r, rn in fb.TOP_SITES]
    for (role, species), anchor in cfg["emit"].items():
        edits.append((anchor, "before", _emit_lines(algo, role, species, "pre")))
    for (role, species), anchor in cfg["post"].items():
        edits.append((anchor, "after", _emit_lines(algo, role, species, "post")))

    # a line may take BOTH a before-block and an after-block (legacy: the update
    # line gets the pre-ladder before + the actual q_post after).
    plan = {}
    for anchor, place, block in edits:
        # An anchor may be (line, occurrence[, landmark]): several injection points sit
        # on lines that repeat verbatim — `call slope_kdm6(...)` occurs seven times, once
        # per rate block — and requiring a unique line would mean either finding no anchor
        # at all or picking a nearby unique COMMENT, which drifts independently of the
        # code it is standing in for. An explicit occurrence index says which one and
        # still fails loudly if the count changes.
        #
        # The occurrence index is 0-BASED, and reading it as "the nth" is how the
        # micro_post_state_update stage got injected after the SEVENTH ProgB_param call
        # (post-satadj) when it meant the sixth (pre-Picons). Nothing failed: both are
        # real ProgB calls, so the overlay built, the run produced records, and the
        # comparison silently ran against a different instant than the C++ side.
        #
        # `landmark` is the fix, and it is not a convention tweak: a substring that must
        # appear within _LANDMARK_WINDOW lines after the resolved point. It states which
        # site was MEANT in terms of the source itself, so an off-by-one lands on a
        # different site and says so, instead of producing evidence about the wrong place.
        want = landmark = None
        if isinstance(anchor, tuple):
            if len(anchor) == 3:
                # want may be None: a UNIQUE line can still carry a
                # landmark, and there is no reason to make it count
                # occurrences to get one.
                anchor, want, landmark = anchor
            else:
                anchor, want = anchor
        idx = [i for i, ln in enumerate(lines) if ln == anchor]
        if want is None:
            if len(idx) != 1:
                raise SystemExit(
                    f"anchor matched {len(idx)} whole lines, expected 1 — the source "
                    f"changed:\n  {anchor}")
            at = idx[0]
        else:
            n, total = want
            if len(idx) != total:
                raise SystemExit(
                    f"anchor matched {len(idx)} whole lines, expected {total} — the "
                    f"source changed:\n  {anchor}")
            at = idx[n]
        if landmark is not None:
            window = lines[at + 1:at + 1 + _LANDMARK_WINDOW]
            if not any(landmark in ln for ln in window):
                raise SystemExit(
                    f"anchor resolved to source line {at + 1}, but the landmark that "
                    f"names the intended site is not within {_LANDMARK_WINDOW} lines "
                    f"after it:\n  anchor:   {anchor}\n  landmark: {landmark}\n"
                    f"Either the occurrence index is wrong (it is 0-BASED) or the "
                    f"source moved.")
        plan.setdefault(at, {"before": [], "after": []})[place] += block

    out = []
    for i, ln in enumerate(lines):
        pl = plan.get(i)
        if pl:
            out.extend(pl["before"])
        out.append(ln)
        if pl:
            out.extend(pl["after"])
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="G3.3-M temporary Fortran overlay generator")
    ap.add_argument("src", help="canonical reference module (.F)")
    ap.add_argument("dst", help="output overlay path (.F)")
    ap.add_argument("--algo", default="legacy", choices=sorted(fb.VARIANTS))
    args = ap.parse_args()

    _validate_against_schema(args.algo)
    raw = open(args.src, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != fb.VARIANTS[args.algo]["sha"]:
        raise SystemExit(
            f"canonical {args.algo} SHA {got} != pinned {fb.VARIANTS[args.algo]['sha']} "
            f"— the reference changed; re-verify anchors and re-pin")

    open(args.dst, "w", encoding="utf-8").write(build_overlay(args.algo, raw.decode("utf-8")))
    print(f"wrote {args.algo} overlay: {args.dst}")


if __name__ == "__main__":
    main()
