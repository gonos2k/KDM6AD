# Native KDM6 NC/NI unit contract

## Finding

The active WRF state contract and the KDM6 number equations use different
bases at the NC/NI boundary. WRF registers and transports `QNCLOUD`/`QNICE` as
number per kg, and its scalar RK update weights the scalar by the dry-column
mass `MU`. The KDM6 kernel instead combines NC/NI with `DEN*Q`, where active
`DEN=1/(AL+ALB)` is dry-air density and `Q` is a water mixing ratio. Its slope
equations and limiter back-calculations therefore operate on volume number
concentration. Both mp37 and mp137 pass the numeric NC/NI values in and out
without a density conversion.

This is a source-supported interface-basis conflict. It does not prove the
basis of every external initial/restart file's numeric payload. The input
metadata and scalar transport specify the WRF side; the kernel equations imply
the KDM working basis. Raw-bit equality between mp37 and mp137 does not resolve
that mismatch because the two paths share the same value handoff.

## Producer, transport, kernel and consumers

| Stage | Source-grounded behavior | Unit interpretation |
| --- | --- | --- |
| WRF Registry | `qnc`/`qni` are `scalar` package fields with `# kg-1`; KDM6 and KDM6AD packages include them as prognostics. | WRF's declared carrier is number per kg of air; the RK mass weighting below identifies the model measure as dry air. |
| Initial input | Optional QNC/QNI flags default off and are populated from input metadata when present. `module_initialize_real` interpolates `qnc_gc`/`qni_gc` directly into `scalar`; no density multiply/divide occurs there. | The code preserves the scalar value. External file provenance is needed to establish what basis its numbers actually encode. |
| RK scalar transport | `rk_update_scalar` evolves `scalar` using `MU_OLD+MUB` and `MU_NEW+MUB` in the conservative numerator/denominator. | The transported prognostic is a mixing ratio per unit dry-column mass, consistent with the Registry's per-kg declaration. |
| KDM driver and mp37 wrapper | The driver passes `qnc_curr`/`qni_curr` as `NC`/`NI`. `module_mp_kdm6.F` copies them to `nci` unchanged and writes them back unchanged. | No host-side basis conversion is performed on the legacy path. |
| KDM6AD wrapper | The wrapper casts `NC`/`NI` to `c_float`, passes them to the C ABI, and copies returned values back to the host `REAL`; neither boundary scales by density. | The f32 bridge preserves the same numeric-value contract as mp37; it does not correct units. |
| KDM internal equations | `DEN` is `1/(AL+ALB)`. The cloud slope uses `lambda_c = (PIDNC*NC/(DEN*QC))**(1/3)`; limiter branches assign `NC = DEN*QC*lambda_c**3/PIDNC`. Ice uses the analogous `DEN*QI` relation. | Since `DEN*QC` is water mass per volume, the number operand and back-calculated number are volume concentrations (`# m-3`) for this equation. This basis follows from the equation, not an explicit KDM variable-unit declaration. |
| Post-KDM diagnostics | `effectRad_kdm6` forms `QC*DEN`/`QI*DEN` and uses NC/NI in the same distribution-derived effective-radius equations. | This consumer is consistent with the kernel's volume-number working values. Those returned values are nevertheless written into WRF's per-kg scalar slots. |
| Native RTTOV cloud bridge | The public cloud bridge declares NC/NI as dry-specific, receives explicit `rho_d`, and converts them to volume moments for optics. | This conversion is valid for Registry-basis inputs. Applying it to unconverted post-legacy-KDM outputs multiplies a volume value by density again. The prior observation evidence therefore retains its stated conditional number interpretation. |

The internal equation gives the central distinction:

```text
N_dry [# kg_dry-1]  ×  rho_d [kg_dry m-3] = N_volume [# m-3]
```

The registry-listed scalar is `N_dry`; the KDM number formulas consume and
return `N_volume`. The wrappers currently identify the values only as `NC` and
`NI`, so there is no typed/unit-bearing boundary that would expose the change.

### Initial values and basis evidence

The optional `QNC`/`QNI` inputs are interpolated into scalar storage without a
conversion. The only `make_DropletNumber`/`make_IceNumber` initialization calls
found in active `module_initialize_real.F` are inside a Thompson/ThompsonAero-
specific block. They convert a volume concentration back to a per-density
scalar by dividing by `temp_rho`. This documents a per-density scalar
convention in that separate initializer path; it does not repair or establish
KDM6's initial NC/NI basis.

