# Freeze-lift request: two diagnostic arms

The owner's review of `main@77eb700a` puts two experiments first, and neither
can start without touching frozen code. This states exactly what would change,
what would not, and what would have to hold before the change is kept. It is a
request, not a plan of record: nothing here has been implemented.

## Why the overlay cannot do it

`make_fortran_overlay.py` is instrumentation only, by contract:

> Protocol §5.1: the canonical Fortran is NEVER edited (frozen). [...] Compiled
> WITHOUT the macro it is byte-identical behaviour.

An arm that changes a transport coefficient is not instrumentation. The
existing `conservative` arm is a separate canonical file
(`module_mp_kdm6_cons.F`), which is the shape these would take.

## Arm N — dry-mass-conservative number transport

**Site.** `host/KIM-meso_v1.0/phys/module_mp_kdm6.F`, two lines:

    1222  dnr(i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld, nrs(i,k+1,1))
    1306  dni(i,k+1) = min(falkn(i,k+1,2)*delz(i,k+1)/delz(i,k)*dtcld, nrs(i,k+1,2))

**Change.** One factor on each, using a variable already in scope on the line
above it:

    delz(i,k+1)/delz(i,k)   ->   dend(i,k+1)*delz(i,k+1)/(dend(i,k)*delz(i,k))

No new state, no new argument, no reordering. `dend(i,k) = den(i,k)` (F:870),
so this preserves the OPERATOR measure the kernel already integrates; whether
the physical measure should use true dry density is the separate basis
question `FINDING_number_mass_basis_v1` already records, and this request does
not touch it.

**What it is predicted to do.** The residual this repo measures is an identity
(`g33_number_transport.column`, `predicted_over_measured` = 1.000000000000 on
twelve rows):

    R_N = sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b

Substituting the corrected coefficient sends every interface term to zero, so
the acceptance criterion is not "smaller" but

    |R_N^corrected| <= B_roundoff

with `B_roundoff` the screening bound the water analyzer already computes.

## Arm L — per-column `ncmin`

**Site.** The `ncmin` assignment in the same file: a scalar set inside the
column loop, so the LAST column's `xland` decides the threshold for the whole
tile.

**Change.** Diagnostic-only per-column threshold:

    ncmin(i) = ncmin_land  if xland(i) == 1
             = ncmin_sea   if xland(i) == 2

**What it is predicted to do.** Make the operator decomposition-invariant:

    M_(3) == M_(1,2) == M_(2,1) == M_(1,1,1)

and equal to the per-column direct-sum oracle the harness already builds. The
current spread is about +/-21% signed one-call in-column rain between
partitions.

## What is NOT requested

- No change to the legacy default. Both arms are ADDITIONAL canonical variants
  selected by `--algo`, exactly as `conservative` is.
- No change to `module_mp_kdm6_cons.F`, to the C++ port, to the oracle, or to
  any pinned bundle.
- No re-pointing of `CLAIMS.yaml`. New arms produce new bundles; existing pins
  answer for the tag they were published under.
- No claim of a forecast impact. Both arms are diagnostic instruments for the
  factorial the review asks for next.

## Gates before the change is kept

1. **Legacy is untouched, proven by bytes.** `--algo legacy` reproduces the
   pinned bundles' member `output_sha256` exactly. A variant that perturbs the
   baseline is not a counterfactual.
2. **Arm N closes.** `|R_N| <= B_roundoff` on all six density arms and both
   species, where legacy gives 1.000000000000 agreement with the closed form.
3. **Arm N leaves MASS alone.** The `qr` control still closes as it does now;
   a number fix that moves water is a different change.
4. **Arm L collapses the decomposition spread.** All four partitions agree,
   and agree with the per-column oracle.
5. **Full suite and the three gates** (chain, header, overlay) on both a
   private and a public checkout.
6. **The SHA pin moves with the file.** `make_fortran_overlay.py` verifies the
   canonical SHA; a new variant needs its own pin, and the overlay's
   per-algorithm anchors must be shown to hold on it.

## What this unblocks

Items 1 and 2 of the review's immediate list, and therefore item 3 (the N x C x
L factorial), which is where the interaction between the three defects is
first measurable. Item 4 (LC05 offline replay) does not depend on this and can
proceed in parallel.

## Baseline

    main  77eb700a25430590257ef7dc978db7de3683956d
