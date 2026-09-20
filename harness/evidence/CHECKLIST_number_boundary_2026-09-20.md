# PR229 follow-up: number representation at calculation boundaries

Preserve the native 5 km column, operational trajectory, QC and all previous
diagnoses. Representation identities are conditional on a declared dry-mass
number basis; they do not assign that basis to historical stored values.

- [x] Correct the stale active-cloud slope docstring; no executable change.
- [x] Identify the earliest source boundary that passes unconverted number and
  distinguish source inspection from a new native-host measurement.
- [x] Capture applied rates and actual state-update operands for the retained
  active liquid case; reconcile the full selected state delta before interpreting
  the accretion component.
- [x] Check equivalent mass/volume representation of values, numeric thresholds,
  applied amounts and inverse conversion; include density-direction terms.
- [x] Independently review evidence and run focused checks; refresh Graphify.
- [ ] Close the physical host/kernel number basis and all threshold policies.
- [ ] Obtain nonzero, matched-source transport departure and arrival. A
  representation identity or a local collection sink is not transport evidence.
- [ ] Close independent radiation accuracy and accepted liquid BT/cost. The
  existing liquid observation gate remains 0/9.
