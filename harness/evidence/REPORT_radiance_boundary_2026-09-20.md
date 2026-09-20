# Fixed-column optical derivative boundary — 2026-09-20

PR227's evidence-file completeness issue remains closed. This follow-up separates
an executed-operator derivative diagnostic from the unresolved physical number
basis and independent radiative-accuracy questions. The fixed column is 35711;
no external atmosphere, solver change or QC relaxation is used.

## Mathematical contract

Use one cut immediately before `rttov_iniedd`: clipped, pre-delta-scaling
extinction, `ssa_all`, and `asm_all`. Reverse operands must be captured after
`rttov_iniedd_ad`, before reversal of the SSA/asymmetry ratios or extinction cap.
The source functions computed downstream of this cut must not be added again as
independent total-derivative contributions.

For the selected control, compare the baseline boundary adjoint with finite
endpoint differences:

    contribution_j(eps) = lambda_j(0) * [xi_j(+eps)-xi_j(-eps)]/(2*eps).

The sum is a finite-width approximation to the chain-rule contraction, not an
exact intermediate JVP. Its difference from the retained whole-channel JVP and
from the BT endpoint difference must remain visible. Matching endpoint branches
does not prove all intermediate branches or the entire alpha interval fixed.

Cloud-column radiances are weighted before conversion to BT. The K driver's BT
seed is propagated through `rttov_calc_bt_ad` before the optical reverse calls;
therefore a BT-seeded boundary adjoint already includes that conversion. Applying
an additional Planck derivative would double-count it.

## Fixed bypass inputs

A byte comparison of the retained `in/` trees finds the same 21 file names in
all five cases. Only `profiles/001/atm/hydro.txt` and `hydro_deff.txt` differ in
each of the four perturbed cases. Temperature, gases, pressure, surface and
geometry files are identical. PR226 measured identical cloud-column mappings
and weights. This supports a conditional cut for the selected liquid-control
experiment, not a complete optical boundary for arbitrary state perturbations.

## Separate physical number contract

The host initializer and Registry describe number per mass, while the inherited
kernel slope equation consumes a volumetric number under dimensional analysis.
The driver copies those fields without an intervening density conversion. The
existing source evidence in `FINDING_number_basis_is_inherited_from_wdm6_v1.md`
and `FINDING_number_mass_basis_v1.md` remains authoritative; this is not a newly
resolved unit contract.

The profile bridge converts content using density and converts radius to diameter
in micrometres. Those transformations do not determine the physical number basis
used upstream to calculate the radius. Inverting a measured radius can test the
executed slope algebra, but cannot by itself decide the intended physical units.
No production density factor is introduced by this diagnostic.

Source trace (private host paths refer to the canonical full host tree):
- `dyn_em/module_initialize_real.F:9078-9180`: mass-based number initialization.
- `Registry/Registry.EM_COMMON:546` and `phys/module_microphysics_driver.F:326-330`: declared number units.
- `phys/module_mp_kdm6.F:388-425`: direct boundary copy without density conversion.
- `phys/module_mp_kdm6.F:3730-3776`: slope algebra consuming density times mass mixing ratio.
- `oracle/kdm6/rttov_bridge.py:174-236`: content and effective-diameter conversion.

These source observations reuse the existing unit audit; no new physical unit
measurement is claimed.

## Measured finite-width contractions

Five completed executions used the isolated two-routine instrumentation, plus
two failed setup attempts (missing configuration/output directory). Failed
attempts are excluded from the usable evidence, not counted as successful cases.
All five required raw output files for each completed endpoint match their
retained originals byte-for-byte. The installed executable is unchanged.
The earlier uninstrumented relink comparison is reused from PR226.

The sums use baseline K adjoints and boundary differences, with no second
Planck conversion. K mode preserves a separate channel axis (`is_ad=False`);
simultaneously seeding channel BTs does not collapse these independent K rows
into a single nine-channel objective.

| channel | extinction | SSA | asymmetry | sum (K/control), epsilon=0.03 |
|---|---:|---:|---:|---:|

