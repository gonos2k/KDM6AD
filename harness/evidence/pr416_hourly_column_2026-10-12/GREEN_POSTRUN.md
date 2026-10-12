# Green postrun review: selected Jul19 hourly native column

## Integrity and binding

The root executed the one declared read once. `SUMMARY.json` reports `READ_COMPLETE_NO_MODEL_CALLS`; its plan SHA matches `PLAN.json` (`b38b0493ac9a2764b0f75dae0e276ba2e76747d0fb870d7bb720fac07c2b4b25`). `READ_STARTED_ONCE.json` binds that plan to the selected source, times and column. The source is the run-specific MP137 child `.../runs/mp137_termparity_720min_hist60_np4_20260718_185625/klfs_lc05_fcst.202507190000`, not the case-root forecast.

The before/after forecast stat is identical; no full forecast hash was made. The private NPZ has 270 arrays, SHA-256 `4a2f7e636c90ab38fa7a09d123977d82f093d0a956051d83ced53e21575760ec`, mode `0600` in a `0700` directory. Public `PROFILE.csv` has 117 rows, 39 levels per selected time. All small source/run receipts still match their declared hashes and sizes. All raw selected variables have source dtype `float32`, and each source mask count is zero. The corrected extractor is bound by its summary source receipt. No forecast arrays were reopened by Green.

The fixed point resolves exactly to `(j=103,i=48)`, latitude `36.195343017578125`, longitude `122.0966796875` at 05:00, 06:00 and 07:00. All samples have `XLAND=2` and `SEAICE=0`; grid spacing is 5 km with 39 mass levels and 40 interfaces. The selected time indices are 5, 6 and 7. No other cells or times were selected.

## Independent physics and units checks

I independently recalculated values from the private NPZ only. The corrected temperature path is `theta_m=THM+300 K`, `theta_dry=theta_m/(1+(Rv/Rd)qv)`, `T=theta_dry*PII`, matching the source-backed PR406 V2 `_selected_frame`. Independent values for dry theta, physical temperature, P/PB center pressure, dry/moist density, height and layer thickness match the stored derived arrays. The earlier preflight endorsement of `theta_m*PII` was wrong; root corrected that P2 before the one actual read, and the older Green/Red drafts were preserved. In this column, the incorrect moist-theta temperature would exceed the corrected temperature by as much as 8.19 K at 05:00, 8.30 K at 06:00 and 8.34 K at 07:00.

I reimplemented the declared P8W source transcription from saved P/PB/PH/PHB/FNM/FNP slices using REAL(4) operations; all 40 interfaces match exactly. This is a Python transcription, not execution of the host Fortran routine. The dry-air mass sum and hydrometeor mass columns recompute from the saved arrays. Staggered U/V center winds match arithmetic means of adjacent faces; earth-relative components match `Ue=Ug*COSALPHA−Vg*SINALPHA` and `Vn=Vg*COSALPHA+Ug*SINALPHA`. Raw neighbor pairs, W interfaces, U10/V10, COSALPHA/SINALPHA, source dtypes and masks are retained privately. Every saved raw slice hash, CSV row value, mask count, and summary unit/shape claim passed my independent check.

Temperature ranges are 201.488–297.045 K at 05:00, 200.615–297.211 K at 06:00, and 200.214–297.464 K at 07:00. QVAPOR ranges are `2.48e-6–0.01714`, `2.99e-6–0.01736`, and `2.50e-6–0.01743` kg/kg. Fixed-dry-air QCLOUD column mass is `0.007922`, `0.002475`, and `0 kg m-2`; QRAIN is `1.32e-5 kg m-2` at 05:00 and zero at 06:00/07:00; QICE, QSNOW and QGRAUP column masses are zero at all three samples. These are stored model-state diagnostics, not microphysical rates, external fluxes, retrieved cloud truth or process attribution.

For 05→06, maximum absolute profile changes are 2.522 K for T, 5.670 K for dry theta, `3.104e-4 kg/kg` for qv, and `1.483e-3 kg m-3` for dry density. For 06→07 they are 0.891 K, 1.668 K, `3.991e-4 kg/kg`, and `2.891e-3 kg m-3`. They compare three saved hourly endpoints only; they do not imply a continuous tendency or a new forecast run.

## Scope limits

No native-model run, KDM M, all-sky H, RTTOV, optimizer, or acquisition occurred. This is one selected-column read from the completed hourly MP137 child. The 12:00 boundary endpoint is end-exclusive for further advancement. The run’s executable and IC/BC/wrfchainp byte hashes remain unbound; the `wrfchainp_d01` `START_DATE`/`Times` discrepancy remains unresolved. The samples do not establish forecast skill, atmospheric truth, cloud truth or process causality.

**Disposition:** Green confirms the single bounded read, source/stat integrity, fixed selected point/time, corrected temperature calculation and consistency of saved profile/summary values. The earlier Green/Red preflight endorsement of the moist-theta temperature conversion was incorrect; root corrected it before the sole read, and the values here verify the corrected dry-theta formula.
