# PR391 observation correspondence scope

Date: 2026-10-09. Scope: observation-side evidence for the pre-existing
VIIRS row 205/column 27, AMI row 320/column 48, native cell j86/i48 selection.
This review preserves the selected candidate and does not approve a science
comparison, select a residual-favored correspondence, or change sigma/bias.

## Directly measured or retrieved

| Quantity | Evidence | Interpretation boundary |
| --- | --- | --- |
| VIIRS candidate | NOAA-20 JRR-CloudPhase v3r2 file `JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc`, SHA-256 `7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2`; row/column `(205,27)`, nominal location `(35.4156379700 N,122.1433868408 E)`. | Exact file/pixel identification from retained producer and receipts; full cloud phase original hash pinned. |
| Native nominal center | Initial private IC `wrfinput_d01` hash `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970`; geometry `(282,234)`; cell `(j=86,i=48)` at `(35.4156608582 N,122.1433105469 E)`. | Spherical nominal-center distance is 7.3673587006 m. This measures coordinate proximity only, not footprint overlap or target-time state. |
| Phase and raw QA | Stored `CloudPhase=1`, `CloudPhaseFlag=0`; `CloudType=2`. The candidate screen was declared as phase 1, stored QA byte 0, native `XLAND=2`, distance at most 3.5 km and 10-cell edge margin, then minimum distance. | NOAA Cloud Type ATBD v3.0 Table 31 describes 1 as liquid (>273 K retrieval category); this is cloud-top category evidence, not proof the full native column is warm, single-layer, or nonprecipitating. QA has not been scientifically approved. |
| Corrected QA counts | Context result reads stored bytes without netCDF automatic masking/scaling. For this granule, 214,771 nonfill stored bytes outside declared 0..1 were automatically masked by the earlier default netCDF read; the previous local-interior histogram's 19,338 `-128` values were false fill counts. No true fill `-128` occurred in these full arrays. The selected stored byte remains 0. | Raw bytes and prior flawed counts are both retained. No bit decoder or QA approval is inferred. |
| Same-overpass cloud retrieval | Generation-pinned CloudHeight/CloudDCOMP HDF5 ranges, target `(205,27)`, gave CTH 587.7369385 m, CTT 296.5706787 K, CTP 940.9852295 hPa, height QA 0, height parameter flags `[3,1,1,1,1]`; DCOMP optical depth 2.6809735 and effective radius 113.55732 µm. All 36 sampled stored values replayed from cached blocks. | Product outputs are derived from the same VIIRS overpass and use ancillary model inputs; they are not independent truths. Height datum / surface-relative meaning is not fixed by the stored field alone. DCOMP `EQualityFlag=17` exceeds its declared valid range 0..6; do not adopt optical depth/radius as accepted truth. The full height/DCOMP granules were not downloaded or full-file hash verified. |
| Neighborhood | Spherical nominal-center neighborhood counts around VIIRS target: within 1 km, 3 phase-1/cloud-type-2 centers (QA bytes 0:2, 5:1); within 3.5 km, 36 all phase 1/type 2 (QA 0:29, 5:7); within 5 km, 75 all phase 1/type 2 (QA 0:66, 5:9); within 10 km, 291 (288 phase 1/type 2, 3 clear/type 0). | Centers are not independent samples, true pixel footprints, optical-depth averages, or proof of uniform cloud structure. |
| VIIRS scan geometry/time | Full GMTCO original SHA-256 `2a194c417533a1087543cc7a91b1de2a5a6d8d71d1d71e2bfeb1571cc9f8dd0c`; EDR valid latitude/longitude exactly match its geolocation arrays. Sensor zenith 68.9266891°, azimuth −91.7182388°. Product anchor 05:55:47.547447Z plus same-granule IET differences brackets scan 12 start at 05:56:08.986512Z and next scan start 05:56:10.773095Z; target is scan 12, detector 13. | This is a scan bracket, not a per-pixel time. Absolute IET epoch/leap-second conversion is not independently certified. Granule bounds alone do not prove synchronization. |
| AMI selected pixel | Existing LA reader decoded the 05:56 slot, row/column `(320,48)`, nominal location `(35.4192506933 N,122.1372416465 E)`, IR105 `291.3025922 K`, nine DQFs all zero. Center distances: AMI–VIIRS 686.6436229 m; corrected AMI–native 679.550498963 m. | DQF zero is instrument sample quality only; it does not establish time or common footprint. Slot metadata calls the filename label OBT. AMI pixel UTC time remains null/unverified. |
| Target-time atmosphere artifact | Eight saved native states at 05:55:40 through 05:58:00 and eight RTTOV calls are reported in the 2026-10-08 packet. | The 358-minute launcher returned 1 and experiment validity remains false. Use only as diagnostic artifacts. Native centers/T/Q are retained for the selected cell; interfaces are source-derived P8W transcription, not target-run P8W measurements. No observation correspondence is accepted by these artifacts. |

## Assumptions and unresolved facts

