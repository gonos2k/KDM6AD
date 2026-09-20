# Number representation at entry, applied-process and return boundaries

This follows PR229's conditional size comparison. The operational number basis
is still unresolved. No density factor is inserted into production physics,
the ABI, or the observation interface. The native 5 km model levels and the
existing QC-excluded liquid result are retained.

## Source boundary versus measured execution

The canonical local host passes number fields directly. In
`host/KIM-meso_v1.0/phys/module_mp_kdm6.F`, entry assigns `nci=nc` and `nrs=nr`
and return assigns their evolved values back. In `module_mp_kdm6ad.F`, the
corresponding operation casts host number to `c_float` and copies it back after
the C ABI call. Neither operation computes `rho_d*n` or its inverse.

That establishes the implemented copy contract. Combined with the previously
documented host mass-number declaration and kernel volume-number formulas, it
localizes a representation conflict. It does **not** establish that a particular
historical stored value is physically per kilogram or per cubic metre.

The new applied-process evidence below is an **offline Python oracle trace** of
the retained model column. It is not a new native-host entry/exit dump. Source
inspection, oracle execution, and mathematical representation witnesses must
not be counted as the same evidence.

## Representation identity and its derivative

For a declared dry-mass quantity x and positive dry density rho_d, the volume
representation is X=rho_d*x. This applies separately to mass, number, rates and
thresholds when each has that declared basis. It is not permission to rescale
every model field: pressure, diameter, temperature and already-volumetric
quantities have different contracts.

The tangent and inverse tangent are

    dX = rho_d*dx + x*d(rho_d),
    dx = (dX - x*d(rho_d))/rho_d.

The harness checks both a fixed-density setting and a nonzero density direction.
These are exact conversion identities with scalar numerical witnesses, not a
new derivative path added to the model. Density remains frozen in the retained
KDM–RTTOV experiment.

Activation and reservoir limits must transform too. For positive rho_d,

    n > n_min  iff  rho_d*n > rho_d*n_min,
    rho_d*min(dt*r, n-n_min)
      = min(dt*rho_d*r, rho_d*n-rho_d*n_min).

The small threshold witness uses n=.02, n_min=.01 and rho_d=.25. Reusing the
unconverted .01 threshold changes the branch; using .0025 preserves it. This
is a deliberately synthetic counterexample, not an additional meteorological
column or a proposed floor policy.

## Transfer scope

A second synthetic witness prescribes a nonzero paired transfer of 4 particles
per square metre between two cells. The donor and receiver use their own dry
densities and layer thicknesses. Both mass-number and volume-number ledgers
give the same post-transfer inventory. It checks representation bookkeeping;
it does not evaluate KDM's flux reconstruction, independent caps, bottom loss
or transport time integration. The matched-source **nonzero native transport
measurement remains open**.

Cloud collection can reduce particle number while transferring liquid mass
from cloud to rain. A nonzero local collection sink is not a vertical departure
or arrival and must not be substituted for that missing transport measurement.

## Documentation correction

`diag_cloud_slope_torch` now documents its actual behavior: the active slope is
unlimited, and the inactive cloud gate supplies 1/lamdacmax. Downstream radius
limits are separate. Only the docstring changed; no executable expression did.

## New measured boundary witness

One offline alpha=0 oracle calculation reuses column 35711 (j=152, i=143),
forecast time index 1, all 39 native layers and dt=20 s. A temporary wrapper
calls the original accretion function once, records operands/results, and is
restored. There are **zero new RTTOV calls and zero native-host runs**.
The capture used Python 3.10.11 / NumPy 2.2.6 / PyTorch 2.13.0, separately from
Python 3.12 replay checks. No external model data were added.

The retained post-limiter pracw/nracw arrays match the earlier trace exactly.
Final qc/nc match PR229; all nine saved profile fields match the PR224 JSON,
and the four hydrometeor profile files match PR228 ASCII exactly. These are
local capture checks, not operations repeated by the public arithmetic replay.
Source paths, source hashes, environment and capture-script hash are retained
in `number_boundary_2026-09-20.json`. Its three rows expose the selected actual
producer operands, capped producer outputs, limited rates, initial state,
state-update entry/exit and final state. The larger local trace remains at
`graphify-out/pr230-number-boundary/native_number_boundary_2026-09-20.json`.

All three rows select the large-drop rain-active producer branch. The public
replay reconstructs that branch and its qc/dt and nc/dt caps. Producer output
and later shared-limiter output remain separate records; there is no claim
that archived pre-limiter rates were available for independent comparison.

The full selected nc update is

    rate = dt*(-nraut-nccol-nracw-niacw*cold-naacw-naacw)
    amount = -ninuc-nfrzdtc+pimlt_ni
    nc_after = max(nc_before + (rate+amount), 0)

where cold=(supcol>=0). Rate terms and amount terms must not both be multiplied
by dt. Each naacw occurrence is retained to match the implemented budget.
Although these rows are warm, layer 14 retains a nonzero naacw term,
applied twice without the niacw cold gate. Its total amount is
-9.885944669683195e-5. The replay consumes it rather than dropping all
cold-bundle terms on the basis of temperature. The other cold/amount terms
are zero in these selected rows.

| Native bottom-up layer | RTTOV user layer | Accretion number amount | Self-collection number amount | Full nc amount |
|---:|---:|---:|---:|---:|
| 11 | 28 | -7295029.731931067 | -10762.161302831944 | -7305791.893233899 |
| 12 | 27 | -5706926.961404562 | -14786.378699753844 | -5721713.340104316 |
| 14 | 25 | -5113588.899359227 | -7204.306939531417 | -5120793.206397619 |

Layer 14 also includes the twice-applied naacw amount stated above.
The table uses **internal number amounts**, without assigning a physical unit
to the unresolved stored number. Replay evaluates the source-ordered full
expression and reproduces selected post-update nc exactly; nc also remains
unchanged from this boundary to the final state in these three rows. Subtracting
the two large stored reservoirs first can lose low bits, so that different
operation order is not required to equal the applied amount bit-for-bit.
The accompanying qc/qr/nr values are context, not complete budgets for those
fields. In particular this is not full water or particle-number conservation.

Conditionally treating nc and every number amount as per dry-air mass, the
replay converts the full ledger with the same frozen initial rho_d and inverts
it. The returned values agree within eight binary64 ULPs (a rounding allowance
for this scalar algebra, not a new physical tolerance). This checks arithmetic
covariance of a prescribed update. It does **not** demonstrate that the kernel
would generate the same rates if its inputs were rescaled and the physics
rerun. That physical representation-invariance question remains open.

## Validation and remaining contract

Python 3.12 focused tests cover the measured replay, omitted self-collection,
changed amounts and states, invalid density, changed producer outputs/gates,
false unit-approval claims and disabled assertions. Separate small scalar
witnesses cover variable-density JVP/inverse/VJP identities, a converted
threshold/reservoir cap and a paired nonzero synthetic transfer. These are not
additional atmospheric cases. The public replay reports
`scope=arithmetic_replay_only` and all physical/transport/observation approvals
remain false.

The next unresolved measurement is a matched native-host entry/apply/return
and nonzero transport ledger with an established number basis. No production
density conversion, alternative trajectory, CI matrix expansion, QC change or
new radiation-accuracy claim is part of this change.

Focused validation: **29 passed** on Python 3.12 (18 boundary tests and 11
existing number-size tests). Stripping docstrings and comparing Python ASTs
confirms that `cloud_dsd.py` has no executable change. Green review checked the
public rows against the local capture without another KDM/RTTOV run.
