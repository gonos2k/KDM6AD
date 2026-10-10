# PR402 independent input availability and physical scope

Retrieved 2026-10-11. This is an observational-source and definition check for the case centered at 35.41566 N, 122.14331 E. The native model frame is labeled 2025-07-19 05:56 UTC; the GK2A AMI source filename is stamped `202507190556`, while its per-pixel UTC has not been verified. This note does not run a model or retrieval, acquire model/reanalysis inputs, or infer an observation from residuals.

## What is verified

- The retained observation packet has a GK2A AMI 5x5 brightness-temperature patch and VIIRS descriptive patch. It records the AMI center at 35.41925069 N, 122.13724165 E, but explicitly marks per-pixel UTC and physical matchup approval unverified. The packet says no new observation was acquired. Source: `harness/evidence/pr398_spatial_representativeness_2026-10-10/OBSERVATION_PATCH.json`.
- A narrow NASA CMR query for NOAA-20 STAR VIIRS GHRSST L2P over 2025-07-19 05:30–06:30 UTC and 121.8–122.5 E, 35.2–35.7 N returned granule `20250719055000-STAR-L2P_GHRSST-SSTsubskin-VIIRS_N20-ACSPO_V2.80-v02.0-fv01.0`, nominal 05:50–06:00 UTC. The catalog polygon spans the queried case area. This verifies an archived candidate swath and its granule-time/footprint metadata only. It does not verify a non-fill SST sample at the native point, the pixel acquisition time, clear-sky/quality flags, or a collocated independent SST value. The query did not download the granule.
- NASA CMR returned daily Aura MLS V005 granule metadata for both ozone (`ML2O3.005:...2025d200.he5`) and temperature (`ML2T.005:...2025d200.he5`). These daily files have global catalog boxes, so those metadata hits do not prove that an MLS profile is near the point at the relevant time. An unauthenticated OPeNDAP metadata request returned HTTP 401; no profile records, geolocation, retrieval quality, or sensitivity data were read.
- The retained IC/BC audit identifies the current REAL_EM-labeled IC and BC files, but says the meteorological provider and original preprocessing lineage are unverified. The only other-date `met_em` candidates documented there are from 2023-02-16 and are not independent native cases for this July 2025 event. Local inventory does not establish that no original archive exists. The original provider/path request is already outstanding; this scope check does not repeat it. Source: `harness/evidence/pr400_input_compatibility_2026-10-10/IC_BC_LINEAGE.json`.

## Independent SST: physical match needed

The saved native sea-point `TSK` is 300.77423 K. It is a model surface skin state, not a measured SST reference. GHRSST distinguishes infrared skin temperature (roughly the top 10–20 micrometres), microwave subskin temperature, in-situ temperatures at stated depth, and foundation temperature with diurnal variability removed. A nominal NOAA-20 VIIRS L2P granule found by CMR is explicitly an SST-subskin product. Its measurement type therefore must be stated; a subskin value should not silently be called skin or foundation SST. A defensible matchup needs actual valid sample value, actual pixel time and coordinates, quality/clear-sky flags, uncertainty, and the spatial/time representativeness rule. If comparing to the model skin state, either select a skin retrieval or explicitly model/justify the skin-to-subskin relationship. A buoy/in-situ value must retain instrument depth and time and cannot be relabeled skin SST.

GHRSST's product guidance also cautions that infrared products are cloud-obscured, microwave products approximate subskin and have reduced spatial resolution and coastal limitations, and L4 analyses blend observations. The retrieved candidate is near the model point but pixel-level validity and representativeness remain unconfirmed. No independent SST value is available in the inspected packet.

## Upper-air temperature and ozone: profile, time, and sensitivity

A column total cannot validate a vertical profile perturbation. For an independent ozone comparison, require a retrieved O3 profile with native retrieval pressure coordinates, geolocation and observation time, quality/status flags, uncertainty, and averaging-kernel/prior or other vertical-sensitivity information. For temperature, require equivalent profile-level metadata and vertical sensitivity, plus the valid pressure range. Review the actual 39 native model levels and the 27 RTTOV reference levels above the native model top as distinct vertical regions. The 27 upper reference levels remain in scope wherever the retrieved profile's useful range and vertical sensitivity support them; do not exclude the target region solely because it lies above the native model top. Keep these upper reference levels distinct from native model states, and use the retrieved pressure coordinates and averaging-kernel/sensitivity information to determine which levels the observation constrains. Do not treat the fixture's 69 reference levels as observed atmospheric levels.