- VIIRS code 1 and CloudType 2 are retrieval classifications; phase/depth
  uniformity, warm single layer, no precipitation, full-column state, and
  scientifically accepted QA remain unverified.
- The CloudHeight field is a retrieved height but no exact datum is established
  here. Its parallax-corrected coordinate is about 1,525.19 m from the nominal
  pixel. A local flat tangent-plane calculation gives 2,866.61 m of relative
  shift per assumed 1 km height for the VIIRS/AMI view geometry; using 587.74 m
  above surface would imply 1,684.81 m. These are conditional scale checks, not
  an applied correction, actual cloud displacement, or pixel reassignment.
- AMI's raw observation start/end numbers are seconds with no resolved epoch;
  synchronization UTC/OBT fields are retained raw. The legacy Satpy noon-epoch
  interpretation places the nominal slot at 05:56:56.171461–05:57:56.016143Z,
  but remains conditional and is not treated as actual UTC.
- The already-used observation/native coordinate proximity is nominal-center
  geometry. Native output is at the initial-IC cell; the target native run's
  invalid launcher exit means no valid forecast/analysis claim follows.
- KMA v3.0 BT-coordinate conversion and fixed 1 K / zero-bias diagnostics in
  the target artifact do not validate SRF compatibility, timing, or physical
  correspondence. The observation audit does not choose settings based on BT,
  sigma, or bias.

## Predeclared correspondence cases for any later comparison

Retain one candidate and report cases separately; do not select among cases by
cost, residual, or desired result.

| Case | Time rule | Geometry rule | Meaning |
| --- | --- | --- | --- |
| A: nominal-coordinate diagnostic | Treat each saved native output time as a sample; no claim of exact VIIRS–AMI time match. Use nominal-center cell j86/i48 and AMI view geometry. | No cloud parallax or footprint correction. | Reproduces the current diagnostic sampling design only. |
| B: VIIRS scan-bracket timing | Report the fixed VIIRS scan bracket 05:56:08.986512–05:56:10.773095Z against the two available surrounding native saved times (05:56:00 and 05:56:20); no interpolation is implied. Clearly label AMI time unresolved. | Nominal centers; no parallax correction. | Brackets the scan with available frames without pretending either frame is a time-aligned state or that VIIRS and AMI are simultaneous. |
| C: conditional AMI slot epoch | If independently documented AMI epoch conversion is established, pair within that declared interval and its uncertainty; until then the noon-epoch interval is only a sensitivity scenario, not UTC evidence. | Nominal centers; no parallax correction. | Makes AMI clock conversion conditional and auditable. |
| D: conditional height-relative parallax | Keep A/B/C time rule fixed, state an independently justified height datum, then evaluate provided parallax coordinates alongside nominal VIIRS coordinates as a separate geometric scenario. | Report both coordinates/distances while retaining the selected candidate and native cell; do not reassign the column or infer footprint overlap from centers. | Sensitivity to a specified parallax convention; no candidate-selection or BT tuning. |

Do not combine B/C timing with D geometry and then rank scenarios by BT fit.
Until time, QA, full cloud structure, footprint and invalid-run status are
resolved, none of these cases constitutes an approved scientific matchup.

## Source and coverage notes

Primary local sources read: `REPORT_VIIRS_native_candidate_2026-10-07.md`,
`REPORT_VIIRS_context_2026-10-07.md`, `REPORT_native_target_artifact_2026-10-08.md`,
`VIIRS_native_candidate_result_2026-10-07.json`,
`VIIRS_context_result_2026-10-07.json`, `VIIRS_geometry_result_2026-10-07.json`,
`VIIRS_products_result_2026-10-07.json`, `VIIRS_AMI_candidate_result_2026-10-07.json`,
`NATIVE_geometry_correction_result_2026-10-08.json`, and the corresponding
receipt archives. The prior graph at
`/private/tmp/KDM6AD-pr390-small-diagnostics-20261008/graphify-out/graph.json`
was queried for VIIRS candidate, timing, QA, geometry and footprint; its result
was mostly unrelated generic footprint nodes, so observation coverage is
incomplete and conclusions here are source/receipt based.

Official primary documentation already bound in the source packet:

- NOAA Cloud Type ATBD v3.0 (Tables 31–32):
  <https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_CldType_v3.0.pdf>
- NOAA JPSS VIIRS SDR Dictionary Rev L (scan geometry / geolocation QF):
  <https://nesdis-prod.s3.amazonaws.com/2024-01/474-00448-02-06_JPSS-VIIRS-SDR-DD-Part-6_L.pdf>
- NOAA ACHA ATBD v3.4 (relative cloud-height basis for parallax):
  <https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_ACHA_v3.4.pdf>
- KMA AMI data-use QA guide referenced by the unchanged LA reader for raw time
  semantics; local evidence does not resolve numeric epoch/UTC conversion:
  <https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf>

No new primary source closed the existing CloudPhaseFlag encoding or AMI clock
uncertainty. No external model/reanalysis data was acquired. No native/RTTOV
run, candidate change, or physics change was performed for this review.
