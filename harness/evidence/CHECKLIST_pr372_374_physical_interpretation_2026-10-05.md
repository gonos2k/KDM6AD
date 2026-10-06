# PR #372–#374: existing physical interpretation items

This follow-up keeps the bounded numerical and worker closures intact. It
quantifies the saved analysis, without changing physics, thresholds, QC, priors,
observation weights or native inputs.

| Existing question | Result | Status |
| --- | --- | --- |
| Is cost reduction an NC-only correction or convergence? | Four state controls changed; two iterations ended with gradient norm 1.50711. Cost reduction remains a diagnostic joint-state descent result. | Interpretation fixed |
| What water did the analysis add? | Existing native arrays give +0.101512531 kg/m² on one fixed background dry measure, mostly vapor; operator measure separately gives +0.102902660. [Signed report](REPORT_native_analysis_inventory_2026-10-05.md). | Bounded inventory accounting complete |
| How does the slot increment relate to the initial increment? | The signed species identity separates initial analysis changes and both model legs. Liquid slot difference +0.044497510 kg/m² is not the initial QC control alone. No named-process attribution inferred. | Bounded endpoint decomposition complete |
| What heat inventory changed? | Existing per-phase and operator-potential state functions give different conditional increments. References and constants are recorded; missing flux/work terms remain null. | Conditional inventories complete; S17 OPEN |
| Which density is used? | Current fixed-forcing research keeps initial-background optical density and a common fixed inventory measure. Runtime entry density and live-entry optics have different roles/derivatives; no policy is selected by smaller FD error. | Current numerical policy explicit; host/S2 physical reference OPEN |
| Does `cloudy_clear` prove an observed clear scene? | It is the existing IR105 <270 K proxy combined with background slot-time model condensate support. No independent cloud mask was used; threshold unchanged. | Interpretation fixed |
| Can this approve physical analysis, B/R/bias, product/SRF, forecast or cycling? | Single-column/fixed-target arrays supply neither independent calibration nor net boundary flux/external-work evidence. Existing S2/S11/S17 and operational conditions remain unresolved. | OPEN |

The [executed offline source](NATIVE_analysis_inventory_source_2026-10-05.py)
and [result](NATIVE_analysis_inventory_result_2026-10-05.json) pin the input
arrays, existing state-function source, enthalpy conventions and arithmetic
environment. This is not a new KDM/RTTOV run or an added meteorological case.

The subsequent [host dry-mass source audit](REPORT_native_host_mass_reference_2026-10-06.md)
identifies the hybrid-coordinate reference in the active host and evaluates it
from the same retained frame. It differs from the earlier rho_d*dz measure;
hypsometric option 2 explains the dominant difference. Snapshot identification
does not supply live staged mass/flux terms or settle all S2/S17 contracts.
