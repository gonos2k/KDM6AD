# PR395 fixed-candidate observation correspondence

Date: 2026-10-10. Candidate is frozen at VIIRS `(row=205,col=27)`, AMI
`(row=320,col=48)`, and native `(j=86,i=48)` zero-based. This note uses
already-local satellite originals, byte-range receipts, existing result JSON,
and official KMA/NOAA documentation. It does not change the candidate, import
model/reanalysis data, reuse the failed target forecast as a valid run, or infer
match quality from BT residuals.

## Source-bound observations

| Topic | Confirmed from source/artifact | Boundary that remains |
| --- | --- | --- |
| VIIRS identity and position | NOAA-20 `JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc`, full local file size 8,810,069 bytes, SHA-256 `7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2`; raw file hash matches the pinned result. Pixel `(205,27)`, nominal center `(35.41563796997 N,122.14338684082 E)`. | This fixes product and sample identity only. |
| Native center | Original IC hash `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970`, grid 282×234, fixed cell `(86,48)` at `(35.41566085815 N,122.14331054688 E)`. VIIRS/native nominal-center distance is 7.3673587 m. | Center proximity is not a sensor-footprint or model-cell-average match. |
| VIIRS phase and quality byte | Full CloudPhase file stores `CloudPhase=1`, `CloudType=2`, `CloudPhaseFlag=0`. File metadata binds history to Enterprise Cloud Phase/Type Algorithm v2.2.0, delivery v3r2. NOAA Cloud Type ATBD v3.0 Table 32 defines six phase/type quality flags with 0 = high quality; the NOAA-21 v3r2 family readme says `CloudPhaseFlag` is a packed byte. Since the selected byte is zero, each documented quality flag is zero regardless of bit-origin convention. The selected pixel's phase/type QA therefore resolves as high quality under this v3r2 product-family interpretation. | NOAA-21 documentation is a sibling-platform family readme, not a NOAA-20 pixel-specific maturity approval. Do not decode the other nonzero stored bytes from that generalization. The granule's declared `valid_range=[0,1]` conflicts with packed nonzero bytes: 214,771 nonfill bytes are outside it; the prior netCDF default-mask histogram falsely counted 19,338 as `-128` fills; the raw arrays contain zero actual `-128` fills. Keep that metadata/counting defect explicit. High product QA does not prove full-column phase, single layer, non-precipitation, or a physical matchup. |
| Same-overpass CloudHeight | Generation-pinned CloudHeight object `JRR-CloudHeight_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc`, generation `1752906345359928`, full size 71,779,579 bytes. Existing range result/replay gives CTH 587.7369385 m, CTT 296.5706787 K, CTP 940.9852295 hPa, `CloudHgtQF=0`, diagnostic bytes `[3,1,1,1,1]`. NOAA-21 ACHA v3r2 family readme defines `CloudHgtQF=0` as fully successful retrieval. | Only targeted generation-pinned HDF5 ranges totaling part of the 8,235,094-byte multi-product receipt exist; the full height object was not downloaded or full-file hashed. Keep `CldHgtFlag` diagnostic bytes raw. `CldTopHght` attributes give units `Meter` and no explicit vertical datum. The successful QA flag supports retrieval success, not height accuracy for this pixel or datum certainty. |
| Cloud parallax field | The same Height range result stores parallax-corrected location `(35.415225983 N,122.126564026 E)`, 1,525.19 m from the nominal VIIRS center. NOAA ACHA v3.4 equations use `(Zc−Zs)` (cloud-top height relative to surface height) and satellite viewing geometry. | `Zs`, exact datum of this file's `CldTopHght`, and actual cloud displacement are not independently established. Product-provided corrected coordinates are an algorithm output, not an independent overlap measurement. Do not shift/reassign the frozen candidate. |
| Cloud optical/microphysical product | Generation-pinned DCOMP target is at the same VIIRS pixel/overpass. Stored optical depth is 2.6809735, effective radius 113.55732 µm, but `EQualityFlag=17` lies outside its declared 0..6 range. | Full DCOMP object is not downloaded/full-file hashed. Do not use DCOMP values as accepted optical/microphysical truth and do not infer mixed phase by comparing LWP/IWP fields. |
| VIIRS scan time and geometry | Full matching NOAA-20 GMTCO original is present, size 33,174,372 bytes; SHA-256 `2a194c417533a1087543cc7a91b1de2a5a6d8d71d1d71e2bfeb1571cc9f8dd0c` matches the prior record. EDR valid lat/lon arrays match GEO exactly. Target is scan index 12, detector 13 of 16; geolocation reports sensor zenith 68.926689°, azimuth −91.718239°. Official SDR Dictionary Rev L defines per-scan `StartTime` in IET microseconds since 1958-01-01 and the azimuth convention. Combining same-granule IET differences with its UTC aggregate anchor yields the existing scan-start bracket `05:56:08.986512–05:56:10.773095Z`. | GEO supplies scan timing, not a target-pixel exposure time. The bracket must not be restated as exact per-pixel UTC or AMI synchronization. It brackets native saved frames 05:56:00 and 05:56:20, not an interpolated model state. |
| AMI sample and metadata | Existing original LA IR105 file is present, size 532,071 bytes, SHA-256 `824ee57213da084e8f3f129fd2767cee1f68e0bb10ef101d7419b7c4ec3ea889`, matching the selected AMI result. The fixed pixel `(320,48)` is `(35.4192506933 N,122.1372416465 E)`, IR105 291.3025922 K; all nine DQFs are zero. Local-area grid is 500×500, nominal IR channels 2 km, SINC resampling; file metadata reports three source swaths. AMI–VIIRS and AMI–native center distances are 686.644 m and 679.550 m. | KMA L1B guide says `scene_acquisition_time` is the OBT time of the first swath/first packet, and `mission_reference_time` is the planned UTC start for the whole image. It documents start/end values in seconds and a UTC/OBT synchronization pair but does not state the numeric epoch or a selected-pixel clock. DQF zero is sample quality, not timing or footprint quality. |