The KDM6AD bridge does not scale NC/NI at either end. Its `REAL`→`c_float` and
`c_float`→`REAL` copies preserve values at f32 precision, and the mp37 Fortran
wrapper does the same around its internal `nci` arrays. Parity of those two
values is evidence of implementation agreement, not evidence that the units
are consistent with Registry or scalar-RK semantics.

## Number budgets and cleanup

For a Registry-basis state, the KDM entry conversion needed by the kernel
equations is `N_volume,in = rho_d * N_dry,in`; the returned volume value must be
converted back as `N_dry,out = N_volume,out / rho_d` before storing it in the
host scalar or advancing it through scalar RK. With density treated as live,
the conversion derivatives are also part of the map:

```text
dN_volume = rho_d * dN_dry + N_dry * d(rho_d)
dN_dry,out = dN_volume,out / rho_d
              - N_volume,out * d(rho_d) / rho_d**2
```

For per-species cotangents, the entry-map adjoint contributions are
`bar_N_dry = rho_d * bar_N_volume` and
`bar_rho_d += sum_s(N_dry,s * bar_N_volume,s)`. For the inverse exit map,
`bar_N_volume = bar_N_dry / rho_d` and
`bar_rho_d -= sum_s(N_volume,s * bar_N_dry,s) / rho_d**2`. All species sharing
one layer's density must accumulate into that density cotangent. If density is
fixed for the local operator, the `bar_rho_d` terms are omitted.

These are boundary requirements for a future versioned map, not changes made
to the operational legacy path. A repair must cover entry, exit, first-step
number initialization, restart/checkpoint interpretation, and every number
field the kernel consumes. It must be opt-in or separately versioned; silently
changing the default would invalidate existing raw-bit parity evidence and
would reinterpret stored checkpoints.

`solve_em.F` orders `microphysics_driver` (3722), mass-array `zero_outb`
(4015–4021), mass-array `zero_outa` (4056–4062), then
`moist_physics_finish_em` (4088). The scalar `zero_outa/b` calls are guarded by
`MP_ZERO_OUT_ALL>0` (4023–4043, 4064–4085) and are skipped in the audited
`MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0` setup. In this configuration `solve_em`
calls `microphysics_zero_outa/b` on `moist`; the generic routines can also be
called on `scalar` when the ALL option is enabled. Under the audited setup, the
six water-mass species are clamped/thresholded and NC/NI are not. Thus
cleanup does not itself transfer or zero a number moment. The raw NC/NI
difference across legacy KDM cannot be labelled a host-carrier applied change
in `# kg_dry-1`: the kernel equations imply volume number. A valid number ledger
must first establish the incoming value's basis, put both sides on one declared
measure, and keep mass cleanup, number tendencies, and observation-profile effects as
separate terms. If provenance establishes that a selected KDM input already
carries volume number from an earlier KDM call, that isolated kernel's
pre/post number difference can be described conditionally in `# m-3`; it is
still not a dry-specific host-scalar change and does not close a number budget
through scalar RK or a restart. If the input came from a Registry-basis source,
the entry already crosses the mismatch. The root-owned application ledger is
linked from the [native number-budget evidence](../harness/evidence/native_number_budget_2026-10-22/REPORT.md)
when present. Its water entries use the declared dry-mass measure; its number
entries are marked as legacy raw values with the basis conflict retained. The
ledger is not a closed conservation proof by itself.

## Public dry-number and optical paths

The public runtime has an opt-in `dry_number` map that multiplies the four
number fields (CCN, cloud, ice and rain) by its computed dry density before the
kernel, then divides them after the kernel. That map is not used by the
operational C ABI, which retains the legacy default. Its density expression is
`forcing.rho/(1+qv)`, so callers must supply a `forcing.rho` representing moist
density for the result to equal dry density. The native WRF `DEN` argument
audited here is already dry density (`1/(AL+ALB)`); passing that `DEN` directly
to this opt-in conversion would divide by `(1+QV)` a second time.

Supplying moist density to satisfy that conversion is not a correct native
KDM workaround either: `build_forcing` also leaves `den=forcing.rho` for the
kernel's physical rates, changing it from host `DEN`. A coherent native repair
needs a separately named `rho_dry` conversion operand while preserving the
existing physical-density operand, plus the entry and exit number conversions.
The optical profile bridge's local `rho_moist` construction is isolated to its
cloud conversion and is not a recipe for the native KDM forcing bundle.

