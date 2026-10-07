# VIIRS candidate context, stored QA correction and actual scan geometry

Base: PR #387 `f0b5060b`. Capture dates in filenames are UTC 2026-10-07;
the work continued into local October 8. Production physics, AD, loss and LA
reader are unchanged by this observation-context change. R2 remains OPEN.

## Correct the QA histogram, preserve the original run

The PR #387 historical producer called `np.ma.filled` on a default NetCDF read
of `CloudPhaseFlag`. Its declared `valid_range=[0,1]` automatically masks stored
packed bytes 3, 5, 9, 13, 17 and others. Those were reported as `-128`, although
the three original arrays contain **zero actual -128 fill bytes**. The selected
pixel's byte 0, phase 1 and nearest-center selection are unaffected.

The [new stored-byte producer](VIIRS_context_source_2026-10-07.py) explicitly
disables automatic masks/scales. It does not invent a new bit decoder. The
[actual result](VIIRS_context_result_2026-10-07.json) separately reports fill,
nonfill values outside the declared range and automatic-mask counts. For the
selected 05:55 granule, 214,771 nonfill stored flags were automatically masked;
the 19,338 `-128` entries in the old native-interior histogram were false fills.
This corrects a receipt/statistics error, not a KDM or RTTOV result. Historical
producer, result and ZIP bytes are retained; use the new context result for
stored QA frequencies. A real NetCDF fixture containing 0,1,5,-128 verifies the
distinction between a range-masked byte and a genuine fill.

## Actual neighborhood and same-overpass products

Around the unchanged VIIRS pixel (row 205, column 27), nominal-center counts are:

| Radius | Centers | Phase codes | Stored QA bytes |
| --- | ---: | --- | --- |
| 1 km | 3 | liquid category: 3 | 0:2, 5:1 |
| 3.5 km | 36 | liquid category: 36 | 0:29, 5:7 |
| 5 km | 75 | liquid category: 75 | 0:66, 5:9 |
| 10 km | 291 | liquid category:288, clear:3 | 0:282, 5:9 |

These are spherical nominal-center counts, not independent samples, physical
footprint areas, categorical means or proof of spatially uniform optical depth.
CloudType at the target is raw code 2, the liquid category in NOAA's ATBD.
Selected diagnostic bytes `[3,-128,8,0,0,0]` are preserved without interpretation.

Generation-pinned GCS byte-range reads obtained actual CloudHeight and DCOMP
values at the same row/column. Geolocation is identical to CloudPhase in all
three products. Only **8,235,094 bytes** were transferred; full Height/DCOMP
granules were not downloaded or full-file SHA verified. Original object
generation, metadata MD5/CRC, offsets, exact Content-Range and each range SHA
are recorded in [the product result](VIIRS_products_result_2026-10-07.json).
[Offline replay](VIIRS_products_replay_2026-10-07.py) reproduced all **36 stored
target values** directly from the cached original HDF5 blocks, with no network.

| Product field | Stored value | Interpretation limit |
| --- | ---: | --- |
| Cloud top height | 587.736938 m | retrieved height; datum/surface-relative meaning not independently fixed |
| Cloud top temperature | 296.570679 K | supports warm cloud-top category, not full-column temperature |
| Cloud top pressure | 940.985229 hPa | same-overpass retrieval |
| Height QA / parameter flags | 0 / `[3,1,1,1,1]` | retain raw values, no whole-case approval |
| DCOMP optical depth | 2.680974 | QA not approved |
| DCOMP effective radius | 113.557320 micrometers | QA not approved; do not adopt as a droplet-size truth |
| DCOMP LWP / IWP | 169.135635 / 169.135666 g/m² | do not sum or infer mixed phase from both output fields |
| DCOMP EQualityFlag | 17 | stored byte exceeds declared 0..6; encoding must be checked before use |

