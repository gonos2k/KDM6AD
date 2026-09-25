# S2 number units: owner decision and counterfactual design

This note extends the bounded mp37 QNR trace in
[`REPORT_S2_native_number_basis_2026-09-25.md`](REPORT_S2_native_number_basis_2026-09-25.md).
It does not change the operational mapping. The host scalar trace resolves the
stored-state basis as dry-air mass-specific number; the density source and
corrected KDM6 variant remain open.

## Evidence that constrains the decision

The private host Registry marks `qnr`, `qni`, `qnc`, and `qnn` as
`# kg(-1)` in `host/KIM-meso_v1.0/Registry/Registry.EM_COMMON`; the active
mp37/mp137 packages include these as prognostic `scalar` fields. In the retained
5 km input, all four number fields are zero. The bounded native trace shows the
KDM6 host wrapper copies `nr` into `nrs` and back without density conversion;
the same direct copy applies to ice and cloud numbers. KDM6 itself does not
initialize these prognostics at the wrapper boundary. The Thompson
`make_RainNumber` helper is guarded to Thompson schemes and is not an mp37
initializer.

The host scalar equation rules out interpreting those stored prognostics as
volume concentrations in the current WRF dynamics. Registry places QNRAIN,
QNICE, and QNCLOUD in `scalar` and labels them `# kg(-1)`; `MU` and `MUB` are
explicitly the perturbation and base-state *dry-air mass in column*. The
`other_scalar_advance` loop is called for every `is` from `PARAM_FIRST_SCALAR`
through `num_3d_s`; QNR/QNI/QNC are members of that
Registry scalar range. It calls `rk_scalar_tend` and `rk_update_scalar` on the
`scalar_old`/`scalar` slots and advances each field as

```fortran
scalar_new = ((c1*(mu_old+mub)+c2)*scalar_old + dt*tendency) /
             (c1*(mu_new+mub)+c2)
```

with the advection tendency plus scalar tendency in the numerator. The QN
call passes `mu_1`, `mu_2`, and `mub` to this update. Thus WRF transports
the scalar in a dry-air-mass-weighted state. The current host
prognostic contract is number per dry-air mass; treating its stored value as
`# m^-3` would make horizontal/vertical dynamics transport the wrong extensive
quantity unless the WRF scalar equation and every boundary/restart producer
were redesigned too.

Source anchors (canonical private host paths): `Registry/Registry.EM_COMMON.var`
lines 77–78 declare `mu`/`mub` as dry-air column masses; lines 203–218 declare
QN values as `scalar` fields with `# kg-1` units. `dyn_em/solve_em.F` lines
2767–2868 are the QN `other_scalar_advance` path; lines 2851–2862 pass the
`scalar` slots and `mu_1`, `mu_2`, `mub` to `rk_update_scalar`. `dyn_em/module_em.F` lines 1715–1724 apply the
`mu+mub` weighting. Scalar initialization is at `dyn_em/module_initialize_real.F` lines
2004–2020 (QNICE) and 2024–2050 (QNCLOUD/QNRAIN); the Thompson fallback is
at lines 4789–4837.
Generic scalar boundary arrays are read in `share/wrf_bdyin.f90` lines
1262–1378; the inspected scalar path has no QN-specific density conversion.
The same host sources identify the relevant
density: `temp_rho=1/alt` in `module_initialize_real.F:4811` is used to turn
volume number into the stored scalar at :4817–4823, while
`module_big_step_utilities_em.F:4856` sets `grid%rho=(1/alt)*(1+qv)`.
`dyn_em/solve_em.F:3722–3728` passes `grid%rho` to
`phys/module_microphysics_driver.F`, whose KDM6 call passes `DEN=rho` at
:2756. Thus the host dry-mass density is `rho_d=1/alt`; KDM6's current `den`
receives moist `rho=(1+qv)*rho_d`.

