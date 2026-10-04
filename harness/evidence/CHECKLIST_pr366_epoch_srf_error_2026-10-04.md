# PR #366 follow-up: product epoch, SRF and error coordinates

Baseline: `26354057369e2b3f0820f90fa6cbf827a289b47b`.
The source-paired BT decoder, historical replay and coordinate-JVP closures stay
closed. This follow-up adds metadata and policy evidence, not a new physical map.

- [x] Locate and inspect the original local 2025-07-19 00Z FD products.
- [x] Verify all ten reported table versions and calibration tuples; pin file hashes.
- [x] Inspect the actual KO00/KO02 headers separately rather than transferring FD times.
- [x] Distinguish the product's table label, operational SRF processing history and
  installed RTTOV response package; do not infer one from another.
- [x] State coordinate requirements for Jacobian, bias and covariance together.
- [x] Check availability of the named ELA parents without substituting FD or LA.
- [ ] Establish the exact KO ELA source lineage and processing/SRF identity, or
  obtain a justified product-to-simulation compatibility statement.
- [ ] Approve a physical observation target, supported base error/bias model and
  independent BT/sensitivity accuracy criteria. Do not infer R from these residuals.

## What the recovered files establish

The original FD files are retained under
`/Users/yhlee/KDM6AD+/observations/gk2a/20250719_0000_fd/`, outside the canonical
code tree. All ten files declare `calibration_table_version=v.3.0_20190415`.
Their gain/offset, Teff polynomial and h/c/k match the audited shipped tuples
exactly. This replaces the earlier inability to inspect the 2025 FD headers;
it does not retroactively change the scope of the earlier receipt.

[Header-only source](AMI_epoch_metadata_source_2026-10-04.py) and
[receipt](AMI_epoch_metadata_result_2026-10-04.json) pin the original manifest,
all ten FD and fourteen selected KO hashes, headers, arguments and source hash.
No pixel array was indexed or decoded and no new satellite/model input was acquired.
Hashing reads local object bytes; header inspection is separate from pixel analysis.

