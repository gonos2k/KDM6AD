# Fixed-column extinction-cap follow-up — 2026-09-20

The selected column remains 35711, with the original five PR224 endpoints.
This follow-up corrects the public nine-channel JVP/VJP maximum to
`5.421010862427522e-20` (binary64) and establishes the installed solver's
source contract. It **does not measure cap-active layers**: the isolated
executable could not be linked, and no new RTTOV run occurred.

## Quantity and derivative contract

The installed `rttov_eddington_setup.F90` forms clear extinction as
`delta(opdp_path) / ltick * coszen`; `ltick` is in km and optical depth is
dimensionless. The capped quantity is an extinction coefficient in **km^-1**.
For this aerosol-disabled case, the clear coefficient is floored, then added
to each hydrometeor-combination coefficient. Combination 0 is clear sky.
The code sets quality bit 15 if **any combination/layer** exceeds 20, then
clips that coefficient. This is before delta scaling. The later dimensionless
optical-depth cap of 30 in `rttov_iniedd.F90` is a separate operation.

The supplied 39 user layers and 40 pressure interfaces are retained at this
boundary; gas coefficient-grid calculations are mapped back to user levels.
The positive model top does not activate the top pressure floor. Source-level
mapping does not replace a measured dump of the consumed internal arrays.

TL and AD use the same strict `>20` primal predicate, zeroing the relevant
extinction derivative above the cap. Equality is not in that branch. This
statement is about that intermediate derivative, not the entire BT derivative:
other scattering quantities and paths remain in the computation.

The channel flag reduces information over combinations and layers. Equal flags
at five endpoints do not establish equal masks. A flag also does not identify
gas, liquid, ice, or an input-unit problem. The project QC remains unchanged;
zero accepted channels still means no accepted liquid-process cost validation.

## Measurement limitation and preserved inputs

Retained outputs include BT, quality, transmission and profile K, but not
pre-cap extinction or its combination/layer mask. Profile K cannot recover the
missing primal mask. No layer/component attribution is inferred from it.

An isolated unmodified source object was built with gfortran 15 assembly and
LLVM 22's assembler. The default build path encountered the Xcode license gate;
no license was accepted. An installed LLVM 15 Darwin linker was also tried,
but linking failed on SDK/system symbols. The existing SDK 12.3 is incomplete,
and the SDK 26.5 route was incompatible with that link configuration. This is
an environment limitation, not a demonstrated RTTOV or KDM numerical defect.
No installed source, object, library, executable, or original case input was
modified. No diagnostic instrumentation or live diagnostic run was completed.

The next executable measurement remains: copy the same inputs; dump pre/post
coefficient, clear and hydro contributions, combination/channel/layer indices,
thickness and pressure; verify unchanged BT/K/quality; then compare all five
masks and their overlap with the accretion tangent. A compatible isolated
link environment is required. No new candidate, solver, QC, or tolerance is
needed to answer that question.

Source hashes and failed-link excerpts are in
[extinction_contract_2026-09-20.json](extinction_contract_2026-09-20.json).
Physical number units, nonzero transport and timestep convergence remain open.

## Retained input contract

The native cloud mapping emits `1000*rho_d*qc` in liquid slot 6 and
`1000*rho_d*(qi+qs)` in ice slot 7, in g m^-3 (`mmr_hydro=F`).
Effective diameters are in micrometres: twice the respective effective radius
followed by the declared diameter clamps; ice blends ice/snow radii by content.
The installed Fortran test driver reads the named hydro, diameter and unit
files. This source/file audit does not replace an instrumented consumed-array
dump. Host/kernel particle-number semantics remain unresolved.

Across the retained endpoints, maximum liquid content is 0.1932976371 g m^-3
and maximum ice content is 0.0637484467 g m^-3. Liquid diameter spans
5.02–11.30198718 micrometres and ice diameter 10–120 micrometres.
Both liquid content and liquid diameter change under accretion; the other
retained profile files are fixed. These ranges do not identify the component
responsible for the cap and are not used to infer input validity solely from
plausibility.
