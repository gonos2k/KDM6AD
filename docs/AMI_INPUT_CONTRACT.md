# AMI L1B word decoding and observation availability

The KO and FD readers decode the two most significant bits of each uint16
word as DQF (`raw >> 14 & 3`). DN occupies the low
`number_of_valid_bits_per_pixel` bits, read from the **image variable**.
The supported counts are 11, 12, 13 and 14. Both unsigned 16-bit byte orders
are accepted. Missing or invalid metadata is
refused; a global calibration attribute cannot override the variable.

NMSC defines uint16 pixels with two quality bits and a variable attribute for
the valid DN width in its [L1B format description, PDF p. 21](https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf).
The [official Satpy AMI reader](https://satpy.readthedocs.io/en/v0.54.0/_modules/satpy/readers/ami_l1b.html)
extracts DQF from the high two bits and DN from this variable attribute.
DQF 0 is good, 1 conditionally usable, 2 outside the scan, and 3 erroneous.
This application's existing QC accepts only 0. NetCDF masks independently
mark pixels unusable, including words whose embedded DQF is zero.

Both sampled KO and FD slots contain the attribute in every channel:

| Channels | Valid DN bits |
| --- | ---: |
| VI004, VI005, NR016 | 11 |
| VI006, NR013, WV063 | 12 |
| VI008, WV069, WV073, IR087, IR096, IR105, IR112, IR123, IR133 | 13 |
| SW038 | 14 |

These are observed metadata values, not fallback defaults. The calibration
JSON contains radiance/Planck coefficients; its former null word-width
placeholders are removed. Positive finite radiances retain the existing
Planck arithmetic and operation order.

## Calibrated radiance domain

A BT observation requires finite, strictly positive calibrated radiance.
`dn_to_bt()` checks this before the inverse Planck calculation. Nonpositive
or nonfinite pixel radiances receive a finite BT=0 placeholder; embedded
DQF=0 becomes 3, while an existing nonzero DQF is preserved. The temporary
positive calculation operand is not a repaired observation. The NetCDF
missing mask separately marks a pixel unusable, as before.

Calibration coefficients must be finite scalars, with positive wavelength
and Planck constants and representable positive Planck factors. A malformed
calibration or a nonfinite or nonpositive BT in kelvin from positive radiance
raises an error instead of treating a file/configuration error as pixel
missingness. This is the physical Kelvin domain, not an empirical temperature
range filter. The BT=0 placeholder for invalid radiance remains unusable.
Negative AMI radiance gains remain valid. KO and FD readers share this boundary.

With the shipped coefficients, synthetic DQF=0 words IR105 `0x1FFF` and
SW038 `0x3FFF` yield negative radiance. They are unusable, even though clipping
their radiance could produce finite, misleading temperatures. Synthetic
NetCDF → payload → collocation → combined mask → Huber tests verify zero
loss gradient for these pixels and retain a valid neighbour's contribution.
This checks input/QC propagation, not a live RTTOV or forecast experiment.

The independent `measure_ami_bits.py` comparison applies this same physical
domain and pixel-QC contract to its current-reader expectation. Its historical
counterfactual retains the old bit extraction and radiance clipping, including
the misleading finite BT from a negative radiance. Those old values describe
the old decoder; they are not current usable observations. Published historical
measurement files retain their original source hashes and results.

The [post-PR209 checklist](../harness/evidence/CHECKLIST_pr209_boundary_resolution_2026-09-06.md)
records the new regression and normal-value checks. Its
[KO/FD production sample](reports/ami_boundary_followup_sample_20260906.json)
compares the updated independent expectation with the current reader at
explicit strides 16/8; it does not replace the historical full-raster evidence.

The [synthetic boundary record](reports/ami_radiance_boundary_20260906.json)
compares the saved PR209 parent decoder at `2f88c4a` with this correction.
All 652,140 positive-radiance words across ten IR channel fixtures retain
BT bits and DQF exactly. Separately, all 524,288 word/width/byte-order
combinations match quotient/remainder expectations for DN and DQF. These
counts enumerate synthetic input space; they are not scene frequencies.

## Regression witnesses

`test_ami_word_contract.py` uses literal words `0x0BB8`, `0x4BB8`, `0x8BB8`,
`0xCBB8`: all have DN 3000 and DQF 0, 1, 2, 3 respectively. It also checks
all four quality values at each supported maximum DN, SW038 `0x3E80`
(DN 16000, DQF 0, BT approximately 284.944 K with the shipped coefficients),
and actual synthetic NetCDF → KO/FD → payload paths with masks, both byte
orders and conflicting global metadata. Missing metadata, duplicate/ambiguous
channels, nonpositive strides and unequal channel grids are rejected. Inputs
must supply packed words; auto-scaled floating-point NetCDF values are refused.

## Measurement scope

Full-raster comparison uses KO `202507190000` and FD `202507190100`, all
16 channels, with file hashes and separate unmasked/finite-coordinate counts.
The historical and corrected decoders operate on the same words and coefficients.
The slots are separate measurements; this is not a KO–FD scene equality claim.
Details are in [the full-raster record](reports/ami_bit_decode_full_raster_summary_20260905.json).
The separate [production-sample verification](reports/ami_bit_decode_20260905.json)
runs both corrected readers on their normal selections: KO stride 16 (3,136
pixels) and FD default ROI, stride 8 (10,350 pixels), ten IR channels each.
DQF and BT match an independent word decoder exactly in those samples. The
coordinate selection and calibration arithmetic are shared; this is an
independent bit-decoding comparison, not an independent geolocation proof.

In that historical bit-decoding-only comparison, on the finite-coordinate
domain, SW038 changes from zero usable pixels to
810,000/810,000 in KO and 23,046,116/23,046,116 in FD. Its mean decoded BT
changes from 376.616 to 288.818 K (KO) and 376.458 to 286.776 K (FD).
There are no commonly usable SW038 pixels under the old and new decoders:
these BT differences describe decoded values, not changes to assimilated BT.
Other channels have unchanged DN, QC availability and common-usable BT in
these two finite-coordinate samples. Off-disk DQF=2 also demonstrates the
old quality decoding error; the FD reader's coordinate filter independently
excludes off-disk points. No forecast or assimilation performance is measured.

### Radiance-domain follow-up, 2026-09-06

A new [20-file full-raster measurement](reports/ami_radiance_full_raster_20260906.json)
compares parent `2f88c4a` and corrected decoder `0e3dbe4`, with the existing
KO `202507190000` and FD `202507190100` ten-IR-channel slots. All input files,
decoder sources, calibration and measurement script have recorded hashes.
NetCDF masks and finite-geolocation domains are counted separately.

KO has no Q0 pixels with invalid radiance. FD SW038 has **243** such pixels
among all 30,250,000 unmasked pixels; **76** are in the 23,046,116-pixel
finite-geolocation domain. All have nonpositive radiance; none is nonfinite.
They become Q3/BT=0. Thus the SW038 domain's usable count changes from
23,046,116 to **23,046,040**; the other nine IR channels do not change QC.
Common usable BTs remain exactly equal (0 K difference, 0 ULP) in all
twenty channel/slot pairs. The historical bit-decoding report is preserved.

This is a full-raster domain count, not the FD production bbox/stride
selection, an assimilated-pixel count, or a forecast-impact measurement.

## Empty input and ownership policy

An empty observation payload produces empty collocation indices/distances
after validating the model grid. Column observations remain unusable with
zero assignments. Upper DA logic retains responsibility for empty-observation
execution decisions. An empty list of channel files is a malformed slot and
is rejected explicitly.

The existing distance-first ownership policy is unchanged: an unusable nearest
pixel can win a column before channel QC. This documented choice is not a
new regression. Quality-aware competition would change observation selection
and requires a separate experiment; this correction adds no reassignment mode.