FD headers record mission reference 00:00:00, scene acquisition 00:00:33,
generation 00:09:53 and raw start/end times. These are full-disk product metadata,
not a selected pixel's exact acquisition time. The KO headers instead name original
ELA files (`origianl_sourece_file`, the producer's spelling) and expose no calibration
version or acquisition-time attributes. A filename is not a source hash or established
KO→FD lineage. Do not assign the FD interval to the remapped KO pixels or treat
nominal 20-second timing as a measured collocation error.

## Named ELA parents: bounded follow-through after PR #368

The team rechecked the fourteen selected KO object hashes against the retained
[metadata receipt](AMI_epoch_metadata_result_2026-10-04.json); all match. Their
headers name fourteen same-channel ELA parents at the two nominal slots. For
example, IR105 at 00:00 names
`gk2a_ami_le1b_ir105_ela020ge_202507190000.nc`. No `ela020ge` files were found under
`/Users/yhlee/KDM6AD-k/GK2A` or `/Users/yhlee/KDM6AD+/observations/gk2a`.
The local manifests describe FD objects, and the searched repository reader/
mapping code does not supply the ELA-to-KO producer or its remapping parameters.
This records the searched scope, not global absence of the source products.

The anonymous NOAA bucket queries on 2026-10-04 provide a separate availability
check: the [exact ELA hour-prefix response](AMI_ELA_prefix_listing_2026-10-04.xml)
has zero keys and is not truncated; the
[L1B prefix response](AMI_L1B_product_prefixes_2026-10-04.xml) lists only FD and LA
at that location. An LA object is not the named ELA parent. Query URLs are:

```text
https://noaa-gk2a-pds.s3.amazonaws.com/?list-type=2&prefix=AMI%2FL1B%2FELA%2F202507%2F19%2F00%2F&max-keys=10
https://noaa-gk2a-pds.s3.amazonaws.com/?list-type=2&prefix=AMI%2FL1B%2F&max-keys=10&delimiter=%2F
```

For these 2026-10-04 queries, the saved XML body SHA-256 values
are `fc3dce6da04601917f763dca7327abff82e9de663584f8dccefafe3a31856c1c`
and `029483d541b4cd6b02f5d4152e22b8927db01c480493f18b8e1c3fa105d98123`.
No image product was downloaded or substituted. The official
[NMSC catalog](https://nmsc.kma.go.kr/enhome/html/base/cmm/selectPage.do?page=static.utilization.software)
publishes calibration/SRF packages and separate projection reference data; that catalog
alone does not identify the processing baseline of these particular KO objects.

The unresolved evidence is now specific: the referenced ELA object/processing
record, or a producer statement tied to the selected KO objects, must connect its
radiance/SRF definition to the installed RTTOV response. A remapping record and
source scan-time mapping are also needed before assigning a footprint or pixel
acquisition time. Generic operating history or a same-stamp FD/LA file cannot
supply these missing links. Compatibility and observation-error approval remain
OPEN; the numerical decoder and coordinate closures are unchanged.

## Three meanings of version

| Evidence | Established | Not established |
| --- | --- | --- |
| 2025 FD table-version header | v3.0 BT coefficient table label and exact tuple match | Actual SRF curve or per-pixel scan time |
| KMA processing history | Published operational IR133 SRF-model revision | Hardware change or exact KO product processing baseline |
| Installed RTTOV package | Shifted IR133 curve and v3.1-referenced coefficient package | Certified equivalence to the selected KO products |

The NMSC-authored [in-orbit validation paper](https://doi.org/10.3390/rs13071303)
reports an IR133 shift chosen through GEO–LEO intercalibration tests and introduced
operationally on 27 September 2019. This is a response-model/processing revision,
not evidence that the sensor physically changed. The
[NWP SAF description](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_gkompsat2_1_ami_srf.html)
identifies KMA's later shifted IR133 package. Therefore a v3.0 table label alone
cannot prove that a 2025 radiance used an unshifted response. Conversely, operational
history alone does not certify this individual product's processing baseline.
[Bounded source/history note](AMI_IR133_SRF_epoch_and_error_coordinates_2026-10-04.json)
records URLs and official archive hashes. The earlier unshifted curve was not recovered.

For normalized responses a and b, scalar band radiance generally cannot recover
another response's integral. A two-frequency example is enough: a=(1,0), b=(0,1),
spectra (1,1) and (1,2). Both give a·L=1, while b·L differs. Thus no scalar function
of a·L alone recovers both. This is a mathematical counterexample, not an IR133
error estimate. Changing the BT coordinate cannot perform a missing band integration.

## Coordinate-consistent error policy

For B_K=g(B_R), at a declared common reference point let D=diag(g'_c). Locally:

$$
J_K=D J_R,\qquad b_K\simeq D b_R,\qquad R_K\simeq D R_R D^T.
$$

For invertible D and the same linearization, J^T R^-1 J is invariant. This transforms
an independently supported R; it does not estimate one. With diagonal sigma only,
the local rule is sigma_K=abs(D)*sigma_R. Keep bias, error and Jacobian reference
points explicit. At different model/observation points their derivatives can differ.

From the retained IR105 observed radiance, D_obs=0.9999850849540072 and
D_obs²=0.999970170130473. At the model radiance D_model=0.999978794334092.
The exact common-coordinate residual is 5.718488515262 K; rescaling the RTTOV
residual by D_obs gives 5.718506502003 K, differing by -0.000017986741 K.
This illustrates the finite-residual approximation; neither number defines sigma.
[Seven-channel deterministic ratios](AMI_coordinate_error_ratios_2026-10-04.json)
are conditional coordinate diagnostics, not variances or confidence intervals.

For finite residuals use the exact transformed model and observation values. A
nonlinear transformation does not generally preserve a Gaussian/Huber cost merely
by multiplying sigma at one point. Declare the physical observation coordinate,
base error distribution, bias treatment and approximation before approving cost.

This limitation concerns the approximated error model, not loss of information
under an exact change of coordinates. For a differentiable, invertible,
state-independent g with a nonsingular Jacobian,
the full conditional density transforms as

$$
p_K(z\mid x)=p_R(g^{-1}(z)\mid x)\,|\det Dg^{-1}(z)|.
$$

At the fixed accepted observation z=g(y), its negative log-likelihood differs
from the original by log|det Dg(y)|, a data-only constant. State likelihood ratios,
gradients and the optimizer are preserved. Assuming Gaussian/Huber errors again in
the new coordinate with only a local sigma or DRD^T transformation is a separate
approximation. No probability-model implementation or calibrated R is added here.

The existing sigma=1 K remains diagnostic, not a calibrated all-sky error model.
No covariance framework, new weighting, SRF substitution, channel deletion or
production algorithm is introduced. S2 calibration, S11 physical accuracy, full
DAWindow/native routing and operational approval retain their separate OPEN status.
