# PR400 — actual AMI LA calibration and RTTOV sensor compatibility

## Finding

The nine local AMI LA020GE files for the `202507190556` slot declare calibration table `v.3.0_20190415`. Their headers and all eight stored calibration values match the official NMSC v3.0 workbook exactly. The selected RTTOV setup uses the AMI coefficient file whose embedded README identifies the KMA SRFs delivered in February 2021 and channel 16 `New_AMI_SRF_IR133_-0.80wn.txt`, with the v3.1 shifted IR133 center.

The calibration tuple and RTTOV spectral setup align on physical AMI channels 10–15. **IR133, physical channel 16, is the sole difference:** the actual LA file declares and carries the v3.0 IR133 effective-temperature-to-brightness-temperature polynomial. The v3.1 NMSC workbook lists a revised polynomial, while the RTTOV coefficient uses the shifted v3.1 center wavenumber and documents the KMA shifted SRF. The polynomial delta comes from the NMSC workbook comparison, not from RTTOV metadata. The LA header has no SRF identifier or explicit wavenumber, so it does not establish which IR133 response curve the upstream LA processor used. The evidence therefore establishes a calibration-tuple mismatch and an unresolved upstream SRF payload; it does not establish that the physical sensor response changed or quantify an IR133 BT error.

This check read only NetCDF headers and dimensions. It did not index the image arrays, recompute DN-to-BT arithmetic, run model data, or call RTTOV forward/H. The `rttov_coef_info.exe` invocation inspected coefficient metadata only.

## Actual LA files and official calibration tables

The nine files were already present in the pinned NOAA-GK2A-PDS local slot. The copied slot receipt identifies the `AMI/L1B/LA/202507/19/05/` prefix and contains each original object name, size, and SHA256. All nine local SHA256 values and sizes match that receipt. Each file is a `500×500` AMI LA020GE product, reports `data_processing_center=NMSC`, `data_processing_mode=operation`, and `file_generation_time=20250719_055820`.

