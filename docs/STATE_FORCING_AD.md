# Independent state and forcing derivatives

The additive fp64 interface differentiates the existing KDM step with respect
to twelve state blocks and four independent forcing blocks. It preserves the
old state-only entry points and their packed layouts. It does not differentiate
the native host time step or declare `NativeLiveStepper` to be `full_host`.

For `y = K(s, F)`, the first-order contract is

```
JVP(ds, dF) = K_s ds + K_F dF
VJP(u)     = (K_s^T u, K_F^T u).
```

The four forcing blocks, in order, are `rho` (kg m^-3), `pii`
(dimensionless Exner), `p` (Pa), and `delz` (m). The twelve state blocks retain
the order `th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg`. Each block is a native
Fortran `(im,kme,jme)` array; fields are concatenated, with `i` contiguous.
No vertical remapping is performed. The selector and number-coordinate
contracts are inherited from `kdm6_step_ad_number_c`; selecting joint
derivatives does not normalize the inputs or change the physical map.
Independent forcing perturbations need not satisfy the host's thermodynamic
relations. They identify kernel partials; composing the host forcing generator
later supplies the physically linked directions.

## Entry points and ownership

* `kdm6_step_ad_state_forcing_c` has the same arguments as
  `kdm6_step_ad_number_c`. With `value_only=0`, it copies the raw buffers into
  sixteen independent owning leaves and returns a recorded handle. With
  `value_only=1`, it returns the same forward values and a null handle.
* `kdm6_handle_state_forcing_jvp_c(h, ds12, dF4, dy12)` consumes both input
  directions and writes twelve output direction blocks.
* `kdm6_handle_state_forcing_vjp_c(h, u12, gs12, gF4)` writes both gradients.
  Caller allocations must have the documented sizes; the output buffers must
  not overlap one another.
* Both C derivative calls retain the graph for repeated calls and use the
  existing single-thread fence, exception translation, and floating-point
  environment guard. Close the handle with `kdm6_handle_closep_c`.

Old state-only handles are rejected by the joint derivative calls before
tensor staging or output writes. Old state-only derivative calls remain
available. No existing exported signature or ABI version changes: ABI major
2 now has fourteen allowlisted C symbols, including these three additions.
The ISO_C_BINDING module exposes corresponding `kdm6_step_ad_state_forcing`,
`kdm6_handle_state_forcing_jvp`, and `kdm6_handle_state_forcing_vjp` wrappers.
Its forward wrapper checks four-dimensional array shapes before entering C;
derivative buffers follow the existing flat caller-sized contract.

Direct C++ users can mark their sixteen inputs as independent leaves before
calling the existing `kdm6_step` and use `Handle::jvp_state_forcing` and
`Handle::vjp_state_forcing`. Joint methods reject frozen, non-leaf, or repeated
input tensor identities and require exact shape, dtype, and device agreement
for seeds. This identity check does not detect every shared-storage view;
direct callers must preserve the inputs throughout the handle lifetime.
The state `active_field_mask` projects state directions/gradients only; all
four forcing inputs remain active. These are partial derivatives: passing a
non-leaf `F=G(s)` would confuse independent partials with a composed derivative
and is deliberately rejected. The C boundary's output serialization is
value-only. This interface establishes first-order derivatives, not HVPs.

## Native 39-level verification

`harness/verify_state_forcing_ad.py` reads the existing MP137 hexadecimal
trace without modifying it. The published evidence uses the second MP input
from PR #426's saved-T/Q experiment, native column `(i=156,j=21)`, all 39
levels, `dt=20 s`, `xland=2`, and `ncmin_land=ncmin_sea=10`. It promotes the
captured binary32 values exactly to binary64. The executable used for this
verification is a separately built research library; no new native host
integration is implied by this offline evaluation.

The captured wrapper executed `physics_variant=0,dry_number=0` and copied its
raw fields directly. In particular, the cold-start `NN` is populated by the
host's volume CCN profile even though other native number fields have Registry
mass-specific declarations. The capture is therefore an **as-executed legacy
coordinate case**, not evidence that all four number fields have one consistent
physical basis. `dry_number=1` assumes homogeneous dry-mass-specific number
inputs and is a separate opt-in map; it must not be substituted for this trace.

The verifier requires raw-bit equality between the old value-only forward,
the new value-only forward, and the new graph-recording forward. It checks
state theta/QV, each forcing separately, and their mixed direction. Directions
in zero-valued hydrometeor fields are zero in this capture; it does not claim
finite-difference coverage of every state direction at a positivity boundary.
Every direction uses nine central-difference step sizes. Error gates apply to
each of the twelve output fields after declared physical scaling, so a large
number-concentration output cannot hide a temperature or moisture error.
The report retains the entire sweep and both sides of each dot product.

The initial warm/cold and inactive-rain summaries are value-only diagnostics.
They do not expose downstream limiter branches or integer sedimentation
substep schedules. Derivatives are local to the executed piecewise map;
success on this profile does not certify differentiability at every branch
boundary. Independent finite differences and JVP/VJP inner products serve
different purposes and are both required.

Run with a caller-provided private trace and the intended isolated library:

```sh
python3 -m harness.verify_state_forcing_ad \
  --library /absolute/research/build/libkdm6_c.dylib \
  --trace /absolute/private/native_trace.hex \
  --step 2 --i 156 --j 21 --levels 39 --xland 2 \
  --ncmin-land 10 --ncmin-sea 10 --output /new/report.json
```

Inputs, the library, and the verifier source are hashed before and after the
evaluation. The report destination must be new and distinct from those inputs.
The raw private trace is not distributed in the public repository. Synthetic
C++ and Fortran ABI tests are separate from native-input evidence.

The Fortran interoperability fixture also retains an unscaled-covector stress
diagnostic. Its joint dot residual is approximately `1.9e-9` relative and does
**not** meet an initially attempted `1e-10` gate. The state-only part reproduces
the old ABI's result bitwise, including its own small duality residual. The
discrepancy is concentrated in NCCN-seeded derivatives; exact accumulation of
the final products does not remove it. An internal cancellation mechanism has
not been proven. The primary interoperability gate uses declared output-unit
scales at `1e-10`; that gate does not repair or close the unscaled numerical
stress. Neither this interface nor the native-input result promises uniform
relative derivative accuracy at every number-concentration regime.

## Remaining composition

These kernel partials do not supply `G_X` for host-generated forcing `F=G(X)`.
They also exclude RK integration, retained heating memory, moist-theta host
conversion, finish limiters, native radiation, and RTTOV pressure sensitivity.
The already demonstrated two-step forward state/tendency carry is not a
derivative proof and does not need to be rerun to establish this kernel boundary.

For a later same-coordinate, fixed-dt tendency `r=(y-s)/dt`, the derivative
must include `(dy-ds)/dt`, including the negative input identity. Actual host
finish uses additional transformations and limiters; its applied map must be
composed explicitly before claiming a host tendency derivative. Observation
and cost derivatives, full-host adjoint replay, physical budget closure, and
forecast skill remain distinct validation work.
