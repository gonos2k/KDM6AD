# PR398 native 3x3 saved-frame spatial diagnostics

Diagnostic only. The arrays use the fixed native cells j=85..87, i=47..49 at saved frames 1/4/6. No M/H, optimizer, new native run, or external data was used.

Private NPZ SHA256: `947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21`; canonical copy SHA256: `947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21`.

VIIRS region filter is the axis-aligned bounding box of native 3x3 cell centers. The corners below are descriptive bounds of center coordinates only, not cell-edge or sensor footprint corners.

| Frame/time | Native center-bounds corners (NW, NE, SE, SW; lat/lon deg) | VIIRS candidate center inside |
|---|---|---|
| 1 / 2025-07-19_05:56:00 | northeast=35.463676,122.202209; northwest=35.463676,122.084351; southeast=35.367634,122.202209; southwest=35.367634,122.084351 | True |
| 4 / 2025-07-19_05:57:00 | northeast=35.463676,122.202209; northwest=35.463676,122.084351; southeast=35.367634,122.202209; southwest=35.367634,122.084351 | True |
| 6 / 2025-07-19_05:57:40 | northeast=35.463676,122.202209; northwest=35.463676,122.084351; southeast=35.367634,122.202209; southwest=35.367634,122.084351 | True |

`maxsat` is the KDM6 phase-aware qv/qs diagnostic, not observed vapor-pressure RH. QC and NC sums are unweighted native-level summaries; unweighted QC sum is not LWP. QN number basis is not calibrated; no mass-weighted LWP or area-weighted matchup score is claimed.

Per-cell arrays and diagnostics are in the private NPZ/result. These nine cells are not independent 5 km scenes, and the seven-band VIIRS/AMI comparison remains NOT_ASSESSED.
