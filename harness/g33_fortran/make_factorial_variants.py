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

#: N_d -- the DRY layer-mass ratio, applied to the N form (owner freeze-lift,
#: 2026-08-22). Arm N closes the OPERATOR's ledger, which is moist because
#: `dend(i,k) = den(i,k)` (F:870). The physical column number is taken in dry
#: mass (G33-BASIS-006), and with `rho_d = rho/(1+q)` the weight becomes
#:
#:     rho_d(k+1) dz(k+1)     den(k+1) dz(k+1) (1+q(k))
#:     ------------------  =  --------------------------
#:     rho_d(k)   dz(k)       den(k)   dz(k)   (1+q(k+1))
#:
#: `q` is the vapour mixing ratio, `q(ims:ime,kms:kme)` in `kdm62D`'s own
#: argument list, so it is in scope on the line being edited. No new state, no
#: new argument, no reordering -- the same shape of edit as N itself.
#: The replacement CONTINUES the line rather than lengthening it. The N form is
#: already 106 characters against a canonical maximum of 119, and the two
#: moisture factors take it to 132 -- which the length guard refused, exactly
#: as it is meant to. Splitting at the divide keeps every generated line inside
#: what the reference sources already carry.
ND_EDIT = (r"dend\(i,k\+1\)\*delz\(i,k\+1\)/\(dend\(i,k\)\*delz\(i,k\)\)",
           "dend(i,k+1)*delz(i,k+1)*(1.+q(i,k))    &\n"
           "                          /(dend(i,k)*delz(i,k)*(1.+q(i,k+1)))")

#: L -- `ncmin` per column. Identical in both bases.
L_DECL = ("   real                                :: ncmin",
          "   real, dimension(its:ite)            :: ncmin")


def apply_n(text: str, base: str) -> str:
    for pat, rep in N_EDITS[base]:
        text, n = re.subn(pat, rep, text)
        if n != 2:                      # nr and ni
            raise SystemExit(f"N edit on {base}: matched {n} sites, expected 2")
    return text


def apply_nd(text: str) -> str:
    """The dry ratio, on top of the N form. N must already have been applied."""
    pat, rep = ND_EDIT
    text, n = re.subn(pat, rep, text)
    if n != 2:                          # nr and ni
        raise SystemExit(f"N_d edit: matched {n} sites, expected 2")
    return text


#: N_d-WINDOW (owner approval, 2026-08-23). Arm N_d is TOLD the dry layer mass
#: instead of forming it from the call's own `q`: one extra `mdry0` argument on
#: `kdm62D`, optional so the 3D wrapper's call still compiles, and the two
#: transfer lines weight by its ratio directly. The driver fills it from the
#: window-initial state. A harness instrument only -- see
#: FINDING_fixed_dry_mass_arm_v1 for why production needs no such argument.
NDW_SIG_OLD = ("                   ,graupel,graupelncv                            &\n"
               "                    )")
NDW_SIG_NEW = ("                   ,graupel,graupelncv                            &\n"
               "                   ,mdry0                                         &\n"
               "                    )")
NDW_DECL_OLD = "   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: den\n"
NDW_DECL_NEW = (NDW_DECL_OLD +
                "   real, dimension(ims:ime,kms:kme), intent(in), optional :: mdry0\n")
NDW_EDIT = (r"dend\(i,k\+1\)\*delz\(i,k\+1\)/\(dend\(i,k\)\*delz\(i,k\)\)",
            r"mdry0(i,k+1)/mdry0(i,k)")


