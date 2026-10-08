# First observation collection — warm liquid first, mixed phase in parallel

No pre-existing internal calibration sample exists. Keep diagnostic 1 K and
zero bias as the regression reference; caller-fixed alternatives are declared
assumptions, not calibrated R/B or sensor corrections. Observations may be
collected publicly, but external model/reanalysis profiles are not acquired or
substituted for the current native 5 km model.

| Step | Completion condition | Current evidence / status |
| --- | --- | --- |
| 1. Separate data roles | Sensor calibration, independent atmosphere/cloud observations, and new model–observation pairs have distinct roles | DONE — roles below and packet metadata |
| 2. Locate actual public files | Granule IDs, intervals, footprint metadata, access outcomes and hashes | DONE for a bounded first search; not a complete seasonal catalogue |
| 3. Acquire a small raw observation subset | Original bytes, hashes, original metadata and missing-field declarations | PARTIAL — AMI LA originals, four Anmado sounding records and actual NOAA-20 VIIRS CloudPhase originals; MODIS/EarthCARE science files not acquired |
| 3a. Decode the acquired LA slot | Ordered BT/DQF/radiance/nominal GEOS positions and original pixel indices from the unchanged files | DONE within the retained nine-channel 500×500 format — REPORT_LA_decode_2026-10-07.md; no actual UTC/phase/model match |
| 4. Read independent cloud science QA | Verify liquid/ice/mixed phase, layering, uncertainty and precipitation contamination | PARTIAL — VIIRS phase codes/raw QA actually read and NOAA meanings documented; selected liquid-category candidate, QA packing/vertical structure/contamination remain unapproved |
| 5. Establish pixel/time/footprint correspondence | Actual scan time, geometry, surface and independent profile location checked | PARTIAL — actual native-grid and nearby AMI nominal centers identified; UTC/scan/footprint/parallax remain open |
| 6. Produce corresponding native model states | Same current 5 km model's center/interface pressure, T/Q/hydrometeors preserved at observed time | OPEN — retained C5 output ends at 00:00:40 UTC. Satpy v0.57.0 yields a conditional naive 05:34:42–05:35:43 calendar interval from numeric header seconds, but UTC, pixel time and correspondence remain unverified; see [LA time-contract audit](REPORT_LA_time_contract_2026-10-07.md) |
| 7. Complete first research bundles | Warm-liquid acceptance first; cold-season availability collected in parallel for one or two ice/mixed-phase cases | OPEN — three warm-liquid cases are not phase-verified; Nov 2025–Mar 2026 search not performed |
| 8. Accumulate residuals and uncertainty | Sensor bias separate from O–B; event-level design/validation separation; unresolved components labelled | OPEN — no sigma/bias fit from these metadata |

Sensor calibration data: official AMI calibration/SRF/processing records and
GSICS. The downloaded LA header declares v3.0; that does not prove the local
KO/ELA processing lineage or IR133 SRF compatibility. Independent cloud/air
data: MODIS/EarthCARE and soundings. New model–observation pairs: still absent
until steps 4–6 complete. No alternative observation substitutes silently for
the retained KO scene.

## Actual first shortlist

NASA CMR intersects these swaths with bbox 120–135 E, 30–42 N. This is a broad
search filter, not a pixel match or a claim that the current model covers the
whole box. Collection 6.1 originals and exact CMR footprint polygons are in the
[receipt packet](FIRST_observation_inventory_receipts_2026-10-07.zip).

| MODIS producer granule ID | UTC observation interval | Metadata day/night | Role |
| --- | --- | --- | --- |
| MYD06_L2.A2025091.0535.061.2025091220356.hdf | Apr 1 05:35–05:40 | DAY | Phase/QA screening candidate |
| MOD06_L2.A2025200.0045.061.2025205141805.hdf | Jul 19 00:45–00:50 | DAY | Phase/QA screening candidate; 44m20s after retained final frame |
| MOD06_L2.A2025263.0110.061.2025263203907.hdf | Sep 20 01:10–01:15 | DAY | Phase/QA screening candidate |
| MOD06_L2.A2025263.1215.061.2025264014149.hdf | Sep 20 12:15–12:20 | NIGHT | Contrast candidate; solar optical retrieval availability differs |

CMR metadata was retrieved anonymously. Four unauthenticated data-link HEAD
probes returned 403 after redirection; this alone does not identify an account,
method or service-policy cause. No MODIS science granule or cloud QA was read.

ESA MAAP EarthCARE catalogue candidates intersecting East-Korea bbox 126.5–130 E,
34–39.5 N include 06469B (Jul 18 16:51:45–17:03:32) and 06477D
(Jul 19 05:34:57–05:46:44). ESA/JAXA L1/L2 product records exist in the packet.
These orbit intervals do not mean all instruments have valid measurements or
all footprint pixels intersect the model domain. In particular, the frame
start timestamp is not the time the descending track reaches Korea; exact
sample times are unavailable from these catalogue polygons. The queried C5 neighborhood
122.8–124.2 E, 38–39.4 N returns zero items for Jul 18–20 in the tested collections;
do not extend that negative result to all dates or the whole mission.