For an arithmetic illustration only, take `NC=100 # kg_dry-1`,
`rho_d=2 kg_dry m-3`, and `QV=0.02`. The intended volume value is `200 # m-3`.
The legacy no-conversion path sends the numeric value 100. The opt-in formula
fed native `DEN=2` derives `rho_d=2/1.02=1.960784...` and sends `196.0784...`.
Feeding synthetic moist density `rho_m=2.04` yields the intended 200 number,
but also changes the separate physical `den` input from 2 to 2.04. These are
unit-arithmetic counterexamples, not native measurements.

The native all-sky observation bridge avoids that particular ambiguity by
accepting explicit `rho_d` and constructing its generic optical forcing as
`rho_d*(1+QV)`. Its `NativeCloudState` still assumes its NC/NI inputs are dry
specific. Therefore the optical bridge is well-defined for a dry-basis source,
but raw values emitted by the unconverted legacy KDM boundary require a
conditional interpretation. The existing observation reports retain this
qualification; this audit does not retroactively certify their NC/NI units.

## Source references and provenance

The paths below are active local host sources in the canonical private tree
`/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/`; they are not present in a public
clone. SHA-256 values bind this audit to the inspected source snapshot; the
root-owned audit receipt records the same source paths and hashes. The line
ranges below are navigation anchors in the active local tree.

| Source | Relevant lines | SHA-256 |
| --- | --- | --- |
| `Registry/Registry.EM_COMMON` | 535–554, 3214–3217 | `6741720cba12ad7ee1c172339bd8def5973b22f4e88ab9cd152f3ba3df456e37` |
| `share/module_optional_input.F` | 292–302, 361–369 | `99dab3a5c498dd7492ad1a989457c1000f148ae39e1b9235b19352dfaeaa5dca` |
| `dyn_em/module_initialize_real.F` | 2004–2040, 4789–4831 | `a4bb2497d0c70588f45da06fe9754b56597245033fec7b4bb51beba05901ce2c` |
| `dyn_em/module_big_step_utilities_em.F` | 5394–5446, 5540–5545 | `27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c` |
| `dyn_em/module_em.F` | 1680–1725, 1732–1775, 1901–1909 | `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7` |
| `dyn_em/solve_em.F` | 3722, 4015–4044, 4056–4088 | `d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f` |
| `phys/module_microphysics_driver.F` | 2742–2757, 2885–2905 | `94db84c45b7422b62e04967cb3cd1362311abdb02fa3d374d881799c0bce7e84` |
| `phys/module_mp_kdm6.F` | 379–429, 1564–1575, 3266–3295, 4404–4434 | `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` |
| `phys/module_mp_kdm6ad.F` | 236–251, 287–296, 330–345 | `c56499524c73bec4e5092e7aecfde244d072f9572733708226c7f6d743cc9e67` |
| `phys/module_microphysics_zero_out.F` | 24–72, `microphysics_zero_outb` | `a57268701b424b07a604ce93f733314183a29bfb39e7e6283f92f8668808fa4f` |

The public Python/C++ sources remain independently inspectable at
`oracle/kdm6/runtime.py` and `libtorch/src/runtime.cpp` for the opt-in
`dry_number` transform, and `oracle/kdm6/obs/native_cloud_profile.py` for the
explicit dry-density optical bridge. No physics/ABI source, default behavior,
or native host executable was changed for this audit.

The public dry-number implementation is source-audited at
`oracle/kdm6/runtime.py:535–556,728–740` and `libtorch/src/runtime.cpp:421–445,658–669`.
The operational `kdm6_fn`/`kdm6_step` overloads select `dry_number=false`
(`libtorch/src/runtime.cpp:680–687,1086–1093`). The optical bridge's explicit
dry-density and derived moist forcing are at
`oracle/kdm6/obs/native_cloud_profile.py:107–116,139–176`. In the generic
runtime's `build_forcing`, `den` retains the supplied `forcing.rho`; only
`dend` is replaced by the computed dry density in this opt-in mode. This is why
passing the native dry `DEN` directly fails to recover the intended conversion,
and passing a synthetic moist density changes a separate kernel density input.