Every inspected file declares `calibration_table_version=v.3.0_20190415`. Its DN-to-radiance gain and offset, three `Teff_to_Tbb` coefficients, and shared physical constants exactly match the workbook cells in the official [NMSC v3.0 calibration table](https://nmsc.kma.go.kr/homepage/json/base/bbs/selectAtchFile.do?attachFileUsq=40092&refTbUsq=200057). The downloaded workbook hash is `eb15fa4032322e22a44a0a233451978568a46d5f0eabf783cb9c7212327aa822`.

The [NMSC software and SRF listing](https://nmsc.kma.go.kr/enhome/html/base/cmm/selectPage.do?page=static.utilization.software) lists both that v3.0 workbook and the [v3.1 IR133-shift workbook](https://nmsc.kma.go.kr/homepage/json/base/bbs/selectAtchFile.do?attachFileUsq=40620&refTbUsq=201006), plus the 16-band SRF archive. The v3.1 workbook changes only the IR133 row among the ten IR-band calibration rows: the center wavenumber and the three effective-temperature-to-BT polynomial terms change. The DN-to-radiance gain and offset remain the same. Workbook hashes and the full cell-by-cell comparison are in `SENSOR_COMPATIBILITY.json`.

## Physical channel mapping and spectral limits

NWP SAF lists AMI sensor ID 93 with sensor channels 1–16 mapping to RTTOV channels 1–16 in its [supported-platform table](https://nwpsaf.eu/site/software/rttov/documentation/platforms-supported/). The [AMI SRF channel page](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_gkompsat2_1_ami_srf.html) identifies the channel names and order; the centers below come from the v3.0/v3.1 NMSC workbook rows and the installed coefficient README. SRF limits are the min/max wavenumbers with positive response in the downloaded NMSC curves; they describe published response support, not the channels' RTTOV valid-state bounds.

| RTTOV / AMI channel | Product file channel | v3.0 center (cm⁻¹) | v3.1 center (cm⁻¹) | Installed RTTOV center (cm⁻¹) | NMSC positive-response support (cm⁻¹) | RTTOV flags |
|---:|---|---:|---:|---:|---:|---|
| 10 | WV073 | 1365.249992 | 1365.249992 | 1365.249992 | 1324.6–1408.4 | thermal, Planck weighted |
| 11 | IR087 | 1164.949393 | 1164.949393 | 1164.949393 | 1111.2–1219.5 | thermal |
| 12 | IR096 | 1039.960217 | 1039.960217 | 1039.960217 | 1000.0–1075.2 | thermal, Planck weighted |
| 13 | IR105 | 966.153384 | 966.153384 | 966.153384 | 869.6–1052.6 | thermal |
| 14 | IR112 | 891.713057 | 891.713057 | 891.713057 | 833.3–952.3 | thermal |
| 15 | IR123 | 810.609008 | 810.609008 | 810.609008 | 740.8–875.2 | thermal |
| 16 | IR133 | 753.590621 | 752.792488 | 752.792488 | 722.1–780.1 | thermal |

RTTOV reports the same one-to-one channel order in the `rttov_coef_info.exe` output. The installed coefficient file hash is recorded in the JSON receipt and matches the coefficient hash in the PR399 H plan. It reports creation date 2021-05-03, 16 channels, and RTTOV model version 13; NWP SAF also lists the AMI v13 O3+CO2 coefficient with this creation date on its [v13 coefficient page](https://www.nwpsaf.eu/site/software/rttov/download/coefficients/rttov-v13-coefficient-download/). The executable identifies the coefficient's embedded source as the v3.1 shifted table and the updated SRF package supplied by KMA.

For IR133, the center moves by `−0.798133727 cm⁻¹` from v3.0 to v3.1. The official [NMSC SRF ZIP](https://nmsc.kma.go.kr/homepage/json/base/resources/selectAtchFile.do?attachFileUsq=40587) contains `GK2A_ami_srf_IR133_shift_-0.80wn.txt`; the NWP SAF published channel-16 file names `New_AMI_SRF_IR133_-0.80wn.txt` received from KMA. Their 581 common samples on the 0.1 cm⁻¹ grid agree within `5.04×10⁻⁷` response, under one unit of the NWP SAF file's six-decimal response precision. This supports that the published shifted channel-16 response is the same SRF version described in the RTTOV coefficient README. The coefficient file does not embed a hash of its source SRF payload, so this is documentation plus published-curve agreement, not a byte-level identity proof of the coefficient-generation input.

The NMSC workbook comparison shows the IR133 `Teff_to_Tbb` polynomial changes: v3.0 is `(-0.0938521568527657, 1.00053982112966, -5.94913715312849e-7)` and v3.1 is `(-0.0923380404285149, 1.00052560645485, -5.62764997987650e-7)` for `(c0,c1,c2)`. Its DN-to-radiance gain and offset are unchanged between the tables. These are product-calibration values; they are not RTTOV coefficient fields.

## Interpretation and limits

The 2025 LA products' v3.0 header is supported by the values that the files actually expose. It cannot serve as an SRF version identifier because the files contain no SRF/wavenumber attribute. The v3.1 filename makes the IR133 update explicit, and the installed RTTOV coefficient is explicitly tied to the updated KMA input; that pairing leaves the actual upstream LA SRF payload unresolved despite the product's v3.0 calibration label.

The direct, supported finding is limited to IR133's calibration tuple and spectral-center mismatch. It does not show the upstream product processor's internal SRF selection, any image-level BT error, or how much this one-channel issue contributes to an observation/model residual. The remaining six selected channels have matching table and coefficient centers. Operational files and defaults were not changed.

## Reproduction and evidence files

Run `sensor_compatibility_audit.py` with the private paths and calibration assets recorded in its command provenance. The script reads only the nine headers, the two official calibration workbooks, the official NMSC and NWP SAF channel-16 SRF text, and the installed coefficient metadata utility. Its structured results, input and artifact hashes, per-channel comparison, and full utility transcript are in `SENSOR_COMPATIBILITY.json` and `RTTOV_COEF_INFO.txt`. Canonical private copies of the nine local LA inputs, source listing/receipt, official downloads, and the executed source are under `host/research_evidence/pr400_sensor_compat_20261010/` with restrictive file permissions.
