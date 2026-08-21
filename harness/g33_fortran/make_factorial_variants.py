#!/usr/bin/env python3
"""Generate the N x C x L factorial's kernel variants from the two canonical ones.

The review's next experiment needs eight arms: number metric (N), interface cap
(C) and per-column `ncmin` (L), each on or off. C is a whole different kernel
(`module_mp_kdm6_cons.F`); N and L are localized edits that apply to EITHER
base, so the eight are two bases times four edit combinations.

Written as a generator rather than eight hand-edited files. Each edit is stated
once, applied mechanically, and ASSERTED to have matched -- eight files edited
by hand is eight chances to get one wrong, and the one that is wrong is the arm
whose result nobody can explain later.

Every edit is REVERSIBLE BY CONSTRUCTION: the `off` arm of each axis is the
base text untouched, so `--algo legacy` and `--algo conservative` keep
reproducing their pinned bundles byte for byte.
"""
import argparse
import hashlib
import pathlib
import re
import sys

HOST = pathlib.Path("host/KIM-meso_v1.0/phys")
BASES = {"legacy": HOST / "module_mp_kdm6.F",
         "cons": HOST / "module_mp_kdm6_cons.F"}

#: N -- the interface number transfer carries the layer air mass.
#:
#: The two bases put the thickness ratio in DIFFERENT places: legacy computes
#: `dnr(i,k+1)` with the ratio inside the `min`, conservative applies it at the
#: update. Same defect, same fix, two spellings -- which is exactly why this is
#: a table and not a sed one-liner.
N_EDITS = {
    "legacy": [
        (r"(dn[ri]\(i,k\+1\) = min\(falkn\(i,k\+1,[12]\)\*)delz\(i,k\+1\)/delz\(i,k\)",
         r"\1dend(i,k+1)*delz(i,k+1)/(dend(i,k)*delz(i,k))"),
    ],
    "cons": [
        (r"(\+dn[ri]\(i,k\+1\)\*)delz\(i,k\+1\)/delz\(i,k\)",
         r"\1dend(i,k+1)*delz(i,k+1)/(dend(i,k)*delz(i,k))"),
    ],
}

#: L -- `ncmin` per column. Identical in both bases.
L_DECL = ("   real                                :: ncmin",
          "   real, dimension(its:ite)            :: ncmin")


def apply_n(text: str, base: str) -> str:
    for pat, rep in N_EDITS[base]:
        text, n = re.subn(pat, rep, text)
        if n != 2:                      # nr and ni
            raise SystemExit(f"N edit on {base}: matched {n} sites, expected 2")
    return text


def apply_l(text: str) -> str:
    old, new = L_DECL
    if text.count(old) != 1:
        raise SystemExit(f"L edit: declaration matched {text.count(old)} times")
    text = text.replace(old, new)
    text, n = re.subn(r"^(\s+)ncmin = (ncmin_(?:sea|land))\s*$",
                      r"\1ncmin(i) = \2", text, flags=re.M)
    if n != 2:
        raise SystemExit(f"L edit: assignment matched {n} sites, expected 2")
    out = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("!") or ":: ncmin" in line or "ncmin(i) =" in line:
            out.append(line)
            continue
        out.append(re.sub(r"\bncmin\b(?!_)(?!\()", "ncmin(i)", line))
    return "".join(out)


#: The build passes `-ffree-line-length-none`, so gfortran will not truncate.
#: This does not rely on that: a substitution that lengthens a line is exactly
#: the edit whose failure mode is SILENT -- a truncated continuation still
#: compiles and computes something else. The bound is the longest line the
#: canonical sources already carry, so no generated arm is stranger than what
#: the reference build already accepts.
MAX_LINE = max(len(l) for f in BASES.values()
               for l in f.read_text().splitlines())


def variant(base: str, n: bool, ell: bool) -> str:
    text = BASES[base].read_text()
    if n:
        text = apply_n(text, base)
    if ell:
        text = apply_l(text)
    long = [(i + 1, len(l)) for i, l in enumerate(text.splitlines())
            if len(l) > MAX_LINE]
    if long:
        raise SystemExit(
            f"{base} N={n} L={ell}: {len(long)} line(s) longer than the "
            f"canonical maximum {MAX_LINE}, first at {long[0]} -- a lengthened "
            f"continuation is the edit whose truncation compiles silently")
    return text


def name(base: str, n: bool, ell: bool) -> str:
    """`legacy`, `nmass`, `lncmin`, `nmass_lncmin`, and the `cons` family."""
    tag = "".join(t for t, on in (("nmass", n), ("lncmin", ell)) if on)
    stem = {"legacy": "", "cons": "cons"}[base]
    parts = [p for p in (stem, tag) if p]
    return "_".join(parts) if parts else "legacy"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the files; otherwise just report")
    args = ap.parse_args(argv)
    for base in BASES:
        for n in (False, True):
            for ell in (False, True):
                nm = name(base, n, ell)
                text = variant(base, n, ell)
                digest = hashlib.sha256(text.encode()).hexdigest()
                if not n and not ell:
                    # the base itself, byte for byte -- the reversibility check
                    if text != BASES[base].read_text():
                        raise SystemExit(f"{nm}: base text changed with no edits")
                    print(f"  {nm:22s} {digest[:16]}  (base, unchanged)")
                    continue
                out = HOST / f"module_mp_kdm6_{nm}.F"
                if args.write:
                    out.write_text(text)
                print(f"  {nm:22s} {digest[:16]}  {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
