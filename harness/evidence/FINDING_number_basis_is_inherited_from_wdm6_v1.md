# The number basis the kernel assumes is m^-3, the Registry declares kg^-1, and both come verbatim from WDM6

Owner review item 15.6 asked for a conversion-free ice fixture. Before building
one, this reads the basis the kernel actually assumes, and where that assumption
came from.

## The slope machinery requires number per m^3

`module_mp_kdm6.F:3507`

```fortran
   pidnr =  cmr*g1pdrmr/g1pmr
```

`cmr = pi*denr/6.` (`:3429`) with `denr` the density of water, and `dmr = 3.`
(`:134`), so `cmr` is the mass-diameter coefficient of `m = cmr * D**dmr`:
`[cmr] = kg m^-3`. The two gamma ratios are dimensionless, so
`[pidnr] = kg m^-3`.

`module_mp_kdm6.F:1552`

```fortran
   lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))/(den(i,k)*qrs(i,k,1))))*(1./dmr))
```

`[den*qrs] = kg m^-3`. For `lamdr` to come out in m^-1:

    [pidnr * nrs] / [den * qrs]  =  m^-dmr
    (kg m^-dmr * [nrs]) / (kg m^-3)  =  m^-dmr   =>   [nrs] = m^-3

The reconstruction at `:1557` is the same relation solved the other way and
agrees: `nrs = den*qrs*lamdr**dmr/pidnr` also yields m^-3.

## The Registry declares per kilogram, and nothing converts

`Registry/Registry.EM_COMMON:546`

    "QNRAIN"  "Rain Number concentration"  "# kg(-1)"

and the kernel takes it and returns it untouched:

    module_mp_kdm6.F:388    nrs(i,k,1) = nr(i,k,j)
    module_mp_kdm6.F:425    nr(i,k,j) = nrs(i,k,1)

There is no `*den` on entry and no `/den` on exit, for `nr` or for `ni`.

## Sedimentation carries the same split

    :1193   falk(i,k,1)  = dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)
    :1194   falkn(i,k,1) = nrs(i,k,1)*workn(i,k,1)/mstep(i)
    :1217   dqr(i,k)  = min(falk(i,k,1)*dtcld/dend(i,k), qrs(i,k,1))
    :1221   dnr(i,k)  = min(falkn(i,k,1)*dtcld, nrs(i,k,1))

Mass is lifted to a per-volume flux by `dend` and dropped back by `dend`; number
gets neither. Both incoming terms carry `delz(k+1)/delz(k)`. These are the
candidate measures for matched interface transfers: `sum rho*q*dz` for mass
and `sum N*dz` for number. Legacy's separate departure/arrival caps can break
that matching, so conservation is not unconditional. `sum N*dz` is
the physical column number **only if N is per m^3**, which is what the slope
machinery assumes and not what the Registry declares.

## All of it is WDM6's, verbatim

Every element above appears unchanged in `phys/module_mp_wdm6.F` in this same
tree:

| element | KDM6AD | WDM6 |
|---|---|---|
| boundary in, no conversion | `:388` | `:240` |
| boundary out, no conversion | `:425` | `:275` |
| slope relation | `:1552` | `:2010` |
| reconstruction from mass | `:1557` | `:2014` |
| number flux without `dend` | `:1194` | `:814` |

The reconstruction row is spelled differently -- WDM6 writes `lamdr_tmp**3`,
KDM6AD writes `lamdr_tmp**dmr` -- but `dmr = 3.` is a parameter, so the two are
numerically the same.

So the basis question is not a KDM6AD-introduced defect. It is the WRF-distributed
parent scheme's policy, carried across.

## What this does and does not settle

**Settled from source**: the kernel's slope machinery assumes m^-3; the Registry
declares kg^-1; no conversion sits between them; thickness-only number transfer
has `sum N*dz` as its matched-transfer measure; and these source assumptions
are inherited from WDM6 unchanged.

**Not settled**: which side is wrong. If the code is right, the Registry's units
string is wrong and the dynamics -- which advects `qnr` as a per-kg scalar scaled
by `mu` -- is the inconsistent party. If the Registry is right, the microphysics
is. Both readings leave an inconsistency; they place it in different code.

**Not measured here**: any magnitude. Nothing was run for this finding. The
6-14% transfer residual in `FINDING_number_basis_gap_v1` and the 0.10% moist/dry
weight error in `FINDING_number_mass_basis_v1` are different quantities against
different measures, and neither is evidence for or against this one.

**Boundary contract still to close**: host dry-mass number `n_d [# kg_d^-1]`
would map to kernel volume number `N [# m^-3]` via `N=rho_d*n_d`, with the inverse
on return. This states the conditional conversion, not a decision to insert it.
Choosing it requires checking the PSD, mean particle mass and dynamics together;
adding density to sedimentation alone cannot resolve the mismatch. Inheritance
establishes origin, not correctness or authorization to change the f32 path.

## Reproducing

    grep -n "pidnr *=" phys/module_mp_kdm6.F                  # 3507, live; 3506 commented
    sed -n '1552p;1557p;388p;425p;1193,1194p;1217p;1221p' phys/module_mp_kdm6.F
    sed -n '240p;275p;814p;2010p;2014p' phys/module_mp_wdm6.F
    sed -n '545,546p' Registry/Registry.EM_COMMON
