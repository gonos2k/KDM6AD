# PR223 follow-up: layer contributions and an existing liquid-process candidate

Scope: first-order KDM–GK2A/RTTOV sensitivity on the existing 5 km model's
native levels. Reuse retained evidence; no external atmospheric data, production
physics changes, QC relaxation, or new CI version matrix.

- [x] Preserve the selected PSFC-bottom experiment and previous closed findings.
- [x] Replay retained raw K tokens and fixed profile tangents by field and layer;
  check their sums against the published channel products.
- [x] Quantify K text-rounding contribution separately from full numerical error.
- [x] Publish sufficient compact operands for independent arithmetic replay.
- [x] Record candidate criteria, source/time selection and corrections before
  treating a warm-liquid column as validation evidence.
- [x] Check actual applied autoconversion/accretion rates and native state/profile
  sensitivities before spending new RTTOV calls.
- [x] Execute five native RTTOV endpoints with fixed auxiliary/QC conditions.
  All nine clean IR observations are RTTOV-QC excluded (32768); retain raw
  channel comparisons as diagnostics, not accepted BT/cost validation.
- [x] Green/Red review: check claims, operand provenance and reproducibility.

A rejected or unresolved candidate remains evidence of that outcome. It does not
close the active liquid-process observation connection. Broader regimes, exact
pixel navigation, upper/gas assumptions, physical number units, nonzero transport
and timestep sensitivity remain open independently.

Evidence: [layer report](REPORT_layer_contributions_2026-09-19.md),
[offline liquid candidate](REPORT_pr224_warm_liquid_candidate_2026-09-19.md),
[live QC-excluded result](REPORT_native_liquid_accretion_2026-09-19.md).
The first 24 candidates failed the nonzero-rate gate; ordinal 25, column 35711,
has active accretion at three warm native levels. Local diagnostic script
corrections were completed before accepting derivative evidence.

Validation so far: Python 3.12 stdlib layer replay and syntax check pass; altered
K tokens, NaN tangent, truncated summary, and mutually altered field/total deltas
are rejected. Green and Red reviews support the scoped offline claims. Existing
Python 3.12 CI policy is unchanged; no new CI job or version matrix is added.

- [ ] Accepted nonzero liquid-process BT/cost validation remains open. The
  Delta-Eddington extinction limit is exceeded; no QC relaxation or candidate
  substitution was used. Two failed setup attempts and five completed calls
  are counted separately. Empty-mask zero cost is not successful validation.
