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


def _stage_write(stage, n_expr, field, k_expr, dtype, expr):
    val, zf = _EMIT[dtype]
    return (f"{fb.IND}write(*,'(A,1X,I0,1X,A,2(1X,I0),1X,A,1X,{zf})') "
            f"'G33F STAGE {stage}', {n_expr}, '{field}', i, {k_expr}, "
            f"'{dtype}', {val.format(e=expr)}")


def _stage_block(stage, n_expr, col_fields, whole_k_fields):
    """An injected whole-K emission loop for a pre-sed stage snapshot. Per-column
    scalars (mstep/gate/dtcld) carry k=-1; whole-K fields carry top-first kte-k."""
    lines = ["#ifdef KDM6_G33_FORTRAN_DUMP", f"{fb.IND}do i = its, ite"]
    for field, dtype, expr in col_fields:
        lines.append(_stage_write(stage, n_expr, field, "-1", dtype, expr))
    lines.append(f"{fb.IND}  do k = kts, kte")
    for field, dtype, expr in whole_k_fields:
        lines.append(_stage_write(stage, n_expr, field, "kte-k", dtype, expr))
    lines += [f"{fb.IND}  end do", f"{fb.IND}end do", "#endif"]
    return lines


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
    line is  G33FOP <loop> <chain> <n> <col> <k_top> <op_id> <field> <dtype> <hex>.
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
                f"{fb.IND}write(*,'(A,3(1X,I0),1X,A,1X,A,1X,A,1X,{zf})') "
                f"'G33FOP 1 main', n, i, kte-k, '{op_id}', '{field}', '{dtype}', "
                f"{val.format(e=expr)}")
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
            f"{fb.IND}if (n .eq. 1) write(*,'(A,1X,I0,1X,A,1X,Z8.8)') "
            f"'G33F MSTEP', i, 'i32', mstep(i)")
    lines.append("#endif")
    return lines


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
             (fb.STAGE_ANCHOR, "before",
              _stage_block("outer_pre_sed", "0", [], fb.OUTER_PRE_SED)),
             (fb.STAGE_ANCHOR, "after",
              _stage_block("substep_pre", "n", fb.SUBSTEP_PRE_COL, fb.SUBSTEP_PRE_K)),
             # surface bottom-fall operands, per column, at the accumulation (k=-1;
             # already inside `do i` so no injected loop).
             (fb.SURFACE_ANCHOR, "after",
              ["#ifdef KDM6_G33_FORTRAN_DUMP",
               *[_stage_write("surface", "0", f, "-1", dt, e)
                 for f, dt, e in fb.SURFACE_FIELDS],
               "#endif"])]
    for (role, species), anchor in cfg["emit"].items():
        edits.append((anchor, "before", _emit_lines(algo, role, species, "pre")))
    for (role, species), anchor in cfg["post"].items():
        edits.append((anchor, "after", _emit_lines(algo, role, species, "post")))

    # a line may take BOTH a before-block and an after-block (legacy: the update
    # line gets the pre-ladder before + the actual q_post after).
    plan = {}
    for anchor, place, block in edits:
        idx = [i for i, ln in enumerate(lines) if ln == anchor]
        if len(idx) != 1:
            raise SystemExit(
                f"anchor matched {len(idx)} whole lines, expected 1 — the source "
                f"changed:\n  {anchor}")
        plan.setdefault(idx[0], {"before": [], "after": []})[place] += block

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