| WV063 | 0.00000000e+00 | -2.90335023e-10 | 8.46969238e-13 | -2.89488054e-10 |
| WV069 | 0.00000000e+00 | -9.16043621e-08 | 6.44214780e-10 | -9.09601473e-08 |
| WV073 | 0.00000000e+00 | -5.22534721e-07 | 4.57100287e-08 | -4.76824692e-07 |
| IR087 | 0.00000000e+00 | 5.87900255e-06 | 1.94036559e-06 | 7.81936814e-06 |
| IR096 | 0.00000000e+00 | 2.04929134e-06 | 9.18384199e-07 | 2.96767554e-06 |
| IR105 | 4.09025933e-04 | 1.61290932e-06 | 1.04113503e-06 | 4.11679977e-04 |
| IR112 | 2.75610345e-04 | 6.22597888e-07 | 4.73343320e-07 | 2.76706287e-04 |
| IR123 | 0.00000000e+00 | 6.84072834e-07 | 4.25867843e-07 | 1.10994068e-06 |
| IR133 | 0.00000000e+00 | 7.00860985e-07 | 2.56608746e-07 | 9.57469731e-07 |

Seven of nine channels have zero extinction contraction; SSA/asymmetry paths
retain nonzero responses. IR105 and IR112 also retain extinction contributions
through uncapped selected layers. These signed contributions can cancel; neither
counts nor signed ratios are general sensitivity fractions.

The maximum relative difference from the retained full channel JVP, normalized
by max(abs(contraction), abs(JVP)), is **0.0154858% at epsilon=0.03** and
**0.171884% at epsilon=0.1**. Smaller width reduces this measured discrepancy,
but two widths do not establish asymptotic convergence. The input control is
exponential and the intermediate differences have finite-width error. No new
threshold is fitted to these results.

The public JSON contains all 351 selected cloudy channel/layer baseline operand
and adjoint rows, exact replacement operands for four endpoints, retained JVPs,
BT endpoint strings, and required-file equality records. The replay independently
contracts these operands and reports the direct BT central differences as well.
Weak-channel BT text quantization remains as recorded in PR224; this boundary
contraction does not repair that independent FD resolution limit.

## Defined fields and scope

The aerosol-free clear combination does not consume its stored `asm_all` (or
`ext_all`) values at this boundary; those unused slots can differ between direct
and K passes and are excluded from the contraction. They are not interpreted as
physical coefficients or silently turned into measured zeros. The defined clear
extinction, Planck layer fields, layer thickness, cosine, clear optical input,
cloud weights and cloud-top indices were compared separately and remain fixed.
The executed max-random overlap branch builds column weights from prescribed
`hydro_frac` (`rttov_cloud_overlap`); this input is unchanged and the profile
builder detaches its condensate-presence gate from the control derivative.
The two defined cloud optical boundary passes agree exactly for every endpoint.
The retained genuine profile JVP also has exactly zero T, Q, ice-content and
ice-size tangents; only liquid content/size at the three stated layers are
nonzero. These reused arrays and their source hash are included in the JSON.

IR surface reflectance has no optical-depth dependence in this installed source
branch (`rttov_eddington_setup`, IR surface section); surface inputs are fixed.
Planck/source and geometric tangents are therefore zero for this selected
control. Their downstream dependence on the three optical variables is already
included in the captured adjoints and is not counted a second time.

This is a finite-width contraction diagnostic of the executed capped operator,
not a separately computed genuine boundary JVP, a proof of all internal branch
stability, or an independent solver-accuracy test. Source identities and observed
operand equality support the cut only under the stated fixed-input experiment.
No unclipped counterfactual was run. The liquid observation/cost gate remains
excluded under the existing QC (0/9 channels).

Python 3.12 public replay and seven new normal/corruption tests passed, alongside
the 13 existing required-file tests (20 focused tests total). No full oracle or
native rebuild is claimed for this evidence/replay change. Public replay checks
recorded hashes, not unavailable original files; actual local file comparisons
are separate execution evidence.

Independent Green/Red review found no required corrections to this conditional
boundary result. Per-channel K indexing and the unused clear-storage exclusions
were explicitly checked.
