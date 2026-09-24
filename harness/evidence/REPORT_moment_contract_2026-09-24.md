# G3: declared moments, regenerated rates and actual paired transport

## What this closes

The earlier boundary replay converted an already-generated rate. This experiment
instead calls the existing cloud/rain DSD and `accretion_torch` producers again
from declared physical moments, compares newly generated rates with a separately
written volume-form equation, and executes the existing analysis-only, opt-in conservative ice function
on unequal-density/unequal-thickness cells. Production equations, defaults, ABI,
QC, tolerances and native sources are unchanged. There are **zero native-host
or RTTOV runs** in this G3 experiment.

The result establishes conditional representation properties of these isolated
operators. It does **not** resolve the historical host number basis or prescribe
an operational density conversion. `CHECKLIST_generalization_2026-09-24.md`
tracks those separate obligations and the subsequent G4 work.

## Physical declaration and the two collection arms

For this experiment only, declare

    q_d [kg water/kg dry air], n_d [particles/kg dry air], rho_d [kg dry air/m3]
    C = rho_d*q_d [kg water/m3], N = rho_d*n_d [particles/m3].

The mixed kernel interface uses mass mixing ratio and **volume** number in its
DSD/collection expressions. One arm converts the explicitly declared dry-mass
numbers to N and supplies q_d, N and rho_d. The other evaluates the formal
volume-coordinate algebra using C,N and denominator 1. That denominator is an
algebraic unit conversion, **not another atmospheric density** or a host run.
Actual cloud and rain slopes are freshly regenerated in both arms. The direct
volume collection equation separately computes both regimes, gates and caps;
it reuses the fresh DSD outputs to isolate the collection-law comparison. It is
not a second independent DSD implementation or independent physical model.

For each regime, the expected commutation is

    rho_d * R_mass_mixing = R_mass_volume,
    R_number_kernel = R_number_volume,
    R_number_dry = R_number_volume/rho_d.

A rain threshold L in volume coordinates is compared as L/rho_d against q_r in
the mixed arm. The synthetic on/off threshold is prescribed relative to rain
concentration, separately from the freshly computed DSD transition diagnostic.
Both mass and number reservoir caps transform with their own moments. Neither
moment is required to move at the same fractional rate as the other.

Eight synthetic cases cover two rain-size regimes, active/inactive rain gates,
and free/limited raw rates. Additional tests use densities 0.25, 0.88 and 1.4.
The capped cases retain every production coefficient and use deliberately long
**synthetic** time intervals (about 1710/7853 s) to activate both reservoir caps.
These are branch witnesses, not proposed model time steps or weather cases.
Raw-cap eligibility and the outer inactive gate are distinct: an inactive case
returns zero even if its unevaluated physical-rate formula would hit a cap.

The maximum recorded representation/direct-equation relative difference is
1.48e-16. The value check allows 64 binary64 epsilons for rearranged scalar
arithmetic; no existing production or observation tolerance is changed.

## Limits near activity floors are explicit

The production cloud gate compares q_c to its fixed mixing-ratio EPS. A formal
volume arm cannot reuse that number as a volume floor near the threshold.
For q_d=1.5 EPS and rho_d=0.25, the mass-coordinate cloud is active while the
unconverted numeric volume floor makes C=0.375 EPS inactive. The probe records
both actual slope outputs. Thus the den=1 metamorphic comparison is restricted
to the jointly active states; it is not claimed to commute across every source
activity floor. Converting the floor itself is a necessary policy, still not an
operational change in this PR.

`moment_validity.py` separates inactive pairs, active inadmissible pairs and
admissible mean particle mass under **caller-declared volume floors and bounds**.
Both moments below their floors leave C/N undefined rather than asserting a
physically meaningful radius. Positive active mass with zero number is rejected.
The tests use synthetic bounds; they do not establish KDM species-size limits.
The output consumer reads only admissible cells; an unreadable inactive sentinel
checks that a validity mask prevents using undefined producer slots. Its zero
placeholder is diagnostic and is not inserted into native physics.

## Retained three layers: recalculation, not an alternative model trajectory

The six rows reuse PR230's three actual producer inputs at native layers
11/12/14 and regenerate slopes and rates under two **hypotheses**:

- Raw-number arm: captured density and raw number, matching the legacy formula's
  numerical use; this is not proof the stored number really has volume units.
- Conditional dry arm: rho_d, rho_d*n_d and the corresponding dry-mass moments.
  The captured threshold remains mass-based in the raw arm. Its physical-volume
  value `rho_source*lenconcr` is converted to the dry arm's mixing coordinate.