These are linked derived products from one VIIRS overpass with ancillary model
inputs, not three independent truths. Low-layer fields are fill, which does not
prove the absence of another layer. No external model/reanalysis was acquired
or substituted into the current native model.

## Actual geolocation and scan information

The matching NOAA-20 GMTCO original is 33,174,372 bytes, SHA-256
`2a194c417533a1087543cc7a91b1de2a5a6d8d71d1d71e2bfeb1571cc9f8dd0c`.
All valid EDR latitude/longitude values match its geolocation arrays exactly.
The [executed geometry producer/result](VIIRS_geometry_source_2026-10-07.py)
([JSON](VIIRS_geometry_result_2026-10-07.json)) records the actual sensor angles:
zenith **68.926689°**, azimuth **−91.718239°**. The current NOAA SDR Dictionary
Rev L defines azimuth clockwise positive from north. Its Table 2.16.6-2 shows
scan QF1=128 means HAM mirror side B with other status flags zero; scan QF2=0
and pixel QF2=0 are nominal under those definitions. This is a geolocation
quality interpretation, separate from cloud-retrieval QA.

The granule contains 47 actual scans in 48 allocated slots; rows 752–767 are
padded geolocation fill. Documented M-band scan grouping has 16 detector rows:
row 205 is scan index 12, detector 13. The same product records UTC aggregate
beginning 05:55:47.547447 and beginning IET 2131595784547447 microseconds, equal
to StartTime[0]. Integer IET differences yield scan 12 start
**05:56:08.986512Z**, and next scan start **05:56:10.773095Z**. This is a
product-anchored scan bracket, not per-pixel time and not row-linear interpolation.
An absolute 1958-epoch/leap-second conversion was not independently certified.
AMI clock and scan/pixel timing remain unresolved. The earlier granule-interval
overlap is therefore not proof that these selected pixels were simultaneous.

CloudHeight additionally stores parallax coordinates (35.415225983 N,
122.126564026 E), **1,525.19 m** from its nominal point. NOAA's ACHA ATBD uses
relative height `(Zc-Zs)` for this correction; the selected field alone does not
fix that datum. At the documented viewing directions, the flat local-tangent
relative-parallax scale is 2,866.61 m per assumed 1 km cloud height above surface.
Using 587.74 m as that height would give 1,684.81 m, conditionally. These are
scale/consistency diagnostics: no AMI correction, actual cloud displacement,
common footprint or model-column reassignment was applied.

## Next case step and evidence

The independent science/read and actual geolocation/scan steps are demonstrated.
Warm single-layer/nonprecipitating structure, detailed retrieval QA, AMI timing,
footprint and the target-time native atmosphere remain open. A separately
isolated host experiment is being built/checked; it is not part of this
observation receipt's completion evidence. No forecast/analysis skill, calibrated
sigma/bias or full physical budget follows from these reads.

The raw range and geolocation subsets, source capture and source-document
manifests are in [the receipt packet](VIIRS_context_receipts_2026-10-07.zip).
Full GMTCO/CloudPhase originals stay local and their official URLs/SHA are
recorded. Code graph and bounded document semantics are refreshed; source and
raw receipts are authoritative. Verification is the real stored-byte producer,
real full-GEO producer, 36-value cached HDF5 replay and the targeted mask fixture.
No KDM/RTTOV, full oracle or native forecast is claimed by this packet.

Primary sources: [NOAA cloud-type ATBD v3.0](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_CldType_v3.0.pdf)
Tables 30–32; [VIIRS SDR Dictionary Rev L](https://nesdis-prod.s3.amazonaws.com/2024-01/474-00448-02-06_JPSS-VIIRS-SDR-DD-Part-6_L.pdf)
pp.142 and 204–206; [NOAA ACHA ATBD v3.4](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_ACHA_v3.4.pdf)
pp.39 and 42; [NOAA JPSS access](https://www.star.nesdis.noaa.gov/jpss/DataAccess.php).
