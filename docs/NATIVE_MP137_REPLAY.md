# Native MP137 checkpoint/replay audit

This audit follows the P0 native-forward work in
[the coupled-window design](COUPLED_MP137_DA_DESIGN.md). It exercises an
installed MP137 host and an isolated, two-module source rebuild. It does not
implement `HostTransition`, assimilate observations, or supply full-host AD.

## Executed case and attribution

- Public base: `ceaa3bb7400fffb88c6948136edccc9c52485f4d` (PR #422).
- Existing native input: 234 × 282 columns, 39 mass / 40 interface levels.
  No external model data were acquired or substituted.
- Model date: 2025-07-19 00:00 UTC; dt = 20 s; continuous end = 00:04.
  History and restart records every 120 s; replay starts at 00:02 and ends
  at 00:04. There are twelve continuous steps, six replay steps.
- `mp_physics=137`, `no_mp_heating=0`, `use_theta_m=1`,
  `use_q_diabatic=0`, `tree_canopy=2`, surface layer / land / urban = 1 / 2 / 1.
- Each case uses `harness/run_ss_case.py`, one MPI rank and one thread.
  Separate cases may run concurrently. KDM and its installed library are
  unchanged by the initializer patch.
- Installed executable SHA-256:
  `676223e8d61d23456d4ac83713bff0283ea08b1e71776b7f8885b062d97f801b`.
  Installed KDM library SHA-256:
  `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7`.
- The installed executable's complete source/build correspondence is not
  attested. The isolated rebuild replaces only `module_physics_init.o` and
  `module_sf_urban.o` in a copy of its 376-member archive. All other archive
  members are byte-identical. This is not a clean rebuild of the host.

Private inputs, sources, binary snapshots, run receipts, full comparisons and
failed-attempt logs are preserved under the canonical local path
`host/research_evidence/mp137_native_replay_20261020/`. They are not present in
a public clone. In particular, `PREPARED.json` binds resolved inputs, binaries
and the runner; `ACTIVE_SOURCE_REVIEW_SNAPSHOT.json` pins source-review files;
the build manifests and `ARCHIVE_MEMBER_DIFF.json` identify the isolated changes.

## Failure localized to restart initialization

The unmodified installed host reaches 240 s successfully. Two restarts from
the same copied 120 s checkpoint produce raw-bit identical terminal values
for all 652 checkpoint variables. However, they differ from the uninterrupted
integration. Loaded `H_DIABATIC`, `QV_DIABATIC`, `QC_DIABATIC` and `QNCCN`
match their checkpoint values exactly. Successful restart I/O alone therefore
does not establish replay equivalence.

A dump immediately after restart initialization narrows the serialized-state
differences to seven fields:

| Field | Changed values | Maximum absolute change |
| --- | ---: | ---: |
| `Z0` | 27,773 | 4.716176599264145 m |
| `ZNT` | 37,212 | 4.716176599264145 m |
| `G_URB` | 1,277 | 414.1875 |
| `QC_URB` | 1,277 | 0.012381352484226227 |
| `RN_URB` | 1,277 | 515.7046508789062 |
| `SH_URB` | 1,277 | 199.85330200195312 |
| `LH_URB` | 2 | 14.040055274963379 |

The active private source has corresponding assignments:

- `phys/module_physics_init.F:1442`: tree-canopy reconstruction is outside
  the non-restart guard and writes `Z0`/`ZNT` on both land and water.
- `phys/module_sf_urban.F:2737` and `:2838`: urban fluxes and canopy humidity
  are reset before the routine's non-restart guard.
- `phys/module_sf_sfclay.F:493`: `ZNT` enters surface-layer logarithmic
  exchange factors. This is a prognostic consumer, not just an output field.

These line numbers refer to the pinned, unmodified active-source snapshot.
All seven fields have restart registration. Radiation scheduling was checked:
RRTMG runs at 0 s in the continuous case and is not rerun during 120–240 s.
The loaded held-radiation arrays also match the checkpoint. An extra restart
radiation call is not the demonstrated cause.

This restart-file comparison differs from the history-at-entry comparison:
the latter changes `FOGFRAC_SFC`, `NOAHRES`, `REFL_10CM`, `RHO_ICE`, and three
`VIS_*` fields. Those history diagnostic differences are not explained by
the seven serialized-state overwrites and remain a separate coverage limit.

The dump uses `write_restart_at_0h=true`, which means **dump and shut down**,
not “also dump, then integrate.” The installed executable subsequently returns
14 after MPI finalization. Its dump is used only to inspect loaded state; it
is never counted as a valid integration. All integration cases use this flag
as false. The actual namelist keys are `rst_inname` and `rst_outname`, with
distinct copied input and output files. Saved timers are retained with
`override_restart_timers=false`.

## Opt-in initializer correction

[`patch_restart_state_init.py`](../harness/patch_restart_state_init.py) guards
only the three identified initializer blocks with `.not.restart`. Cold-start
assignments remain the original assignments. Restarts retain the saved
roughness, canopy humidity and urban flux fields. The tool does not modify
KDM, the ABI, RK integration, or a physical rate.

Run check-only first against an isolated private source/build copy:

```sh
python3 harness/patch_restart_state_init.py --host-root /path/to/isolated/host
python3 harness/patch_restart_state_init.py --host-root /path/to/isolated/host --apply --report patch.json
```

Both source contexts must pass preflight before replacement. Fully applied
state is recognized; drift, duplicates and mixed states are refused. Caught
replacement failures trigger rollback. A hard interruption between the two
replacements can leave mixed state, which a later invocation refuses. The
tool does not rebuild or install the host. The operational private tree and
installed executable/library were left unchanged in this audit.

The corrected initialization dump matches all 652 checkpoint variables by raw
bits and contains finite numeric values. The subsequent integrations complete
with return code 0 and valid input/executable/library receipts. Results at the
same saved timestamps are:

| Comparison | Variables | Raw-bit result |
| --- | ---: | --- |
| Corrected load at 120 s vs saved checkpoint | 652 | PASS |
| Unpatched two-module rebuild vs installed restart at 240 s | 652 | PASS |
| Corrected cold integration vs original continuous checkpoint at 240 s | 652 | PASS |
| Corrected cold integration vs original continuous history at 240 s | 261 | PASS |
| Corrected restart vs corrected continuous checkpoint at 240 s | 652 | PASS |
| Corrected restart vs corrected continuous history at 240 s | 261 | PASS |
| Corrected restart-entry history vs continuous history at 120 s | 261 | FAIL: `FOGFRAC_SFC`, `NOAHRES`, `REFL_10CM`, `RHO_ICE`, `VIS_SFC`, `VIS_SFC_CAPPED`, `VIS_SFC_RAW` |

Each checkpoint comparison covers 322,426,586 numeric elements; each history
comparison covers 97,487,929. The passing comparisons have zero mismatches and
finite numeric data. A separate scan of the 120 s input checkpoint found no
occurrence of NetCDF's standard default fill values. The comparator also
rejects declared missing sentinels and nonfinite data as scientific passes.

`VARIANT_VERIFICATION.json` therefore has `terminal_replay_pass=true` and
`complete_history_pass=false`. The narrow result is restored **terminal**
replay for this four-minute case and decomposition, with cold-forward
noninterference. It is not general restart equivalence for other windows,
physics schedules or decompositions. The public
[summary receipt](../harness/evidence/native_mp137_replay_2026-10-20/summary.json)
includes compact results and hashes of the private evidence manifests.

## Tendency memory reaches the native state

An independent copy of the installed host's 120 s checkpoint changes exactly
one `H_DIABATIC` element by float32 `0.0010000000474974513`. All other checkpoint
variables are bit-identical. This is a value-only intervention, not a DA
control or analysis. By 240 s, the state changes, and the source-form terminal
diagnostics change in 39,512 pressure elements (maximum 3 Pa) and 34,902
density elements (maximum `2.5212764739990234e-5 kg m-3`).

Pressure here is `P+PB` and density is `1/(AL+ALB)`, computed from terminal
checkpoints. These are not captured actual next-call forcing tuples or
derivative evidence. Together with the reviewed native producer/consumer
path, the intervention demonstrates that retained heating memory affects
the native forward transition. It does not certify every applied budget,
full forcing sensitivities, RTTOV pressure sensitivities or optimizer closure.

The literal `use_theta_m=1` finish formula also needs preservation in any
future derivative backend. With dry potential temperature `theta`,
`alpha=R_v/R_d`, `dtheta=theta_new-theta_old`, `dq=q_new-q_old`, and applied
limited increment `m`, the reviewed source writes

```text
theta_m_after = theta_old*(1+alpha*q_old)
              + m*(1+alpha*q_new) + alpha*dq*theta_new
H_DIABATIC   = (m*(1+alpha*q_new) + alpha*dq*theta_new) / dt
```

Here `theta_old` is the full dry theta saved in `h_diabatic` by prep before
microphysics, and `q_old` is its saved `qv_diabatic`. `theta_new=th_phy` and
`q_new=qv` are sampled at finish before its host-coordinate update. The
equation's `theta_m_after` means `t_new_after+T0`; the stored perturbation
`t_new` receives the expression minus `T0`.

Thus the same `h_diabatic` array temporarily means full dry theta in prep and
an applied heating tendency after finish. The replay files here are complete
timestep checkpoints; this audit does not authorize a checkpoint in the middle
of that reuse. The saved `ITIMESTEP` is 6 at 120 s and 12 at 240 s. The wrapper's
`ITIMESTEP==1` CCN initialization is not repeated at the restart. A future
initial-state/control derivative must include that initializer when it is
actually active, rather than assuming every initial CCN perturbation is used.

This is a source transcription, not a physical conservation verdict or a
complete installed-binary attestation. Relative to simply mapping
`theta_new*(1+alpha*q_new)`, the difference is
`(m-dtheta)*(1+alpha*q_new) + alpha*dtheta*dq`. Do not replace this executed
map by a generic theta conversion while claiming legacy parity. The future
same-coordinate tendency JVP/VJP must still include the input `-I/dt` term,
plus the actual coordinate transformation and limiter derivatives.

## Verification and remaining gates

Native comparisons use `compare_frames()` in
[`native_replay_compare.py`](../harness/native_replay_compare.py). Frame indices
are explicit (continuous history frame 2 vs restart frame 1 at 240 s), while
the selected `Times` value must be identical. All variables and non-time
dimensions are checked; raw field equality is distinct from whole-file
metadata/file-byte equality. The run receipts bind the execution context.

The public focused suite covers explicit timestamp/frame pairing, complete
variable inventories, raw signed-zero differences, missing/nonfinite values,
patch preflight, idempotence and rollback after an injected second-file failure:

```sh
python3 -m pytest -q harness/tests/test_native_replay_compare.py harness/tests/test_patch_restart_state_init.py
```

Result: **18 passed**. Native files are unavailable in a public clone; these
tests do not substitute for the private native comparisons.

The native integrations and terminal comparisons are complete for the case
above. The restart-entry diagnostic history discrepancy remains open.
Full-host state/control encoding, `HostTransition` integration, forcing
JVP/VJP, pressure-aware observations and full-cost directional differences
remain unimplemented. Existing full-host scope gates stay closed. The earlier
fixed-forcing KO DA remains paused; no observations were assimilated by these
native cases.