## AMI clock: evidence and conditional mapping

The selected LA file reports `scene_acquisition_time=20250719_055656` (OBT),
`mission_reference_time=20250719_055000` (planned UTC),
`observation_start_time=806176616.1714611`,
`observation_end_time=806176676.0161434`,
`time_synchro_obt=806176616.1714611`, and
`time_synchro_utc=806176616.1774336` seconds. The UTC/OBT synchronization
pair differs by 0.0059725 s. In this same file, treating the numeric values as
seconds from `2000-01-01 12:00:00Z` maps the OBT synchronization value to
`2025-07-19 05:56:56.171461Z`, which rounds to the documented first-swath OBT
string `20250719_055656`; the paired UTC field maps to `05:56:56.177434Z`.
This is a strong internal cross-field consistency check for the epoch/offset
hypothesis. The official KMA guide does not specify that numeric epoch or state
that the one measured offset is constant over the whole scan. Therefore the
result is a conditional file-level interval, not certified per-pixel UTC:

- Raw numeric interval under the internally supported noon-epoch mapping:
  `05:56:56.171461–05:57:56.016143` on the OBT axis.
- If the synchronization offset is treated as constant across the scene, the
  corresponding exploratory UTC interval is
  `05:56:56.177434–05:57:56.022116Z`.
- The target AMI pixel has no acquisition-time array or per-pixel line/scan
  timestamp in the retained product result. Its exact UTC cannot be assigned
  from the filename, first-swath label, or full-scene interval alone.

Under that conditional clock mapping, the AMI full-image interval starts about
45 seconds after the VIIRS scan bracket. This is evidence against calling the
two samples simultaneous under the assumed mapping, but it is not an exact
pixel-to-pixel time difference.

