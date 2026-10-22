# Native dry-number research boundary v1

`harness/native_number_boundary.py` implements an opt-in first-order boundary
around the unchanged legacy state+forcing kernel:

\[
\Psi(s_d,F)=C_{\rho_d}^{-1}\,K_0(C_{\rho_d}s_d,F),\qquad
\rho_d=F_{DEN}.
\]

Only state rows `NN, NC, NI, NR` change coordinate: input/output counts are
per kg dry air and internal kernel operands are per volume. `TH, QV, QC, QR,
QI, QS, QG, BG` are unchanged by these coordinate conversions. BG/QIB is a
rime-volume mixing ratio, not a particle-number field. All four physical
forcing arrays `DEN, PII, P, DELZ` pass through unchanged. There is no
`DEN/(1+QV)` conversion and no synthetic moist-density forcing.

This implements a **versioned research kernel boundary**, not a replacement
for the operational mp37/mp137 wrappers, first-step initialization, scalar RK
or checkpoint migration. Those host paths remain unchanged. The default
`verify_microphysics_obs_ad` invocation still uses legacy raw numbers.

## Admission and provenance

An explicit `NumberBasisAdmission` is required. Its schema is
`kdm6.native_dry_number.v1`; all four field units, source identifier, source
SHA-256 and receipt SHA-256 must be present. Allowed origins are
`verified_dry_producer` and `derived_kernel_volume_coordinate`. Unknown,
Registry-only and historical-raw declarations are refused. Validation of a
metadata record is not independent proof that arbitrary caller assertions are
true; the enclosing caller must bind the receipt to its actual loaded inputs.

`harness/native_number_qualification.py` supplies the bounded native research
admission used here. It takes exact recorded kernel-volume operands and
native dry DEN at one fixed baseline and defines `n_d=N_volume/rho_d` once.
It preserves TH and all other non-number state rows, pins the complete state
and forcing arrays and binds trace/namelist/checkpoint hashes, step, column,
level count and the initial native-X digest. The receipt validates its exact
field map, density source, conversion declaration, canonical content digest
and recomputed numeric roundtrip. It is applied before the trial loop; dry
controls are **not re-derived from archived volume values at each trial**.

| Field | Kernel coordinate source | Research input/output coordinate |
| --- | --- | --- |
| NN / NCCN | Captured `MP_INPUT.NN`, required volume operand for activation/clamps | Defined `NN_volume/rho_entry`, per kg dry air |
| NC | Captured `MP_INPUT.NC`, volume-number DSD coordinate | Defined `NC_volume/rho_entry`, per kg dry air |
| NI | Captured `MP_INPUT.NI`, volume-number DSD coordinate | Defined `NI_volume/rho_entry`, per kg dry air |
| NR | Captured `MP_INPUT.NR`, volume-number rain DSD coordinate | Defined `NR_volume/rho_entry`, per kg dry air |

The receipt says `original_host_payload_basis=unknown_not_migrated` and
`original_host_basis_certified=false`. This is an explicitly defined
coordinate pullback of the captured kernel input, **not** a claim that its
historical initial/restart payload was physically dry-specific. In particular
NN's first-step volume profile is not repaired by relabelling the research
coordinate. A physical producer/initializer/restart migration needs a separate
versioned implementation for the complete host carrier history.

Divide/multiply roundtrip is checked against a predeclared 2-ULP limit, not
assumed bit-identical. In the selected 39-level case the maximum is 1 ULP for
NN and NR and zero for NC and NI. Source native dry density ranges from
`0.0898140` to `1.1295171 kg m-3`, so this is not a unit-density-only test.

## First-order products

For each number species at entry,

\[
z_i=\rho_d n_i,\qquad
\delta z_i=\rho_d\delta n_i+n_i\delta\rho_d.
\]

The unchanged KDM JVP receives this full state direction **and the original
forcing direction**. At exit, with volume output `y_i`,

\[
\delta n_i^+=\frac{\delta y_i}{\rho_d}
-\frac{y_i\delta\rho_d}{\rho_d^2}.
\]

For output cotangent `u`, divide its four number seeds by entry density before
the KDM VJP. If that VJP returns state covector `g_z` and forcing covector
`g_F`, the number input covectors become `rho_d*g_z,i`. Accumulate into DEN:

\[
\bar\rho_d=g_{F,DEN}
+\sum_i n_i g_{z,i}
-\sum_i\frac{y_i u_i}{\rho_d^2}.
\]

The first term is the kernel's own physical DEN dependence; the other two
are the entry and exit coordinate terms. All four species share each layer's
density covector. Other state and forcing covectors keep their original
coordinates. Density is the entry value for this fixed-geometry local
microphysics application, not a separately advanced end-of-step host density.

Handles own copied snapshots and the underlying recorded C handle. Foreign,
closed and value-only handles cannot supply JVP/VJP. A recorded number-only
`joint=False` call is refused because it lacks the required forcing partials.
Failure after kernel dispatch closes its handle. This opaque first-order
protocol does not expose HVPs or a live higher-order Torch graph.

## Composition with the existing observation verifier

`--native-number-admission <receipt.json>` explicitly selects v1 in
`harness.verify_microphysics_obs_ad`. The kernel wrapper is inserted before
the existing cleanup/finish/EOS/profile path; the final dry NC/NI now satisfy
the optical bridge's declared dry-specific input convention for this research
map. The internal kernel still uses `physics_variant=0,dry_number=0`.

The output schema changes to
`kdm6.microphysics_observation_ad.native_dry_numbers.v1`. It records the
receipt, internal volume inputs/outputs, entry density and physical-forcing
identity separately. The old legacy-raw ledger refuses this new schema, so
new dry-coordinate output is not silently interpreted as the earlier raw
number state. The default legacy schema and behavior are retained.

The actual native-column experiment and separately reported legacy replay are
in the [evidence report](../harness/evidence/native_number_boundary_2026-10-22/REPORT.md).
It includes nonunit-density MU/PH directions, number directions and a joint
mixed direction through actual KDM and RTTOV cost. NN probes avoid its known
entry clamp; locally zero responses are reported as zero, not identifiability.
The native NC input is zero; nonzero NC conversion and density terms have
independent affine-kernel coverage rather than a new native liquid case.

No host integration, unattended cycling, full RK/retained-memory adjoint,
closed physical budget or forecast-skill result is implied. The +40 s nominal
KO offset, unknown pixel time, fixed reference/surface/gas assumptions,
source-reconstructed P8W and prior whole-reference pressure discrepancy remain.
The older raw NCCN stress limit is not claimed solved by the coordinate map.