def apply_nd_window(text: str) -> str:
    """The window-initial dry mass, on top of the N form."""
    if text.count(NDW_SIG_OLD) != 1:
        raise SystemExit("N_d-window: kdm62D signature close matched "
                         f"{text.count(NDW_SIG_OLD)} times, expected 1")
    text = text.replace(NDW_SIG_OLD, NDW_SIG_NEW)
    if text.count(NDW_DECL_OLD) != 1:
        raise SystemExit("N_d-window: kdm62D `den` declaration matched "
                         f"{text.count(NDW_DECL_OLD)} times, expected 1")
    text = text.replace(NDW_DECL_OLD, NDW_DECL_NEW)
    pat, rep = NDW_EDIT
    text, n = re.subn(pat, rep, text)
    if n != 2:
        raise SystemExit(f"N_d-window edit: matched {n} sites, expected 2")
    # GUARDED. The argument is optional so the 3D wrapper compiles, but the
    # wrapper's own call to kdm62D omits it, and the four-leg decision driver
    # (g33_fortran_driver.f90) goes through that wrapper. A build of this arm
    # on that path would dereference an absent optional at the transfer line
    # -- undefined, and possibly silent. Refuse at entry instead.
    guard_anchor = "! 20250205 ncmin setting\n"
    if text.count(guard_anchor) != 1:
        raise SystemExit("N_d-window: entry anchor for the presence guard "
                         f"matched {text.count(guard_anchor)} times")
    text = text.replace(guard_anchor,
        "   if (.not. present(mdry0)) error stop &\n"
        "     'nmass_dry_window: kdm62D needs mdry0; the 3D wrapper does not pass it'\n"
        + guard_anchor)
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


def variant(base: str, n: bool, ell: bool, dry: bool = False,
            window: bool = False) -> str:
    text = BASES[base].read_text()
    if (dry or window) and not n:
        raise SystemExit("N_d is the dry form OF the N edit; it needs N")
    if dry and window:
        raise SystemExit("N_d and N_d-window are alternatives, not a stack")
    if n:
        text = apply_n(text, base)
    if dry:
        text = apply_nd(text)
    if window:
        text = apply_nd_window(text)
    if ell:
        text = apply_l(text)
    long = [(i + 1, len(l)) for i, l in enumerate(text.splitlines())
            if len(l) > MAX_LINE]
    if long:
        raise SystemExit(
            f"{base} N={n} L={ell} Nd={dry} Ndw={window}: {len(long)} line(s) longer than "
            f"the "
            f"canonical maximum {MAX_LINE}, first at {long[0]} -- a lengthened "
            f"continuation is the edit whose truncation compiles silently")
    return text


def name(base: str, n: bool, ell: bool, dry: bool = False,
         window: bool = False) -> str:
    """`legacy`, `nmass`, `lncmin`, `nmass_lncmin`, `nmass_dry`,
    `nmass_dry_window`, and `cons_*`."""
    # The factorial's own tags concatenate (`nmasslncmin`), and `nmassdry` is
    # not readable as two words. `_dry` is a MODIFIER of the N edit rather than
    # a fourth factor, and the freeze-lift names it `nmass_dry`, so it joins
    # with an underscore and says so here rather than in a reader's head.
    tag = "".join(t for t, on in (("nmass", n), ("_dry", dry),
                                  ("_dry_window", window), ("lncmin", ell))
                  if on)
    stem = {"legacy": "", "cons": "cons"}[base]
    parts = [p for p in (stem, tag) if p]
    return "_".join(parts) if parts else "legacy"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the files; otherwise just report")
    args = ap.parse_args(argv)
    # The 2^3 factorial, plus the ONE dry arm the 2026-08-22 freeze-lift
    # granted. N_d is not a fourth factor: it is a modifier of the N edit and
    # is generated for the legacy base only, which is the scope that was asked
    # for and the scope that was given.
    combos = [(base, n, ell, False, False) for base in BASES
              for n in (False, True) for ell in (False, True)]
    combos.append(("legacy", True, False, True, False))
    combos.append(("legacy", True, False, False, True))
    for base, n, ell, dry, window in combos:
                nm = name(base, n, ell, dry, window)
                text = variant(base, n, ell, dry, window)
                digest = hashlib.sha256(text.encode()).hexdigest()
                if not n and not ell and not dry and not window:
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