Nine actual NOAA LA thermal originals were acquired (AMI 8–16): eight new
downloads plus the reused IR105 sample, totaling 4,414,025 bytes. Every file was
size-checked and SHA-256 pinned. All nine headers
report the same scene string, calibration version and GEOS 500×500 grid. At the
PR #382 acquisition stage, no image pixels or DQF bits were read. The subsequent
explicit LA read is recorded separately below. The earlier
IR105 receipt preserves a header-reported error-pixel count, which is distinct
from independently inspecting pixel DQF. The IR105 example is:
`AMI/L1B/LA/202507/19/05/gk2a_ami_le1b_ir105_la020ge_202507190534.nc`,
531,907 bytes, SHA-256
`49ed9109637c68465c3d19938b0c794092dcb50b92afb7105ce0d687803789ce`.
Its scene acquisition string is **05:34:42 OBT**, and its header declares LA, GEOS,
500×500, 2 km and KMA calibration v.3.0_20190415. Scene time and the EarthCARE
interval are calendar-label candidates only; OBT has not been converted to UTC.
Pixel DQF is now decoded, but cloud phase and joint footprint remain unverified.
Exact ELA prefixes returned
zero objects in the bounded queries; LA availability does not certify KO/ELA.

Anmado `KSM00047269` (35.3469 N, 126.0305 E) has four acquired raw sounding
records for nominal Jul 19 00/06/12/18 UTC, totaling 534 levels. Preserve the
separate release HHMM (2319/0519/1119/1719); the provider-dependent release date
has not been inferred. Temperature/humidity QC and ascent drift remain open.
The station is about 440 km from the retained C5 center, so these are available
observations, not a collocated C5 reference profile. The full station archive
stays local; the packet contains only this day's extract and archive hash/CRC.

## Official sources and reproducibility

The [manifest](FIRST_observation_inventory_manifest_2026-10-07.json) pins each
packaged response, raw subset, header record and query script. No credentials
were supplied, no institution was contacted and no external model was acquired.
Metadata/header inspection is separate from science validation. Existing
native/KMA arithmetic and closed PR #370–#379 evidence remain unchanged.

* [NASA CMR search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)
* [NOAA GK2A public objects](https://noaa-gk2a-pds.s3.amazonaws.com/)
* [ESA MAAP EarthCARE STAC](https://catalog.maap.eo.esa.int/catalogue/)
* [JAXA EarthCARE product list](https://www.eorc.jaxa.jp/EARTHCARE/data/prd_list_e.html)
* [JAXA CPR operational status](https://www.eorc.jaxa.jp/EARTHCARE/data/operational_status_e.html)
* [G-Portal support and October 2026 CSW/SFTP change](https://www.gportal.jaxa.jp/information/support)
* [NOAA IGRA source and limitations](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive)

Next: obtain a small independent cloud science subset and read QA, then solve
pixel/time/footprint correspondence. Choose actual verified regimes before
expanding model runs or fitting conditional error candidates. A missing cloud
QA field stays unknown; IR105 above 270 K is not proof of clear sky or liquid.

## Unfinished parts of the same observation-case task (R2)

These are concrete substeps of the existing user plan, not new approval gates.

| Detail | Current evidence | Remaining work |
| --- | --- | --- |
| LA ingestion | Dedicated LA reader decoded all nine unchanged originals; BT/DQF and one-based GEOS/header anchors verified | Actual UTC/scan-time interpretation and science/model correspondence remain open; legacy KO/FD contracts are not silently changed |
| Calibration and response | Decoder coefficient table and header version agree | Original SRF/processing identity and GSICS files not acquired; IR133 response compatibility remains S11 work |
| Independent water/phase | MODIS/EarthCARE catalogues; actual NOAA-20 VIIRS phase/raw QA now read | Full QA semantics/vertical phase approval remain open; independent LWP still unacquired |
| Cold-season availability | Current searches cover summer candidates | Nov 2025–Mar 2026 ice/mixed-phase search not performed; parallel collection is planned, not completed |
| Pixel time and model time | Pinned Satpy source gives a conditional naive calendar interval from LA numeric seconds; reader keeps `valid_time_utc=None` | Still open: establish numeric epoch/clock semantics, actual AMI scan/pixel time, footprint and matching native model state; see [LA time-contract audit](REPORT_LA_time_contract_2026-10-07.md) |

The official NMSC metadata guide identifies scene/filename time as OBT and
mission reference time as planned UTC. New LA outputs preserve these roles and
leave `valid_time_utc` unset. Earlier filename labels/15-second nominal differences
must not be read as verified simultaneous UTC samples. Existing KO/FD filename-
time and FD pixel-coordinate conventions need separate verification before
physical matching; historical numerical receipts remain unchanged.

## First actual independent science execution

[VIIRS/native candidate report](REPORT_VIIRS_native_candidate_2026-10-07.md):
official Google/Azure copies provide the Jul 19 VIIRS CloudPhase originals even
though checked AWS 2025 prefixes are empty. The 05:55:47–05:57:10 UTC granule has
a raw code-1/QA-0 marine candidate near native (j=86,i=48), and a newly decoded
AMI LA 05:56 nominal center is nearby. This is not the old LA 05:34/MODIS 00:45
pair. Product QA and actual pixel times/footprints remain required. Target-time
native states were subsequently saved, but their long-run launcher exited 1:
see the [target artifact report](REPORT_native_target_artifact_2026-10-08.md).
Saved states now exist; a valid native experiment and scientific correspondence
remain unconfirmed. The earlier 00:00:40 C5 limitation describes the pre-target
capture, not the current saved-state inventory.
