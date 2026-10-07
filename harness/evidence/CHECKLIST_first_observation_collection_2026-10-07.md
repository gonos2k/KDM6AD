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
| 3. Acquire a small raw observation subset | Original bytes, hashes, original metadata and missing-field declarations | PARTIAL — nine AMI LA thermal originals and four Anmado sounding records; MODIS/EarthCARE science files not acquired |
| 4. Read independent cloud science QA | Verify liquid/ice/mixed phase, layering, uncertainty and precipitation contamination | OPEN — every candidate's phase remains unknown |
| 5. Establish pixel/time/footprint correspondence | Actual scan time, geometry, surface and independent profile location checked | OPEN — bbox/scene overlap alone is insufficient |
| 6. Produce corresponding native model states | Same current 5 km model's center/interface pressure, T/Q/hydrometeors preserved at observed time | OPEN — retained output ends 00:00:40; new candidate window is 05:34 |
| 7. Complete first research bundles | Three verified warm-liquid cases, then one or two ice/mixed-phase cases | OPEN — seasonal dates and day/night are not phase labels |
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
all footprint pixels intersect the model domain. The queried C5 neighborhood
122.8–124.2 E, 38–39.4 N returns zero items for Jul 18–20 in the tested collections;
do not extend that negative result to all dates or the whole mission.

Nine actual NOAA LA thermal originals were acquired (AMI 8–16): eight new
downloads plus the reused IR105 sample, totaling 4,414,025 bytes. Every file was
size-checked and SHA-256 pinned. All nine headers
report the same scene string, calibration version and GEOS 500×500 grid; no
image pixel array was read and no DQF bits were decoded or counted. The earlier
IR105 receipt preserves a header-reported error-pixel count, which is distinct
from independently inspecting pixel DQF. The IR105 example is:
`AMI/L1B/LA/202507/19/05/gk2a_ami_le1b_ir105_la020ge_202507190534.nc`,
531,907 bytes, SHA-256
`49ed9109637c68465c3d19938b0c794092dcb50b92afb7105ce0d687803789ce`.
Its scene acquisition is **05:34:42**, and its header declares LA, GEOS,
500×500, 2 km and KMA calibration v.3.0_20190415. Scene time and the EarthCARE
interval are promising correspondence metadata; no specific AMI pixel QA,
cloud phase or joint footprint has been inspected. Exact ELA prefixes returned
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
