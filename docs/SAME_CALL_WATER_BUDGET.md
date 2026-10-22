# Same-call fp64 column water accounting

The optional `kdm6_column_budget` executable calls the unchanged legacy KDM
runtime exactly once and returns that call's state and surface increments.
`harness.same_call_water_budget` reuses the qualified #433 research coordinate
and the exact live fp64 forcing. This closes the **measurement gap**, but the
measured native case does **not** close its water balance.

## Measure and overlapping diagnostics

For one column with fixed call-entry dry density and thickness,

```
w[k] = forcing.DEN[k] * forcing.DELZ[k]
W(s) = sum_k w[k] * (QV+QC+QR+QI+QS+QG)[k]
R = sum_k w[k] * (q_total_out-q_total_in)[k] + total_precip_mm
```

`W` and `R` have units kg water m-2. The runtime's `rain_increment` is already
the all-species total: rain + snow + graupel + cloud ice. `snow_increment`
contains snow + ice, and `graupel_increment` is a subset as well. They are
preserved as diagnostics, never added to the total. A millimetre of liquid
water is numerically one kg m-2, and increments already include the subcycle
time integration: no additional `dt` factor is applied. The selected column
operator has zero external top influx, fixed forcing, and no horizontal/RK
transport. Number fields and BG are excluded from the water sum.

See `libtorch/src/sedimentation.cpp::surface_accumulation_torch` and
`libtorch/src/runtime.cpp::kdm6_fn`. This fixed measure is not the host's
complete moving-mass or MU/g budget. Negative raw water, if produced, is
included rather than hidden by a diagnostic projection.

Raw KDM change, cleanup change, and applied change are separate:

```
dK = q_raw - q_in
dZ = q_clean - q_raw
dA = q_clean - q_in
```

The pinned interior `MP_ZERO_OUT=2` path clips negative vapor to zero and
sets condensates below the binary32 namelist threshold to zero. No water or
latent-heat compensation is invented. Finish changes temperature coordinates;
its water outputs are the cleaned water fields, so `dA` is the applied water
change. This diagnostic neither alters nor revalidates the accepted finish AD.

## Capture and provenance

Build with `-DKDM6_BUILD_RESEARCH_COLUMN_BUDGET_TOOL=ON`. The default is OFF;
the tool is not installed, not linked into the native host, and adds no C/Fortran
ABI exports. It calls the legacy volume-coordinate kernel (`dry_number=false`),
after the admitted explicit dry-number boundary's entry conversion. Native DEN
remains dry density; the generic `DEN/(1+QV)` conversion is not used.

The Python runner checks the versioned number admission and exact arrays,
pins report/admission/namelist/checkpoint/executable hashes, checks dt and ncmin
against the namelist and XLAND against the checkpoint, and verifies the returned
input echoes bitwise. The C++ tool checks that actual operand tensors were
unchanged by the call. Each response has one FnResult's state and increments.
Separate runs and instrumented builds must have separate attribution.

The binary v1 protocol is little-endian IEEE binary64, field-major, L=1..256:

| Record | Fields |
| --- | --- |
| Request | `K6BUDG1\0`, u32 version=1, u32 L, f64 dt/xland/ncmin_land/ncmin_sea, state[12,L], forcing[4,L] |
| Response | `K6BOUT1\0`, u32 version=1, u32 L, state_in[12,L], forcing_in[4,L], state_out[12,L], total/snow_ice/graupel f64 mm |

Packing follows the existing State/Forcing `fields()` order. Files with wrong
length, version, nonfinite data, or unusable forcing are refused. The output is
published without overwriting an existing path. The Python runner is value-only
and requires private NetCDF input only when capturing a native case; standalone
protocol and analytic ledger tests need NumPy, not the private host or RTTOV.

## Interpretation

`diagnostic_complete` means the raw/cleanup/applied split is available and
consistent. It does not mean conservation. The predeclared numerical comparison
is `abs(R) <= 256*eps*max(1,abs(Win)+abs(Wout)+abs(export))`; this is an
inventory-scale diagnostic gate, not an error bound on the physical scheme.
The gate failure and raw residual are retained. `closed_water_budget_certified`
stays false; no energy, number, named-process, full-host or forecast-skill
certificate follows from this accounting.

The [native experiment](../harness/evidence/same_call_water_budget_2026-10-22/REPORT.md)
reports the material nonclosure and the separate cleanup sink. Legacy forward
parity and accepted local AD results remain distinct from conservation.
An isolated runtime overlay localizes the dominant loss to sedimentation and
a smaller loss to the later microphysics pass, with bit-identical final
responses. Pre-sedimentation trace rows are top-first and must be reversed
against the other, bottom-first stages. These state-stage measurements do not
yet identify the responsible internal departure/arrival calculation.
