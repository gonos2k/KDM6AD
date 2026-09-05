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
placeholders are removed. The radiance and Planck arithmetic is unchanged.

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

On the finite-coordinate domain, SW038 changes from zero usable pixels to
810,000/810,000 in KO and 23,046,116/23,046,116 in FD. Its mean decoded BT
changes from 376.616 to 288.818 K (KO) and 376.458 to 286.776 K (FD).
There are no commonly usable SW038 pixels under the old and new decoders:
these BT differences describe decoded values, not changes to assimilated BT.
Other channels have unchanged DN, QC availability and common-usable BT in
these two finite-coordinate samples. Off-disk DQF=2 also demonstrates the
old quality decoding error; the FD reader's coordinate filter independently
excludes off-disk points. No forecast or assimilation performance is measured.

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
