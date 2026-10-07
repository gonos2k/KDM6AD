# First independent cloud science: VIIRS and an actual native-grid candidate

Base: PR #386 `e4f870359dfdd0c7ba44384b42f0741211c22022`.
This step reads independent observation science, not another arithmetic replay.
No production physics, AD, observation loss, LA decoder or private host source
was changed. No native forecast or RTTOV was run.

## What was acquired and executed

NOAA's [JPSS access page](https://www.star.nesdis.noaa.gov/jpss/DataAccess.php)
names the Google Cloud NOAA-20 bucket; the
[NOAA registry](https://registry.opendata.aws/noaa-jpss/) also lists the Azure
container. The exact `VIIRS-JRR-CloudPhase/2025/07/19/` prefix contains 1,013
objects in each of those copies, while the three checked AWS 2025 prefixes are
empty. An AWS-only access conclusion would therefore have missed a usable
official route. Raw listing responses and individual download hashes are retained
in the receipt packet. No credentials or external model/reanalysis were acquired.

Six bounded original NOAA-20 VIIRS CloudPhase files were downloaded (50,012,707
bytes total). Three missed the broad native-domain rectangle. The three 05:54–05:58
files were actually read: geolocation, CloudPhase, raw CloudPhaseFlag and coverage
times. They each contain 768×3,200 samples. The native candidate producer pins all
three complete original hashes and the existing native IC SHA-256, then reads
only `XLAT`, `XLONG`, `XLAND` and `Times` from that IC.

The IC array order is **south_north=282, west_east=234**; the advertised horizontal
grid is nx=234, ny=282. A rectangle overlap is not accepted as native coverage:
unit-sphere nearest native centers must be within 3.5 km and ten cells from the
edge. This is a nominal candidate screen, not a footprint/parallax operator.

The [executed native result](VIIRS_native_candidate_result_2026-10-07.json) is
produced by [the pinned offline source](VIIRS_native_candidate_source_2026-10-07.py).
Selection is predeclared: phase code 1, raw QA byte 0, native `XLAND=2`, the
distance/edge screen above, then minimum center distance. It does not use BT
residuals or a desired model outcome.

| Selected quantity | Actual value |
| --- | --- |
| VIIRS original | `JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc` |
| Original SHA-256 | `7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2` |
| Granule UTC coverage | 2025-07-19 05:55:47–05:57:10Z; not a pixel timestamp |
| VIIRS row, column (zero based) | 205, 27 |
| VIIRS nominal latitude, longitude | 35.4156379699707 N, 122.14338684082031 E |
| Native j, i (zero based) | 86, 48 |
| Native nominal latitude, longitude | 35.4156608581543 N, 122.143310546875 E |
| Spherical center distance | 7.367358700618518 m |
| Phase / raw QA | 1 / 0; candidate screening only |

This is a western-domain marine candidate, not the historical C5 or a peninsula
subbox match. The independent instrument is VIIRS; its derived cloud retrieval
uses ancillary GFS/CMC SST according to the original file. Those ancillary models
were not downloaded or substituted into KDM6AD. Sensor independence does not
make this retrieval an independent physical truth or eliminate algorithm errors.

## Phase and quality interpretation

NOAA's [ATBD v3.0](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_CldType_v3.0.pdf),
Table 31, printed p.74, maps 0 clear, 1 liquid (>273 K category), 2 supercooled,
3 mixed, 4 ice and 5 undetermined due to bad input. These are cloud-top retrieval
categories: code 1 does not prove an entirely warm, single-layer native column.
Table 32 p.75 defines six high/low quality flags. The
[external users manual](https://www.star.nesdis.noaa.gov/jpss/documents/UserGuides/JPSS_RR_EUM.pdf)
Table 1-10 describes a 3-D byte field with range 0–1, matching the actual
`CloudPhaseFlag` shape `(768,3200,1)`. Other product-family documentation calls
it packed. Preserve byte 0 and fill -128 without inventing bit indexing; full
packing/version semantics and scientific QA approval remain open. Neither a
granule flag nor the candidate's zero byte closes that question.

## A new AMI slot was read near the candidate

All nine unchanged LA 05:56 originals were acquired (4,415,402 bytes). The
existing production `read_la_slot` decoded all 250,000 positions × nine channels,
preserving DQF, original indices and time roles. The
[executed AMI result](VIIRS_AMI_candidate_result_2026-10-07.json) and its
[source](VIIRS_AMI_candidate_source_2026-10-07.py) pin the input/decoder/calibration
identities. No duplicate decoder or new coordinate convention was introduced.

The nearest AMI raster point is row 320, column 48 at
(35.41925069326254 N, 122.13724164654832 E), **686.6436228761686 m** from the VIIRS
nominal center. IR105 is **291.3025921545636 K**; all nine selected DQFs are 0.
These are actual decoded values, not a claim of common footprint or cloud truth.

The raw LA scene label is 05:56:56 OBT. Under the already documented Satpy noon
epoch assumption, its naive interval is 05:56:56.171461–05:57:56.016143. If those
conditional values were UTC, the interval would partially overlap the VIIRS
granule interval; this does not establish time correspondence. AMI UTC/clock semantics and both pixel
times remain unverified; no row-linear scan time was fabricated. The original
LA 05:34 slot and MODIS 00:45 granule remain separate historical/candidate records.

## Native run preparation and the remaining case work

The active private `share/set_timekeeping.F:212–259` confirms positive `run_*`
duration overrides `end_*`. The existing three-hour configuration cannot be
relabelled as reaching this candidate. The current IC and 00/03/06/09 BC records
cover a proposed six-hour window; this is time coverage, not executed stability.

Also distinguish the older dirty canonical/private wrapper from current public
capabilities. Its active `host/KIM-meso_v1.0/phys/module_mp_kdm6ad_cons.F:316`
(`mp337`, inspected in the canonical tree at HEAD `0aa2c30` with local changes)
explicitly selects conservative physics variant 1;
that label alone does not request normalized variant 2/dry number. Current public
`libtorch/bridge/kdm6_c_api.h:156` at this public base supports normalized physics
variant 2, independently of ABI version 2, and line 212 contains the `dry_number` tail.
A future isolated host build/run must explicitly identify wrapper, binary,
linked library and policy. Public ABI support does not certify an existing
private executable, and no default or historical run was changed here.

| Existing R2 substep | Status after this execution |
| --- | --- |
| Independent science file acquisition/read | Completed for the bounded VIIRS files; authentication is not a global blocker |
| Native nominal position candidate | Demonstrated on actual curvilinear geometry, not only a bounding rectangle |
| Nearby AMI original/BT/DQF read | Demonstrated using the unchanged LA reader |
| Product QA / warm single-layer classification | Partial; full QA version semantics and vertical evidence missing |
| Actual scan UTC, footprint and parallax | Open |
| Target-time native pressure/T/Q/hydrometeors | Open; initial IC geometry is not a 05:56 atmospheric state |
| First scientific comparison / calibrated sigma and bias | Open |

Keep R2 open. Next, resolve the recorded QA/time/footprint assumptions for this
one candidate and produce its target-time state with an explicitly pinned
isolated native configuration. Initial exploratory comparisons may retain
1 K/zero bias and declared timing uncertainty; they must not be called calibrated
or a verified simultaneous correspondence. Do not reopen closed numerical results.

## Replay and coverage

Native producer: Python 3.10.11, NumPy 2.2.6, SciPy 1.15.3, netCDF4 1.7.4 in a
separate small environment. AMI producer uses the existing research environment
and production reader. Both real producers completed. Inputs were hash checked
around the reads. Green/Red reviewed consistency and independent distance evidence.
Red identified a 2.1 cm reporting difference caused by float32 trigonometry;
the producer now promotes geolocation before trigonometry, and both receipts
were rerun. The candidate cell did not change. This is not sensor accuracy.
Independent double Haversine gives 7.367358700549504 m at the same cell. Both
source/result SHA bindings were checked; all 23 receipt ZIP members pass CRC,
and all 22 payloads listed in its manifest pass SHA-256 checks.
No original MODIS/EarthCARE science file, KDM/RTTOV, native forecast, C++ build or
full oracle suite was executed in this step; existing CI is separate evidence.

Raw official responses, downloaded AMI originals, a small original VIIRS science
window and manifests are in [the receipt packet](VIIRS_native_candidate_receipts_2026-10-07.zip).
Complete VIIRS originals stay local and can be retrieved from the exact public
URLs and hashes in the native result. Native IC remains private, required for
full geometric replay. A public observation subset is not a substitute model input.

Replay after retrieving the three public originals and access to the unchanged
private IC (use new output paths):

```sh
python harness/evidence/VIIRS_native_candidate_source_2026-10-07.py \
  --originals /path/to/VIIRS-originals --native-input /path/to/wrfinput_d01 \
  --output /new/path/native_candidate.json
python harness/evidence/VIIRS_AMI_candidate_source_2026-10-07.py \
  --ami-dir /path/to/AMI_0556 --candidate /new/path/native_candidate.json \
  --output /new/path/ami_candidate.json
```

The first command needs NumPy/SciPy/netCDF4; the second needs the existing oracle
Python dependencies including Torch. It rejects existing outputs. The current
graph was structurally refreshed, with a bounded semantic update for these
case/checklist documents; source and actual receipts remain authoritative.
