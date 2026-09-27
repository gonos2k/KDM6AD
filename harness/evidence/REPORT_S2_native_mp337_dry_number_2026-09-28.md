# S2 opt-in mp337 dry-number host boundary

The [v2 C ABI selector](REPORT_S2_abi_dry_number_2026-09-28.md) now reaches the
dry-number C++ operator, but the private mp337 host wrapper still selected the
legacy raw-number basis. The opt-in patch
[`s2_mp337_dry_number_optin.patch`](../g33_fortran/s2_mp337_dry_number_optin.patch)
adds an exact `KDM6_S2_DRY_NUMBER=1` gate to that wrapper and appends the new
signed selector to its private ISO_C_BINDING mirror. Unset or exact `0` keeps
the prior mp337 calculation. The canonical private host source and
operational install were not changed.

On the opt-in path, entry `rho_d = DEN/(1+Q)` is checked and frozen for the
call. The timestep-one CCN profile is first generated in its existing volume
units, then divided by `rho_d` before the ordinary dry-specific QN staging.
The C++ path converts all four QN fields to volume units internally and
returns them to the host's dry-specific prognostic basis. For effective
radii, the wrapper supplies the existing helper with paired volume mass and
number arrays and `rho=1` only in the opt-in branch. Reflectivity continues
to receive dry-specific QR/NR/QS/QG; its own equation derives dry density
from pressure, temperature and dry-specific water vapor. The two density
computations are not claimed bitwise identical at every output state.

The patch applies with zero fuzz to the canonical private sources. The
baseline SHA-256 values are `940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb`
for `module_mp_kdm6ad_cons.F` and
`0aef23e61cd0e1a31eda0d9213f48c838a119f0c8e0de6dcf1e8da76af6b55b3`
for `kdm6_iso_c.F`. The resulting source hashes are
`ab370593944f0e6968edcb1c4f8d20f4549ef1f552ea3bfec8295732097e2010`
and `b676c526670922f8e151b1f0835a4a0e1d522b4c3d00675d58d745afb56c08f5`.
The new C ABI library SHA-256 is
`bfe758fb068b737e27f9d97ba3bb05ae6a2bc17c400daebb517dd49387eca625`.
An isolated control wrapper differs from the canonical wrapper only by the
required new selector initialization to zero. Both control and candidate
linked fresh wrapper/ISO objects ahead of the recorded existing host archive;
this is not a clean rebuild of every host object.

Three one-rank/one-thread runs used the same retained 5 km input and 40 s
window, saving 0, 20 and 40 s. The control executable SHA-256 is
`7c264dbd60cad1acab0a85c9bb95b722bf6997945a22a9a129fa82d06e76c908`;
the candidate executable SHA-256 is
`12ccc0e0492f60a8ad1a9b19dae0c08c717b0632daa9f0bd01241ad62afcf1d1`.
Control and candidate with the S2 gate unset completed and produced the same
forecast SHA-256 `5e8094dde895e2fe878aeebb2f725ede449a82a2053b9d0a52946c7fdd074509`.
All 254 common saved variables matched raw-bit at each of the three times.
With the candidate gate set to `1`, the same executable also completed; its
forecast SHA-256 is
`660b5af0c5ebeb46c5af2863dd2d76c4db237a0a11d3746de9b51f1810ea2a8f`.

| Saved time | Numeric variables changed, gate off → on | QN fields finite | `REFL_10CM` changed cells |
| --- | ---: | --- | ---: |
| 0 s | 0 | all four | 0 |
| 20 s | 24 | all four | 143,483 |
| 40 s | 78 | all four | 172,692 |

All numeric outputs in the opt-in forecast were finite at all saved times.
At 40 s, QNCCN/QNCLOUD/QNICE/QNRAIN had 0/4/3/0 negative cells; whole-host
nonnegativity therefore remains OPEN. `REFL_10CM` was finite but its change
is not an independent radar-accuracy result. Effective-radius variables were
not saved in this forecast, so their native output was not compared. The
private source/build/input/run receipt has SHA-256
`1e4c01c7944dc7648f2c1894da47f11d3de557ff30331ba7e3714a31b6e0cfef`;
it is retained locally rather than copied into the public repository.

This is a 40 s execution and default-path noninterference result for one
selected mp337 configuration. Physical number thresholds and empirical
coefficients, full mass/number budgets, mp137 legacy transport, fp64 dry-number
AD, RTTOV accuracy and accepted observations remain unapproved. S2 and the
operational/default-path decision stay OPEN. No deployment action was taken.
