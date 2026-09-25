# X2: selected native phase-change boundary

Base: PR #238's X1 verification-only pilot. This X2 change adds a diagnostic
operand tap in the fp64 oracle and separately measures the same input-selected
column in isolated mp37. Production defaults, private canonical source,
operational installed executable, C++/Fortran physics expressions, ABI, QC and
acceptance tolerances are unchanged.

## Input selection and evidence tiers

The retained 5 km forecast file SHA-256 is
`30ee8656cedf57cc827ad041e4ed8084d8bbf5afdbe0a21b28b33564544bca9f`.
At its 00:00:20 frame, 40 land columns meet the **input-only** rule
`245<T<273.15 K`, `qc>1e-6`, `qi>1e-8`, `nc>100`, `ni>0`. Ranking by each
column's largest `qc*qi` chooses zero-based `(j=96,i=172,k=21)`; no process
result or BT was used to choose it. The native coordinates are `(j=97,i=173,k=22)`.
The original and new control 20 s frames match raw bytes in all 17 selected
full-domain input variables, including state, pressure and geometry. The
public profile contains all 39 native center layers and 40 height interfaces.

Two evidence paths remain distinct:

* The fp64 **offline Python oracle** runs the public 39-level vectors. It
  measures both nonzero D2/D3 producer amounts at the phase boundary; an
  explicit `alpha_freeze=log(1e6)` diagnostic counterfactual exercises the
  optional combined DA cap. In that counterfactual `qc=3.392159123905003e-5`
  is entirely transferred to `qi`, with the same limited amount in the local
  latent-temperature expression. This is not a native controlled forecast.
* The **native mp37** control and diagnostic runs each integrate 40 s with
  `dt=20 s`, one MPI rank, one thread, 39 layers and the original 5 km inputs.
  The isolated diagnostic source copies the canonical source with SHA-256
  `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`;
  its generated source SHA-256 is
  `44fac3a847beb9aa9f53325ff66037a7e708b9a98e4b0e0768f66788a2b93b94`.
  It duplicates the raw request expressions **only to print them**, leaving
  the original `min` and state stores intact. The build reuses previously
  compiled host dependencies and the previously isolated uninstrumented mp37
  executable from the native-number experiment; only the diagnostic module
  and executable were newly compiled/linked here. This is not a complete
  fresh host build.
  The public JSON includes compile/link argument arrays from local command
  records and the `/usr/bin/clang -c` assembler command reconstructed from
  the executed invocation; generated assembly, object and executable hashes;
  and the common input manifest hash. The replayer pins all three command
  arrays and checks that each `-o` target feeds the next command. The
  assembler argv is not an independent execution log. These are provenance
  records, not a public-host rebuild capability.

Both native runs completed and their input manifests agree. At 0, 20 and 40 s,
the control and diagnostic histories have **254/254 common numeric variables
raw-bit equal**; the complete history files have the same SHA-256
`49bbda101a367d5eeb9c460e21c2304767311d274dddecb17a4ec39fe14f1d04`.
The first call's selected D2/D3 rates are zero. The second call records both
processes active at the same cell. Each six-record event contains D2 request
and store, D3 request and store, post-state-update, and final values. The raw
hex tokens are public in `native_phase_event_2026-09-24.json`; their complete
twelve-line payload has a code-pinned SHA-256. The full private RSL file's
hash is recorded separately; public replay cannot rehash that whole file.

## What the second native call measures

| Stage | Raw request = applied water amount | Raw request = applied number amount |
| --- | ---: | ---: |
| D2 contact freeze | `3.8382120914938175e-12` | `18.266846543327144` |
| D3 immersion freeze | `9.932539682138334e-11` | `315.140167922585` |

The number values retain **internal numerical units**; the host/kernel
physical number basis is still unresolved. All four D2/D3 mass and number
caps were evaluated but did **not** bind. D3 receives the exact f32 D2
post-state, including the
remaining `qc`; the requests are not treated as simultaneous independent draws.
The combined applied water amount is `1.0316360891287716e-10`.

The replayer reconstructs **all five** D2/D3 f32 state fields for each process,
including the mixed f32 coefficient/f64 rate temperature expression, and
matches their original hexadecimal bits. Subtracting rounded endpoints is
not identical to the applied amount: the measured `qc` loss exceeds the sum
of applied amounts by `5.187870892366641e-13`, while the `qi` gain differs by
`6.861538015123406e-19`. The stored `nc` loss is 336 versus an applied
number amount of about 333.407, an f32 large-reservoir rounding effect. These
are arithmetic observations, not new physical creation/loss estimates.

The recorded `xlf/cpm` coefficient is `290.51300048828125` K per unit mixing
ratio. From the recorded applied amounts, the D2 and D3 thermal RHS values
are `1.1150505112102705e-9` and `2.885531905526927e-8` K. **Both stored
f32 temperature updates are zero** at this cell: the local temperature ULP
is `1.52587890625e-5` K. Thus this event verifies the source expression's
operands and the exact rounded stores; it cannot resolve those tiny latent
increments from the saved T alone or discriminate a wrong heat coefficient
that also rounds to zero. It does not prove the full thermodynamic
energy budget.

Post-state-update and final values differ from the D3 post-state and from each
other. Their changes are kept as later processes, not added to the isolated
D2/D3 ledger. The first call's number branch is inactive; a first draft of
the diagnostic read an undefined number temporary there. The final instrument
records an explicit branch-validity bit and zero diagnostic placeholder for
inactive outputs, without initializing or changing the production variable.

## Validation and limits

The public replayers run on copied model profile vectors and on the measured
native hex tokens. Focused normal/mutation tests include missing or changed
records, branch validity, source-order stores, scope flags, and opt-in trace
noninterference. The new tests plus adjacent phase/control/sensitivity tests
passed **96/96** locally, with 18 pre-existing `torch.jit` deprecation
warnings. The local Python environment is 3.10.11, NumPy 2.2.6,
PyTorch 2.13.0; public replay does not independently rehash the private
NetCDF or rerun native mp37. The isolated native control/capture and original
input hashes were checked in this workspace; no RTTOV run was performed.

X2 closes **for this selected native event**. Native cap-binding phase events,
other thermal regimes, full enthalpy, physical number units, mp137 ABI,
operational ice-transfer P1, independent radiative accuracy and liquid
observation/cost approval remain separate. Existing liquid approval is 0/9.