The initialization paths support that reading. Optional metgrid QN fields are
interpolated directly into the `scalar` entries when their `flag_qn*` is set.
The separate missing-number fallback converts cloud/rain/ice mass to volume
concentration using `temp_rho=1/alt`, calls `make_*Number`, then divides by
`temp_rho` before storing the scalar. That fallback is explicitly limited to
Thompson/ThompsonAero, so it does not initialize mp37; it still documents the
host's intended stored basis. Restart, lateral-boundary, and regular input
paths use the generic `scalar` state without a QN-specific density conversion
found in this audit. The retained mp37 `wrfinput_d01` and `wrfbdy_d01` have zero QN number
fields/arrays, so this paired 40 s case has no initial or lateral-boundary QN
population; its first populated values are produced by KDM6 processes. This is
case-specific, not a claim about all WRF boundary configurations.

The KDM6 rain DSD closure uses

```fortran
lamdr = ((pidnr * nrs) / (den * qr))**(1/3)
nrs   = den * qr * lamdr**3 / pidnr
```

with `pidnr = cmr*g1pdrmr/g1pmr`, `cmr = pi*denr/6` in kg m^-3,
`den*qr` in kg m^-3, and `lamdr` in m^-1. Therefore `nrs` must be m^-3
for the expression to have its implemented dimensions. The same structure is
used for cloud and ice number. This dimensional reading agrees with Lim and
Hong's WDM6 paper, which describes prognostic number concentration and gives
number concentration in m^-3 and slope in m^-1 ([UCAR-hosted primary paper,
pp. 1588–89](https://www2.mmm.ucar.edu/wrf/site_linked_files/phys_refs/micro_phys/WDM5_6.pdf)).
It conflicts with the Registry metadata and the no-conversion wrapper. The
matched number sedimentation departure/arrival in the inherited WDM6/KDM6
kernel uses `dz*N`; the mass path uses `den*dz*q`. The native WRF scalar
equation now resolves the host-side contract: stored QN fields are per dry-air
mass. The kernel's dimensionally required volume number is therefore not the
same representation as the host prognostic, and the direct KDM6 boundary copy
leaves an unresolved conversion gap. This source conclusion does not establish which correction to adopt. It also
exposes a second density mismatch: the current kernel's DSD denominator uses
`den*q`, while the dry-mass moment is `rho_d*q_d`; with host `den=rho`, these
differ by the `1+qv` factor. A corrected variant must resolve that paired-moment
choice across `q`, `brs`, and number, not only multiply number by density.

The lineage finding records the equivalent WDM6 formulas and transfer path in
the private source archive:
[`FINDING_number_basis_is_inherited_from_wdm6_v1.md`](FINDING_number_basis_is_inherited_from_wdm6_v1.md).
The bounded run adds one active rain-number transfer witness but does not
resolve Registry versus kernel semantics, host dynamics transport, or
inter-call number budgets.

## Corrected-variant design

The current host state is dry-air mixing ratio `n_d` [# kg_d^-1]. A
physically coherent variant can either convert at the KDM6 boundary to a
volume number `N = rho_d*n_d` and convert back on return, or rewrite the KDM6
number equations and transfers directly in the dry-mass basis. Both require an
host-native dry density `rho_d=1/alt`; this is not the KDM6 `den` argument,
which is moist `rho=(1+qv)*rho_d`. The physical extensive number measure is
`sum(rho_d*n_d*dz)`.

No current-source evidence supports storing `N [# m^-3]` directly in WRF's
`scalar` state. That option remains possible only as a separately authorized
host redesign that changes the Registry, scalar transport equation, initial
and boundary inputs, restart semantics, and all other consumers together.
It is not a compatible interpretation of the existing host contract.

For a dry-mass representation, DSD closures must use consistent volume
moments. Host mass-specific water `q_d` [kg kg_d^-1] and graupel volume moment
`b_d` [m^3 kg_d^-1] pair as `rho_d*q_d` [kg m^-3] and `rho_d*b_d`
[m^3 m^-3], while number is `rho_d*n_d` [# m^-3]. The graupel
density/volume closure must use the same chosen density in its paired moments.
This does not imply inserting density in only the sedimentation update or
changing `brs` independently of `qg`. Equivalent representations must preserve
`rho_d*q_d`, `rho_d*b_d`, and `rho_d*n_d` together; a number-only conversion
is not a PSD-equivalent input transformation.

Existing concentration thresholds must stay in concentration
units. For example, the rain DSD gates `nrmin=0.01` and `nrmax=5e7` become
`n_d >= nrmin/rho_d` and `n_d <= nrmax/rho_d` when evaluated on stored
mixing ratio; cloud and ice scalar/per-cell minima require the same conversion.
The water threshold `qcrmin` remains a mass-mixing-ratio threshold. A single
conversion at input is insufficient if later code writes number back from a
clamped slope: each `nrs = den*qr*lambda**3/pidnr` rewrite and analogous cloud
and ice rewrites must return to the declared stored basis.

The representation-invariance test should preserve the physical moments
`rho_d*q_d`, `rho_d*b_d`, and `rho_d*n_d` together; number-only
conversion is not a PSD-equivalent input transformation.

If density participates in the conversion, the JVP includes
`dN = rho_d*dn_d + n_d*d(rho_d)`; the reverse pullback adds
`rho_d*barN` to the number cotangent and `n_d*barN` to the density cotangent.
The inverse return conversion also carries its density derivative. The public
fp64 ABI currently packs rho as forcing but does not mark forcing tensors as
requiring gradients; its JVP/VJP buffers contain the 12 state fields only.
Supporting the density direction therefore requires an explicit forcing
derivative contract. Existing f32 operational parity remains a separate
acceptance gate, and the proposed conversion must be an opt-in variant.

## Owner choices and next native counterfactual

Before implementation, the KDM6 and host owners need to decide:

- Whether the opt-in kernel should use dry `rho_d*q_d` moments in DSD closures,
  or preserve the current `den*q` mapping and treat that as a separate variant.
- Whether number thresholds (`nrmin`, `nrmax`, `ncmin`, and ice minima) are
  physical concentration cutoffs or legacy raw-value gates; if physical, map
  them to the dry-mass state, e.g. `nrmin/rho_d`.
- Whether the AD contract will make `rho_d` differentiable, and how its JVP/VJP
  inputs and outputs are packed.

After those choices, the smallest useful counterfactual is an isolated
synthetic two/three-layer state with nonuniform `rho_d`, nonuniform `qv`, and
nonzero number, mass, and graupel volume moments. Feed equivalent dry-mass
prognostics through the boundary-converted and direct dry-mass variants,
convert outputs to the same physical moments, and compare
DSD-derived sizes, threshold branches, applied departure/arrival amounts,
column number and mass ledgers, plus independent directional differences in
number and density. Only after this passes should an isolated native mp37/mp137
shadow build run paired against operational bitwise output; attribute its
between-variant changes separately. Do not insert a guessed density factor or
change operational defaults while the owner decisions remain open.

The limited algebraic representation check is implemented in
`harness/tests/test_replay_number_boundary.py`:
`test_three_layer_dry_and_volume_number_q_br_s_moments_match` checks three
nonuniform-density layers, paired number/water/graupel-volume moments, the
transformed concentration threshold, and column number; the companion JVP/VJP
test checks `d(rho_d*n_d)`, `d(rho_d*q_d)`, and `d(rho_d*b_d)` against a central
difference and cotangent duality. The targeted file passed 20 tests and Ruff.
This is only a unit-map check: it does not run KDM6 rates, sedimentation,
limiters, or the host dynamics and does not settle which DSD density variant or
threshold policy should be selected. S2 remains OPEN.

## Coverage limits

This note combines the retained native capture/replay, direct source audit of
the canonical private KIM-meso host tree, public Python/C++ source, and the
primary WDM6 paper. Private Registry/driver/Fortran paths are not present in a
public clone, and the public C ABI does not currently expose density gradients.
Graphify rebuilt its structural graph from 922 files after the synthetic test
was added (13,406 nodes, 23,016 edges); the HTML view was skipped because it
exceeds the 5,000-node limit. The semantic fragment adds seven concept nodes
and seven inferred relationships for the WRF scalar contract, host/kernel QN
gap, dry-density quantity, DSD expectation, conversion design, derivative
contract, and WDM6 lineage. The graph report was regenerated with 1,053
communities. `graphify explain "QN number basis gap"` confirms links to the WRF
scalar contract and KDM6 DSD expectation. No native or ABI AD execution is
included; the corrected DSD density mapping and forcing derivative contract
remain unselected.
