# PR399 vertical-neighbor Green consistency review

Scope: final PR399 report/checklist, saved vertical/count audits, neighbor-H receipts and cost-range comparison, and bounded IC/BC source trace. This review is read-only. I made no M/H/RTTOV, optimizer, or native-model calls and did not rerun calculations or tests.

## Vertical result and corrected count

The vertical result is derived from the saved PR398 native patch, not a new forecast. Its 324 lower-layer rows are 9 fixed cells × 3 saved times × 12 levels. For adjacent levels, each 12-level profile contributes 11 valid pairs, so the correct total is 27 × 11 = 297. The preserved V2 value 891 triple-counted the time-expanded profile count; the separate count audit corrects it without rewriting the original outputs. The 51 temperature-inversion flags and 216 positive `dtheta_v/dz` flags are counts over the 297 valid pairs and remain intact.

The stored-state diagnostic places the largest water-referenced phase-aware `qv/qs` near bottom-up k=3 at roughly 261 m AGL, with a warmer, drier layer above around k=4–5. The ratio is about 95.5% in the center example, while the 27-profile maxima are 95.146–95.988%. This is a thermodynamic/vertical-state description; it does not imply cloud condensate, a measured PBL structure, a tendency, or a causal PBL, transport, radiation, surface, or microphysics attribution. Zero QC/NC and nonzero QNCCN remain distinct facts.

The sensitivity terms are finite-endpoint decomposition of the saved qv/qs change, not rates or named-process contributions. The warm/unclipped endpoint condition and explicit nonlinear remainder are reported. Future source V3 is labeled unexecuted, so it is not evidence for the corrected counts.

## Fixed-geometry neighbor H result

The failed first attempt is preserved as fixture preparation failure caused by missing O3/CO2 inputs; it completed no H call. Attempt 2 used a fresh plan/output namespace after an offline fix and validated the six-vector gas/profile fixture preparation for all eight neighbors before H. It then made eight actual neighbor H calls and reused the hash-bound PR398 center H once. This is explicit setup recovery, not an automatic retry or repeated completed H. All nine rows retain seven-channel support with zero `rad_quality`; the receipts and comparison report costs recomputed from saved BT under the same target, frozen mask, sigma, bias, and Huber delta.

The model IR105 range is 296.0824–296.2709 K. The observed AMI 5×5 IR105 range is 288.9325–293.7085 K, leaving the lowest modeled value 2.373946 K above the highest observed patch value. The report identifies this as conditional on fixed AMI candidate geometry, native saved columns, profiles, pressure, density, surface and paired BT coordinates. The observed pixel patch and nine H columns have different spatial support; this difference is not a per-pixel residual, a verified footprint comparison, or a hard lower bound outside these finite samples. Other channel intervals and the unchanged center reuse are reported separately. No minimum-cost neighbor was selected as a replacement candidate.

## Provenance, scope, and consistency

The IC/BC trace supports the bounded lineage in the report: existing canonical symlinks point to REAL_EM V4.6.0 outputs for a 5 km, 39-level, July 19 initialization with boundary data through 09:00. It does not identify the upstream raw meteorological archive or preprocessing configuration. The 84 local forecast variants are not independent dates, and the unavailability finding is bounded to the inspected local inventory; the optional user question about other IC/BC archives remains open.

The report and checklist keep the denominator correction, attempt-1 failure and attempt-2 recovery, eight actual versus one reused H result, fixed geometry, and no-new-native-run scope distinct. They do not attribute a cause, imply global retry behavior, turn spatial BT differences into forecast skill, or claim independent events, physical footprint agreement, calibrated B/R, or full flux closure. Score remains the user-reviewed 56/75 basis with no automatic PR399 points.

The checklist now marks Green/Red and canonical source preservation done. `PRESERVATION_VERIFICATION.json` records the canonical vertical NPZ (`5d02e8bb…30263c0`) and neighbor NPZ (`4e2c3607…e1c793`), with canonical file mode 0600 and directory mode 0700, plus the executed vertical support sources and neighbor source. The receipt records zero H/M calls for preservation verification and retains the original vertical result and denominator correction audit. No remaining consistency blocker was found in the results, provenance scope, and limits reviewed; independent dates, upstream meteorological source, matchup and physical closure questions stay open as scientific scope.

The Graphify query returned generic pressure/native nodes and no focused PR399 chain. This review and its semantic fragment are scoped mappings, not a full graph refresh.