## Footprints and allowed cases

The retained center distances are measurements of nominal coordinates. The
VIIRS view zenith is 68.93°; the AMI product is a 2 km SINC-resampled LA grid;
the model is the current 5 km native grid. The available artifacts do not
include per-pixel VIIRS detector-footprint polygons, the AMI SINC source-weight
map for `(320,48)`, or a common observation/model spatial response operator.
Thus footprint overlap and representativeness of the 5 km cell remain
unverified. Use no center-distance threshold to claim footprint overlap.

| Scenario | Predeclared inputs | Allowed interpretation |
| --- | --- | --- |
| A — nominal-center diagnostic | Keep VIIRS `(205,27)`, AMI `(320,48)`, native `(86,48)`; no parallax. Use exact `Times` from the fresh native-run receipt. For a local one-step cost only, the predeclared `05:55:40` background plus 20 s reaches nominal slot `05:56:00` (`obs_time=1`). | Fixed spatial sample and actual saved model times. The `05:56:00` endpoint is nominal-slot alignment only, not AMI pixel-time or VIIRS scan-time collocation. Do not use the historical exit-1 checkpoint as the background; wait for the fresh run's own valid `05:55:40` frame before any such intake. Do not rank times by residual. |
| B — VIIRS scan bracket | Keep the same candidate; display the VIIRS bracket next to saved native `05:56:00` and `05:56:20` frames, if present in the fresh run. Do not interpolate. | Bracket context only; neither frame is the pixel scan time. AMI UTC remains unresolved. |
| C — conditional AMI slot clock | Also show the raw metadata and the conditional full-image interval above. Use saved model times that lie in/near it only as a sensitivity display; do not select on BT or claim pixel time. | Tests the internally consistent noon-epoch plus sync-offset interpretation. Requires an external epoch/clock contract and per-pixel timing before a matchup can be claimed. |
| D — provided parallax coordinate | Keep the fixed candidate and native cell; place nominal and product-provided corrected VIIRS coordinates side by side. A surface-relative-height calculation is only conditional on an independently stated `Zs`/datum. | Geometry sensitivity only. Never reassign the native cell or infer overlap from the shifted center. |

The scenarios must be reported separately; do not rank time/geometry choices by
BT cost, change candidate selection, retune sigma/bias, or infer a cloud source
from the model's initially clear column. The latest native run is a separate
fresh model experiment; at this note's preparation, the root reports it started
on 2026-10-10 at 05:26 JST and reached model time 00:00:20. Target-window saved
times/validity must come from that run's own receipt. This packet does not use
the historical exit-1 forecast as a valid native run or as observation-time
evidence. Its old `ti=0 @ 05:55:40` state cannot substitute for the fresh run's
05:55:40 frame in a local one-step cost intake.

## Documentation and acquisition manifest

Official complete documents captured on 2026-10-10 for this bounded question:

