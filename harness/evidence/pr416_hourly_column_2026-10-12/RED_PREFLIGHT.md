# Red preflight correction: PR416 hourly native column

## Disposition

**GO after correction, before any selected forecast-column read.** The original draft Red preflight was archived as `RED_PREFLIGHT_DRAFT_BEFORE_TEMPERATURE_CORRECTION.md`. Its endorsement of the temperature conversion was wrong: it repeated the pre-correction line that multiplied moist potential temperature by Exner. Root review found and fixed this P2 issue before execution. It affects only this research diagnostic; it does not indicate a defect in legacy production physics or the AD implementation.

## Corrected conversion and bindings

The final extractor now retains `theta_m = THM + T0`, takes dry potential temperature from the source-backed selected-frame reconstruction (`native["th"]`), and computes physical temperature as `theta_dry * native["pii"]`. This matches the WRF theta-m conversion in the bound PR406 selected-frame helper. The previous `theta_m * PII` expression would yield a moisture-inflated temperature and is not used by the final plan/run.

The corrected extractor SHA-256 is `8bb99057f9b2ca60fbfa8aa76c00ad56bb7717dfd086a371347251a4f061c088`. The refreshed plan SHA-256 is `b38b0493ac9a2764b0f75dae0e276ba2e76747d0fb870d7bb720fac07c2b4b25`; its self-source receipt matches the final extractor. It remains `PREDECLARED_NO_COLUMN_READ` and points to the fixed child MP137 hourly forecast, July 19 times 05:00/06:00/07:00 at `j=103, i=48`. The prior unexecuted script, plan, Green report, and Red report are retained with `_DRAFT_BEFORE_TEMPERATURE_CORRECTION` suffixes for provenance.

The other bounded-read checks remain intact: exact child run identity and terminal markers; saved Times and fixed geolocation; schema checks for dimensions/shapes/dtypes/units; selected column and adjacent staggered U/V slices only; separate mask preservation; positive layer thickness and ordered 40-level P8W validation; source/stat/plan drift checks; one-shot output guards; no forecast writes, no full-grid read, no interpolation/reselection, and no H/M/RTTOV/optimizer calls. The forecast file is stat-bound rather than fully hashed. P8W remains a hash-validated Python REAL(4) transcription, not an executed WRF Fortran call.

No forecast weather arrays were read during this correction review. The archive still lacks the run executable digest and exact input-file hashes; the `wrfchainp_d01` `START_DATE`/forecast `Times` mismatch remains unresolved, and the `[09:00,12:00)` host boundary interval ends exclusively at 12:00. The four-rank hourly MP137 run is separate from the PR415 one-rank local KDM optimization, not a matched experiment, and this diagnostic cannot establish observed cloud truth, process attribution, forecast skill, or host advancement after 12:00.
