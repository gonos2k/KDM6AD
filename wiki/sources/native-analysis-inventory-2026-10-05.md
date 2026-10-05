---
title: Native analysis signed water and heat inventories (2026-10-05)
type: source
date_modified: 2026-10-05
---

The [offline inventory calculation](../../harness/evidence/REPORT_native_analysis_inventory_2026-10-05.md)
uses saved NATIVE analysis endpoints, with initial-background dry density held
fixed at every endpoint and the operator moist-density measure shown separately.
It does not repeat the model, RTTOV or optimizer experiment.

The initial analysis adds 0.101512531 kg/m² of water on the declared dry measure,
almost entirely vapor. At the observation slot, the liquid difference is
0.044497510 kg/m². Decomposing the slot increment into initial increments and
both model-leg endpoint changes prevents attributing that liquid or number
response to the initial QC/NC control alone. It does not identify a named process.

The two existing G33 state functions give conditional heat inventory increments
of 206.77 and 202.87 kJ/m². These are not physical closure residuals: boundary
flux, applied extents, heat and work are missing. Adding a common water enthalpy
reference offset changes delta-H by that offset times the added water, so the
reference and externally supplied mass enthalpy must remain explicit.

The [interpretation checklist](../../harness/evidence/CHECKLIST_pr372_374_physical_interpretation_2026-10-05.md)
keeps S2/S11/S17 and operational approval open. `cloudy_clear` is the original
IR105 threshold proxy, not an independent observed cloud mask. The current
fixed-forcing optical-density convention is retained as a declared research
operator, without equating it to live-entry optics or canonical host dry mass.