| Source | Product/version/date | Bytes and SHA-256 | Use |
| --- | --- | --- | --- |
| [NOAA-21 Cloud Phase provisional readme](https://www.star.nesdis.noaa.gov/jpss/documents/AMM/N21/NOAA-21_Cloud_Phase_Provisional_Readme.pdf) | Enterprise Cloud Top Phase/Type v2.2.0; delivery tag v3r2; effective 2023-03-30; review 2023-10-26. Sibling platform; combined with exact NOAA-20 file algorithm/package attributes and NOAA ATBD. | 261,143 bytes; SHA-256 `ef9b684b9d159c96dc7a10c77c4de126321c4fb332fdc3fe41106798784195f7` | Packed byte and phase QA flag values, Table 1, PDF p.3. |
| [NOAA-21 Cloud Height provisional readme](https://www.star.nesdis.noaa.gov/jpss/documents/AMM/N21/NOAA-21_Cloud_Height_Provisional_Readme.pdf) | Enterprise Cloud Top Properties v2.4.1; processing tag v3r2; effective 2023-03-30; review 2023-10-26. Sibling-platform product-family evidence. | 277,542 bytes; SHA-256 `726d8bf4912348e22422a4dd22593377bc3080ff0af61602af21d1b96af11fcd` | `CloudHgtQF=0` means fully successful retrieval, Table 1, PDF p.4. |
| [KMA GK-2A L1B Data Use QA](https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf) | KMA official guide; HTTP Last-Modified 2021-10-27. | 2,183,673 bytes; SHA-256 `ccefeaffc9550efa327f62db6f0d6d4b60ed4eb2a6faa559645dbe33892bb1bb` | Scene-time roles and attributes, printed p.17/PDF p.20; no numeric epoch/per-pixel time contract. |
| [KMA GK-2A L1B user manual package](https://nmsc.kma.go.kr/upload/resource/data/gk2a/20190524_gk2a_level_1b_data_user_manual.zip) | Official 2019-05-24 manual; contained PDF is dated 2019-06-03 in archive. | ZIP 1,260,375 bytes, SHA-256 `e61b2c8afd167447951b3bceaafb2187f03c6947fed861248ef33cbacf016b0f`; extracted PDF 1,445,310 bytes, SHA-256 `3ce9fda8ce668c3b1ffc524fa7b9729e1d7da4e618670d7430399247fda141e6` | Confirms OBT/planned UTC roles, Table 7 printed p.11; still no numeric epoch or pixel-time array. |
| [NOAA VIIRS SDR Dictionary Rev L, Part 6](https://nesdis-prod.s3.amazonaws.com/2024-01/474-00448-02-06_JPSS-VIIRS-SDR-DD-Part-6_L.pdf) | Document 474-00448-02-06 Rev L, effective 2023-08-30; S3 Last-Modified 2024-01-12. | 5,403,888 bytes; SHA-256 `eaa2d028ec39e71e8a6ef6ac590251d8e5f619cb6c6c1c36aae1ed1f3e76c7d5` | Table 6.2.65-1 p.142 confirms VIIRS scan-level IET `StartTime` and geolocation-array dimensions; does not provide per-pixel acquisition times or footprint weights. |

Previously local official PDFs used, not re-downloaded: NOAA Cloud Type ATBD
v3.0, SHA-256 `e31109a6f64efd68dc8b837f059a6944189cb15934f88eb5a5e034cdabd5ac2c`,
12,447,555 bytes; NOAA ACHA ATBD v3.4, SHA-256
`6c949aa1499eeec1ba631b7b8e594104df7d77d0b38dd0335eb8aa5a75162e19`,
5,908,021 bytes. The Cloud Type ATBD Tables 31–32 are pp.74–75; ACHA §4.4.2.12
is pp.42–43. Their paths and exact cited sections are recorded in the
receipt. No NOAA observation file was newly fetched: the original CloudPhase,
GMTCO and AMI IR105 files above were already present; the full CloudHeight and
DCOMP objects remain unavailable locally and are represented only by the
prior generation-pinned byte-range receipt.

## Graph coverage and fresh-run boundary

The requested query against
`/private/tmp/KDM6AD-pr390-small-diagnostics-20261008/graphify-out/graph.json`
returned generic `footprint`/`native` and VIIRS QA-producer nodes but did not
expose the source-to-consumer timing/observation chain. This note was checked
against the named primary source files and their pinned result JSONs. The
bounded manual semantic fragment is
`graphify-out/pr395-obs-green/semantic.json`; it is not a full graph refresh.
The fresh native run is separate: the observation team has not read its
forecast or certified its target-time `Times`. Use that run's own consumed-
artifact and saved-time receipt when available.

No external model/reanalysis, forecast substitution, candidate change, new
native launch, or RTTOV run was performed for this observation note. The new
native run described above is owned and verified separately.