| Layer | Raw-arm volume number rate | Conditional dry-arm volume number rate |
| ---: | ---: | ---: |
| 11 | 364751.48659655335 | 316461.8871676609 |
| 12 | 285346.3480702281 | 237370.86479515885 |
| 14 | 255679.44496796138 | 191835.7581325776 |

Units in these columns are conditional particles/m3/s under each stated
hypothesis. These rates are freshly calculated, not stored rates multiplied by
rho. The two hypotheses also distinguish captured moist density from derived
dry density, so the difference is not solely a pure number conversion.
This is not a corrected initialization, complete KDM step or alternative native
trajectory. Original source inputs and evidence are preserved.

The source conflict remains: Registry declares mass-based number; host entry
and return copy it directly; slope equations use N/(rho*q), consistent with
volume number. A successful conditional adapter does not determine which
historical state interpretation and all upstream process thresholds should be
adopted. G3.3 stays open.

## Opt-in conservative transfer and derivative of its declared measure

The transport probe uses the existing **analysis-only, opt-in**
`conservative_ice_substep_advection_torch` function. It supplies
separate mass/number velocities normalized once by dz, and lets the kernel
compute limited departures. An independent recurrence in cell-inventory
coordinates provides the expectation:

    y_mass = rho_d*q_d*dz, y_number = N*dz
    Q_out = min(y*v*dt_sub/dz, y)
    y_next = y - Q_out + Q_in; surface_next = surface + Q_bottom.

The same Q is used on both sides of each interface. Three synthetic experiments
include one and three substeps, unequal rho/dz, uncapped and emptied donors, and
nonzero bottom export. They agree across dry/volume encodings and with the
independent recurrence within 32 epsilon64 relative, zero absolute tolerance.
The opt-in function generates these transfers, unlike the earlier prescribed
two-cell transfer identity. This is a counterfactual operator test; it does not
validate the operational legacy transport or close its P1. Velocities are held
fixed through each run; no full reslope/host time accuracy or native
surface-export measurement is claimed.

The derivative tests perturb state, density, thickness and both velocities.
They compare true `torch.func.jvp`, VJP and independent central differences for
all cell and surface outputs. The total derivative includes

    delta(rho*n_d*dz) = rho*dz*delta n_d + n_d*dz*delta rho + rho*n_d*delta dz.

The same physical direction is also encoded in volume coordinates using
`delta N=rho*delta n_d+n_d*delta rho`; the resulting output JVP agrees. A
number input copied without conversion gives a failing physical-inventory
counterexample. These are isolated kernel contracts, not new model controls.
Collection's density JVP also agrees with the direct-volume equation and FD;
maximum recorded JVP/FD relative difference is 3.41e-12.

## Native inactive outputs remain an explicit open item

Canonical private `ProgB_param` declares `rhox`, `cmg` and related outputs as
`INTENT(OUT)`. Its q_g/b_g activity branch assigns them conditionally, but the
subsequent `if(cmg>0)` occurs outside that branch. The source therefore does not
define all inactive outputs before a read. The separate q_g>0 melting path also
uses rhox with a different gate. This source audit is not a new compiler-specific
measurement of an undefined value. No sentinel experiment is counted as a
native execution here, and no arbitrary initialization or old SHA-pin change
was made.

The Python cloud/ProgB functions' explicit inactive fallbacks are tested, but
those results cannot certify the native producer. G3.2's native producer/consumer
validity policy and historical source certification remain open.

## Reproduction

Run from the public repository with its oracle dependencies:

    python harness/run_moment_contract.py --output /tmp/moment_contract.json
    python -m pytest oracle/tests/test_moment_representation_probe.py \
      oracle/tests/test_moment_transfer_probe.py oracle/tests/test_moment_validity.py

The JSON records input/output arrays, conditional historical rows, source hashes,
environment, rate/derivative comparisons and explicit non-approval flags. It is
an executable isolated experiment; it does not claim private-file authentication.
Existing unit, host, transport and observation evidence retains its original
scope. Operational P1 and inherited liquid observation approval 0/9 remain open.

Validation environment: Python 3.12.13 / PyTorch 2.8.0 CPU. **61 focused tests
passed**: 32 new moment/representation/transfer checks and 29 retained boundary/
size checks. Ruff passed. This test count is separate from native atmospheric
case counts (zero new native cases in G3).