The archived candidates are Aura MLS V005, so version-matched V5.0x Level-2/3 quality and description guidance is the relevant reference for screening, useful ranges and product sensitivity. The current MLS data page provides a V5 averaging-kernel link, but its displayed useful-range table may reflect the current product release; no V6 range or QA threshold is silently applied to these V005 candidates. The official V5.0x quality document is linked below; version-matched per-profile QA remains unconfirmed because no profiles were retrieved. Its V005 daily granules exist for the event date, but this metadata-only inspection could not establish a profile at the native column or the 27-level upper reference region at a time suitable for matchup. NOAA's NUCAPS standard product is another profile source: its retrieved variables include atmospheric vertical temperature and trace-gas ozone profiles sampled at 100 pressure points from 1100 to 0.016 hPa. Those grid points alone do not imply 100 independent vertical degrees of freedom; retrieval sensitivity, quality, geolocation and time must be inspected.

The current 69-level fixed O3/CO2 profiles and 27-level upper-temperature perturbation are fixture inputs used in the existing RTTOV sensitivity evidence. They can expose response to those inputs, but they are not independent observations and do not validate their profile values. No observation-derived O3 or temperature profile was found in the referenced packet.

## Minimum data needed to close the availability gap

1. For the NOAA-20 candidate: pixel/subset SST, pixel time and geolocation, quality and cloud flags, SSES uncertainty, and a declared skin/subskin comparison method.
2. For O3 and temperature: a profile record with actual observation time and coordinates near the native column, pressure levels, product version, quality/status, uncertainty, and vertical averaging-kernel/sensitivity information. Report any levels outside the 39-level native model separately.
3. For independent native cases: the already-requested original IC/BC provider archive and preprocessing/cycle lineage, including immutable source identities/hashes and enough inputs to reproduce a separate native case. This remains unknown here; no alternate GFS/ERA5 source is proposed or acquired.

## Primary sources and query records

All links were retrieved 2026-10-11.

- GHRSST SST measurement definitions and product selection: https://ghrsst.org/ghrsst-data-services/for-sst-data-users/products/
- GHRSST L2P product form, per-observation uncertainty and quality fields: https://ghrsst.org/ghrsst-data-services/for-sst-data-users/products/
- NASA CMR collection query for GHRSST/POCLOUD: https://cmr.earthdata.nasa.gov/search/collections.json?keyword=GHRSST&provider=POCLOUD&page_size=100 (collection `VIIRS_N20-STAR-L2P-v2.80`, CMR `C2147478146-POCLOUD`; collection summary identifies native-resolution NOAA STAR ACSPO VIIRS L2P and quality layers)
- NASA CMR narrow case-area granule query: https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C2147478146-POCLOUD&temporal=2025-07-19T05:30:00Z,2025-07-19T06:30:00Z&bounding_box=121.8,35.2,122.5,35.7&page_size=20
- NASA PO.DAAC candidate granule metadata, OPeNDAP link and browse assets: https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C2147478146-POCLOUD&temporal=2025-07-19T05:30:00Z,2025-07-19T06:30:00Z&bounding_box=121.8,35.2,122.5,35.7&page_size=20
- NASA Aura MLS Level-2 data and product-specific ranges/quality guidance: https://mls.jpl.nasa.gov/eos-aura-mls/data.php
- NASA Aura MLS V5.0x Level-2/3 Quality and Description Document (version-matched guidance for the V005 archived candidates): https://mls.jpl.nasa.gov/data/v5-0_data_quality_document.pdf
- NASA Aura MLS documentation/version index (V5 and V6 documents are listed separately): https://mls.jpl.nasa.gov/eos-aura-mls/documentation.php
- NASA CMR daily MLS O3 granule query: https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C1729925806-GES_DISC&temporal=2025-07-19T05:00:00Z,2025-07-19T07:00:00Z&bounding_box=120,34,124,37&page_size=20
- NASA CMR daily MLS temperature granule query: https://cmr.earthdata.nasa.gov/search/granules.json?collection_concept_id=C1729926922-GES_DISC&temporal=2025-07-19T05:00:00Z,2025-07-19T07:00:00Z&bounding_box=120,34,124,37&page_size=20
- NOAA NESDIS NUCAPS vertical temperature and ozone profile product description: https://www.star.nesdis.noaa.gov/jpss/soundings.php
- NOAA CrIS/ATMS vertical-profile context and cloud limitations: https://www.nesdis.noaa.gov/our-satellites/currently-flying/joint-polar-satellite-system/cross-track-infrared-sounder-cris
- NOAA iQuam in-situ SST monitor: https://www.star.nesdis.noaa.gov/socd/sst/iquam/

The CMR records establish catalog metadata availability only. Actual profile/sample availability remains unconfirmed where stated.
