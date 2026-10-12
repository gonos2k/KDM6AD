# Red postrun review: PR416 hourly selected native column

## Disposition

**The single read completed and the saved profiles match the private selected-slice record.** I reviewed the summary, public CSV, plan, and private NPZ only; I did not reopen the forecast file. The prior temperature conversion issue was corrected before extraction, and the stored arrays independently confirm `T = theta_dry × PII`.

## Saved-output checks

`SUMMARY.json` reports `READ_COMPLETE_NO_MODEL_CALLS` and binds plan SHA-256 `b38b0493ac9a2764b0f75dae0e276ba2e76747d0fb870d7bb720fac07c2b4b25`. The final extractor SHA-256 is `8bb99057f9b2ca60fbfa8aa76c00ad56bb7717dfd086a371347251a4f061c088`, matching both the regenerated plan source receipt and the summary receipt. The selected output NPZ contains 270 arrays, mode `0600` in a `0700` parent; its recorded digest is `4a2f7e636c90ab38fa7a09d123977d82f093d0a956051d83ced53e21575760ec`.

The public CSV has 117 data rows, exactly 39 levels each for saved times at indices 5, 6 and 7 (05:00, 06:00 and 07:00 UTC). I compared all 4,563 profile-field values against the private NPZ using the CSV writer's round-trip formatting; there were no mismatches. For every time, all raw-slice hashes in the summary match the NPZ arrays; stored raw arrays retain `float32` and their separate boolean masks contain zero masked values. Summary units and shapes align with the saved pressure, temperature, moisture, wind, height and density arrays.

The forecast before/after stat records are identical (size, nanosecond mtime, inode and device), and the summary states that no native-model, KDM-M, all-sky-H, RTTOV or optimizer calls occurred. No time interpolation, reselection or forecast writes were used. No full 4.13 GB forecast hash was made, so the stat checks do not establish byte identity against a hypothetical same-stat mutation.

## Independent arithmetic and temporal checks

From the private raw `THM`, `QVAPOR`, `P`, and `PB` arrays, I independently recomputed `theta_m = THM + 300`, `theta_dry = theta_m / (1 + (461.6/287) QVAPOR)`, `PII = ((P+PB)/100000)^(2/7)`, and `T = theta_dry × PII`. Across all three 39-level columns, each recomputed `theta_m`, dry theta, temperature and center pressure array matches its stored derived array exactly in float64 arithmetic. The observed temperature ranges are 201.488–297.045 K at 05:00, 200.615–297.211 K at 06:00, and 200.214–297.464 K at 07:00. The old moist-theta multiplication is not present in the final source/result.

The native center pressure is strictly decreasing bottom-up, reconstructed P8W is strictly decreasing, and geopotential interface height is strictly increasing with positive layer thickness for all three profiles. P8W is derived by a source-hash-validated Python REAL(4) transcription; the forecast's declared variable list does not contain a saved P8W variable, and the WRF Fortran routine was not executed. The raw `PH`/`PHB` values are saved geopotential fields used for heights, not pressure interfaces.

Adjacent-face `U` and `V` means in the NPZ match the recorded grid-center winds exactly. Recalculation of `Ue = Ug·COSALPHA − Vg·SINALPHA` and `Vn = Vg·COSALPHA + Ug·SINALPHA` matches all stored earth-relative wind values exactly. `W` remains a 40-level interface field represented by lower/upper values in the 39-level CSV profile; it is not averaged to mass levels.

The three saved snapshots differ. Maximum profile changes are 2.522 K in temperature, 5.670 K in dry theta, `3.104×10⁻⁴ kg/kg` in QVAPOR, and `1.483×10⁻³ kg/m³` in dry density for 05:00→06:00; corresponding 06:00→07:00 changes are 0.891 K, 1.668 K, `3.991×10⁻⁴ kg/kg`, and `2.891×10⁻³ kg/m³`. Fixed-dry-air QCLOUD column mass is 0.007922, 0.002475, then 0 kg/m²; QRAIN is `1.322×10⁻⁵ kg/m²` then zero. The host dry-mass sum also changes from 9717.137 to 9713.594 to 9702.591 kg/m². These are instantaneous model-state diagnostics, not a closed column budget or physical flux-conservation test; no process rates or boundary-flux terms were calculated.

## Provenance and scope limits

The fixed point is `j=103, i=48`, 36.1953430°N, 122.0966797°E, on a 5 km, 39-mass-level grid; all three samples are ocean (`XLAND=2`) with no sea ice and the recorded selected raw fields have zero masks. This is one column from the completed four-rank MP137 child forecast. PR415 is a separate one-rank local KDM optimization over a different time setup, so these records are not a matched experiment and should not be used as a direct comparison. No AMI scenes were decoded or used here.

The hourly candidate still has no executable-byte or exact IC/BC/`wrfchainp` input hashes, the `wrfchainp_d01` `START_DATE`/forecast `Times` mismatch is unresolved, and the 12:00 boundary endpoint ends the final `[09:00,12:00)` interval exclusively for further host advancement. This diagnostic does not establish observed cloud truth, process attribution, forecast skill, or model evolution after 12:00.
