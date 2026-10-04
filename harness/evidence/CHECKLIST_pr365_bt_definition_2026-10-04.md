# PR #365 BT-definition follow-up

Baseline: `dd7bbc68fd3179b7ebf4c5f2e4ace37af539045b`.
Fix the calculation-coordinate pairing, not a fitted observational bias. Existing
NCCN, first-order density, output precision and IR105 transport closures stay closed.

- [x] Reproduce the same-radiance discrepancy and preserve its original records.
- [x] Locate the official KMA coefficient/wavenumber pair, not only a channel name.
- [x] Audit all ten retained IR coefficient bundles and the IR133 version difference.
- [x] Correct shipped BT parameters and KO/FD consumption while preserving DN,
  radiance gain/offset, polynomial, quality bits and NetCDF missingness.
- [x] Refuse unpaired FD metadata; preserve explicit legacy/custom wavelength maps.
- [x] Re-express stored model/observation radiances together and transform the JVP.
- [x] Check actual retained KO and a separately labelled archived FD reader boundary.
- [x] Retain original calibration, results and scientific approval status.
- [ ] S11 physical closure: establish the actual observation/SRF epoch pairing,
  footprint/time target, bias/error policy and independently supported accuracy.

## Source decision

The official [KMA calibration page](https://nmsc.kma.go.kr/enhome/html/base/cmm/selectPage.do?page=static.utilization.software)
provides v3.0 and the later IR133-shift v3.1 workbooks.
In v3.0, sheet `coeff.& equation_WN` rows 13–22 pair center wavenumber in column C
with gain/offset D/F and Teff polynomial I:K. All ten retained gain/offset/poly
bundles and shared h/c/k match this table exactly. The old nominal labels are
preserved as metadata, not used as the paired calculation coordinate.

For IR105, C19 is **966.153383926055 cm⁻¹**, paired with the existing polynomial.
The same value appears in the [NWP SAF AMI SRF description](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_gkompsat2_1_ami_srf.html).
Its band corrections are computed by RTTOV and are not the KMA quadratic.
The [Satpy file-mode source](https://satpy.readthedocs.io/en/v0.54.0/_modules/satpy/readers/ami_l1b.html)
likewise uses a configured calculation wavelength with the file's polynomial;
its rounded channel centers are supporting context, not replacements for the workbook.

IR133 retained coefficients match **v3.0, 753.590621482278 cm⁻¹**. The installed
RTTOV file instead references shifted v3.1, **752.7924878 cm⁻¹**, with different
band coefficients. The update does not mix that center with the old polynomial
or silently switch the observation SRF. The deleted 2025 FD originals cannot be
rechecked for calibration/SRF version; numeric tuple matching is not epoch certification.
[Pairing receipt](AMI_calibration_pairing_receipt_2026-10-04.json) pins URLs,
workbook hashes, cells and the limits of a distinct 2023 FD metadata witness.

## Small decoder change

`bt_wavenumber_cm1` is an explicit positive finite numeric scalar; multiplication
by 100 converts it to m⁻¹ for inverse Planck. The shipped table supplies the audited
pair for all ten IR channels. Missing-field custom/archived tables retain their
previous wavelength-defined calculation; present-but-invalid values never fall back.

FD keeps its own coefficients. It uses an explicit file wavenumber when supplied,
or binds to the audited channel record only if all calibration attributes match
as normalized finite scalars. Unknown pairs are refused rather than guessed.
No packed-word width, DN, DQF, radiance or observation geometry is altered.

The original JSON is preserved byte-for-byte at
[legacy nominal calibration](AMI_legacy_nominal_calibration_202507190000.json),
SHA-256 `f519149e3ea3538866bad9f3e28cc0ddef741b6b4cdbf8febb7988aff6c08d40`.
For historical PR #365 replay, pass this archive to `AMI_local_support_source`;
its old C5 center checks deliberately retain the old definition. Reproducing an
old FD campaign also requires its historical source version, not the corrected reader.

## Same radiance, distinct coordinates

For center radiance **84.10494944080688**:

| IR105 map | BT (K) |
| --- | ---: |
| Legacy nominal-wavelength AMI | 284.584573443923 |
| Source-paired KMA v3.0 | 286.160920783162 |
| Pinned RTTOV band map | 286.160301649584 |

The original 1.575728 K mismatch is reproduced; it is not a constant correction
to apply to every BT. The paired KMA and RTTOV maps differ by about 0.000619 K
at this radiance. Their constants/correction forms are recorded separately.

Let model radiance be L, native RTTOV BT be Psi(L), and source-paired KMA BT be
Phi(L). A common KMA representation uses both Phi(Lmodel) and Phi(Lobs), with

$$
J_{KMA}v = \frac{\Phi'(L_{model})}{\Psi'(L_{model})} J_{RTTOV}v.
$$

At IR105 the derivative ratio is 0.999978794334092. Transformed NC JVP is
-0.000830634343735 K/control; independent transformed endpoints give
-0.000830633837268 K/control, with unchanged h=1e-4 and v=0.01*NC.
The saved seven-channel comparisons keep weak WV073 absolute error separate
from its larger relative error; no per-channel precision upgrade is claimed.

Common-coordinate center residuals are **5.718489 K (KMA)** and
**5.718592 K (RTTOV)**. The conditional positive-weight 3×3 averaging bounds
are **4.418133 K (KMA)** and **4.418216 K (RTTOV)**. The previous 5.990047 K
is preserved as a mixed-definition historical number, not a pure atmospheric
error bound. None of these bounds is a true 5 km footprint or error covariance.

[Comparison source](AMI_bt_coordinate_source_2026-10-04.py) and
[result](AMI_bt_coordinate_result_2026-10-04.json) retain all 126 observation
radiances, two slots, seven channels, strict 9/9 QC/missingness gates, and saved
model BASE/± radiances. New model BT/JVP values are coordinate replays only;
KDM, RTTOV, C-DISORT and native host were not rerun. Different SRFs cannot be
reconciled by scalar BT conversion alone; IR133 physical comparison stays conditional.

## Verification

Focused KO/FD tests: **84 passed / 3 private-data skips**. Independent measurement
expectation tests: **3 passed**. Scalar source-equation witnesses replace old
nominal SW038 expectations without widening their tolerance. New tests cover
IR105 DN3909, preserved DQF, legacy/equivalent wavelength, invalid explicit
wavenumbers, explicit/audited FD binding and rejection of unpaired metadata.

[Actual reader result](AMI_reader_boundary_result_2026-10-04.json) confirms the
retained 2025 KO center changes definition while the entire QC array is identical.
A separate pre-existing 2023 FD IR087 archive exercises the binding path with
2,565 usable sampled pixels; it is not a substitute 2025 meteorological case.
S2 calibration, actual SRF/optical accuracy, R, full DA and operational approval
remain OPEN; no residual fitting, threshold tuning or scientific approval is made.
