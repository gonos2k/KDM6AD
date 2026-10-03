# Independent IR105 transport implementation comparison

Baseline: main `ce0806a6a2789545067d4c7c9e0b835fc6eb1e69` after PR #362.
This closes a bounded independent-implementation check, not S11 physical or
observation-error approval. No KDM equation, RTTOV installation, atmosphere,
optical table, QC mask or tolerance is changed.

## Frozen inputs and scope

Reuse the C5 input-only-selected sea column `(73,157)` at 20 seconds, its
39 native layers plus 24 documented reference-top layers and original surface.
IR105 (AMI channel 13) was selected as a standard thermal-window channel before
this comparison, not from observed residual or solver agreement. The RTTOV test
subset 8–16 renumbers it to internal channel 6.

The environment-gated isolated patch captures consumed DOM layer optical
depths, source radiances, phase moments, view cosine, surface reflectance and
clear/cloud weights. Inputs are pinned separately for BASE and NC±; each original and its OFF/ON
direct/K output trees match byte-for-byte; see [capture receipt](DISORT_capture_receipt_2026-10-03.json).
The installed source and executable remain unchanged. A first wrongly named
archive member did not capture anything and is excluded; corrected object
replacement produced the retained captures.

Independent C-DISORT 2.1.3 through **pydisort 1.8.13**, Python 3.13.7,
Torch 2.10.0 CPU and NumPy 2.5.3 runs in a separate environment. It is separately
implemented transport, but shares the captured gas/cloud optical properties and
uses the same discrete-ordinates family. It does not independently validate
spectroscopy, particle optics, meteorology or observation error.

## Mapping and verification

Top-down layers use `upward=0`. Property slots are tau, unscaled SSA, then
PMOM1…N (PMOM0=1 is implicit). RTTOV coefficients are divided by `2*l+1`;
order 32 comes from the captured forward fraction. Apply delta-M once.
`laymap=0` consumes zero scattering even when an unused raw SSA entry is stale.
Use actual ray-traced view cosine, not a newly calculated angle approximation.

Equivalent temperatures invert C-DISORT's band Planck function at the fixed
900–901 cm⁻¹ numerical carrier band so that each Planck source equals 0.001
of the captured channel radiance. These are numerical source coordinates,
not replacement meteorological temperatures or a new spectral integration.
Surface emission and Lambert reflection are matched separately. Incoming top
radiance equals captured cosmic plus profile-top Planck emission, matching the
actual boundary equations. Thermal intensity correction remains off.

The two-layer pure-absorption analytical check agrees within 4e-12 radiance
units for upward and downward boundary solutions. Actual cumulative absorption
is 0.556/0.789 for clear/cloudy subcolumns, below C-DISORT's cutoff 10. Its cutoff
does not activate here. The source packing retains only available orders;
no moment extension or DOM64 claim is made.

## Actual result

| C-DISORT streams | IR105 BT (K) | NC direction FD (K/control) |
| ---: | ---: | ---: |
| 8 | 291.877604753602 | -0.000833604474337 |
| 16 | 291.878632503468 | -0.000830606552427 |
| 32 | 291.878606113030 | -0.000830657995721 |

The NC endpoints use the unchanged `h=1e-4`, direction `0.01*NC` and captured
actual optical endpoints. RTTOV DOM32 BT is 291.878893444646 K and its K/JVP
is -0.000830651958263 K/control. The C-DISORT32 differences are approximately
**-0.000287332 K** and **0.000727%** of the RTTOV directional signal. These are
observed differences, not approved universal physical tolerances.

## Identified source approximation difference

C-DISORT `cdisort213/disort.h` sets the linear thermal source slope to zero
unless delta-scaled layer optical depth exceeds **1e-4**. RTTOV keeps the linear
slope in these thin layers. Thus the unmodified programs do not solve exactly
the same source approximation even with matched boundary optical inputs.

An independent formal clear-column integration at 32 streams gives
94.130408212229 versus captured RTTOV 94.130408212189. Applying C-DISORT's
thin-layer constant-source rule gives 94.129971162842, matching C-DISORT's
94.129971162842. This attributes the clear-column discrepancy to the source
rule rather than an input mismatch. The comparison retains both original
solver outputs; no production source rule is changed to improve agreement.

## Matched-source attribution experiment

An additional isolated **value-only** RTTOV build applies only the same thin-layer
source rule, via the separate evidence patch; `do_k=False` is explicit and no
K/AD result is claimed for this altered source approximation. Native atmospheric
and optical input files remain byte-identical. It is not adopted in the installed
RTTOV or used to replace the retained original result.

With that shared rule, clear/cloudy and weighted total radiances agree with
C-DISORT32 within 1.3e-12 for each of BASE/NC±. The matched BT central differences
are -0.000830657143069 (RTTOV) and -0.000830657995721 (C-DISORT), an absolute gap
8.53e-10 K/control; endpoint rounding is amplified by division by `2h`.
All nine RTTOV quality flags remain zero/good. No accepted-observation policy is
inferred from that fact. This closes the narrow source-rule attribution for the
actual cloudy case as well as the analytical clear-column check.

[Matched-source execution receipt](DISORT_thin_source_receipt_2026-10-03.json)
records the altered source, build, input and output hashes. The ordinary replay
continues to report the original RTTOV/C-DISORT difference, not this experimental
match as an operational result.

## Replay

In a separate environment with `pydisort==1.8.13` and its CPU Torch dependency:

```sh
python harness/compare_ir105_disort.py \
  --base harness/evidence/DISORT_ir105_base_2026-10-03.tsv \
  --plus harness/evidence/DISORT_ir105_plus_2026-10-03.tsv \
  --minus harness/evidence/DISORT_ir105_minus_2026-10-03.tsv \
  --output /tmp/ir105-disort.json
python harness/evidence/DISORT_pure_absorption_check_2026-10-03.py \
  --output /tmp/disort-boundary-check.json
python harness/evidence/DISORT_clear_formal_check_2026-10-03.py
```

The dependency is optional and is not added to the normal runtime or CI. Existing
public TSVs allow independent replay without private WRF/RTTOV access. The
original capture still requires the licensed local RTTOV installation.

S11 remains OPEN: physical BT/sensitivity tolerances, independent optical
accuracy and calibrated AMI observation-error policy are absent. The host DA
code can read sensor-specific `error_std`/error-factor files, but installed local
radiance-info data contains no AMI policy. AHI settings are not substituted.
Diagnostic sigma=1 K and smaller single-pixel cost do not close this gate.

Primary implementation documentation: [pydisort source](https://github.com/zoeyzyhu/pydisort) and [Python API](https://pydisort.readthedocs.io/en/latest/api.html).
