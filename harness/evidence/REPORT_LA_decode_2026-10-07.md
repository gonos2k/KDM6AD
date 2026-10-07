# Actual LA thermal-slot decoding

Authoring base: PR #384 merge `ab929dd3`. No external model/reanalysis, new
KDM/RTTOV/model run, or institutional request was made. This is an actual read
of the nine public originals already acquired in PR #382.

[Producer](LA_decode_source_2026-10-07.py), [result](LA_decode_result_2026-10-07.json)
and [receipts](LA_decode_receipts_2026-10-07.zip) bind source/table/input hashes
before and after the full read. Archive aliases were restored to original LA
basenames; bytes and hashes stayed unchanged. Full decoded arrays are retained
locally and reproducible from the public pinned originals; the public packet
contains a deterministic 33-pixel subset, not a claim to contain all output rows.

## Actual output and independent checks

* 250,000 geolocated pixels × nine thermal channels = 2,250,000 channel values.
* All decoded source DQF values are 0; all retained radiances are positive.
* IR105 BT range: 212.82890509757797–302.50418088385965 K.
* Independent integer DN/DQF arithmetic agrees exactly across all pixels.
* An independent log1p Planck expression agrees within 1.14e-13 K.
* Independent ellipsoidal forward projection recovers original scan coordinates
  within 3.28e-11 row / 4.67e-12 column pixels.

These checks establish decoder arithmetic and internal nominal-grid consistency.
They do not establish true cloud phase, actual footprint/pointing, physical
model agreement, calibrated R/bias or forecast skill. IR105 thresholds and good
DQF alone cannot classify a warm-liquid case.

## Contracts corrected before publishing the reader

The dedicated LA module reuses existing DN/DQF and GEOS routines, without
relabelling LA as FD/KO or changing their reader defaults. It is explicitly
limited to complete AMI 8–16 500×500 LA020GE v1.0.0_20181120 scenes, checks the
format/16-bit/two-bit DQF meanings, exact paired calibration and common geometry,
and rejects changing source hashes around both passes. The caller's calibration
table is privately copied. Invalid inputs do not produce an assembled payload.

Real header corners showed NMSC scan coordinates are one-based: array (0,0)
must be projected as scan (1,1). The corrected LA reader retains zero-based
pixel IDs and agrees with the original upper-left/center metadata. Legacy FD
reader indexing remains separately reviewable; no old numerical evidence is
retroactively relabelled by this LA change.

The [official NMSC guide, table on PDF page 20](https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf)
defines scene/filename time as first-swath/packet OBT, and mission reference as
planned UTC. Therefore the reader does not assign a verified UTC to the
observation payload. It preserves the raw OBT, planned UTC, seconds-valued
start/end and synchronization pair with unresolved epoch/conversion. The actual
OBT↔UTC numerical offset and per-pixel scan time are not inferred here.

## Unfinished independent science data

A bounded anonymous Range GET for the known MODIS candidate redirected to
Earthdata Login and returned 401. No science bytes or credentials were used.
[Sanitized access receipt](MODIS_unauthenticated_access_result_2026-10-07.json)
keeps status/host/path and redacts query details. Metadata remains available,
but this science download needs account access. No new phase verification or
time-collocated native model case is claimed.

The original first-acquisition packet is retained unchanged. Source/header
timing assumptions are qualified by this primary-source audit rather than
inventing an observed UTC or replacing missing independent data.

Final local validation: **26 focused passed / 2 retained-input skips**; full
public-only suite **1705 passed / 93 skipped / 51 warnings**. Counts overlap.
No private model/RTTOV/native host run was added. The actual retained LA run
above is separate from synthetic tests. Green/Red checks resolved the timestamp,
format/DQF, pixel-origin and between-pass identity findings before publication.
