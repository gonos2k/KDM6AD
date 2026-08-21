# Arm N closes the number budget the closed form predicted it would

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-NUMBER-010` | **active** | confirmed | OPERATOR-LEVEL, and under the same den*dz ledger as G33-NUMBER-008 -- `dend(i,k) = den(i,k)` is MOIST density, so Arm N restores the OPERATOR's own measure and says nothing about the physical dry-air column number (G33-BASIS-002/003). One fixture, nsplit 12, f32, mstep>1 not re-run. Diagnostic arm: selected by --algo, changes no default, and no published bundle is re-pointed. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner freeze-lift granted 2026-08-21. `module_mp_kdm6_nmass.F` is legacy with
the interface number transfer weighted by air mass rather than thickness:

    delz(i,k+1)/delz(i,k)  ->  dend(i,k+1)*delz(i,k+1)/(dend(i,k)*delz(i,k))

Two lines, `dnr` and `dni` -- the only two of seven transfer sites in that loop
without a density factor. The five mass lines all divide by `dend(i,k)`, which
is what makes the omission a gap rather than a choice. Diff against legacy: six
lines.

## The falsification matrix, first call, before the trajectories separate

`g33_fixture_v1`, `nsplit=12`, `rezero`, width 3. Same initial state on both
arms, so this is the operator and not an accumulated difference.

| rho | species | legacy `R_N` | Arm N `R_N` | Arm N / start |
|---|---|---|---|---|
| `as-is` | `nr` | 9.3258e+03 | 2.2958e-07 | 5.85e-17 |
| `as-is` | `ni` | 2.0890e+07 | 1.2666e-07 | 6.94e-17 |
| `uniform` | `nr` | 2.8546e-07 | 2.8546e-07 | 7.23e-17 |
| `uniform` | `ni` | 8.1956e-08 | 8.1956e-08 | 4.47e-17 |
| `inverted` | `nr` | -9.2340e+03 | -4.4225e-08 | 1.12e-17 |
| `inverted` | `ni` | -2.0763e+07 | -1.4901e-08 | 8.09e-18 |
| `x2` | `nr` | 1.8750e+04 | -2.3003e-07 | 5.89e-17 |
| `x2` | `ni` | 4.1920e+07 | 5.9605e-08 | 3.28e-17 |
| `offsetplus` | `nr` | 9.1163e+03 | -5.4016e-07 | 1.25e-16 |
| `offsetplus` | `ni` | 2.0554e+07 | 6.7055e-08 | 3.34e-17 |
| `offsetminus` | `nr` | 9.5612e+03 | 2.2259e-07 | 6.30e-17 |
| `offsetminus` | `ni` | 2.1267e+07 | 0.0000e+00 | 0.00e+00 |

Worst relative residual on Arm N: **1.25e-16**, against an f32 machine
epsilon of ~1.2e-07 -- nine orders below the arithmetic's own resolution.

### What each row is for

`uniform` is the control: with a flat profile the two weights are the same
expression, so the arm must change NOTHING. It changes nothing to the last
bit -- both arms report the identical value. That is what shows the arm
intervenes only where the stratification is, rather than trimming a residual
wherever it finds one.

`inverted` reverses the legacy sign and `x2` roughly doubles the legacy
magnitude, exactly as the closed form
`sum [den(lower) - den(upper)] * delz(upper) * b` requires. Arm N collapses
all of them.

## The mass control is untouched

    qr   1.412673e-16  ==  1.412673e-16
    qi   5.551115e-17  ==  5.551115e-17

Bit for bit. A number fix that moved water would be a different change.

## What this does and does not establish

It DOES establish the mechanism end to end: source equation -> theoretical
residual -> falsifying intervention -> corrected collapse. The review's §3.6
chain is closed on this fixture.

It does NOT establish a forecast impact, a precipitation change or a
trajectory difference of any stated size. The arms diverge after the first
call precisely because the number field differs, and what that divergence
does downstream is the N x C x L factorial, not this.

## Limits

- One fixture, one `nsplit`, f32. `mstep > 1` not re-run.
- Diagnostic only: selected by `--algo`, changes no default, and no published
  bundle is re-pointed.
- `dend(i,k) = den(i,k)` is the MOIST density, so the arm restores the
  operator's own measure. Whether the physical column number should use true
  dry density is `FINDING_number_mass_basis_v1`, untouched here.
