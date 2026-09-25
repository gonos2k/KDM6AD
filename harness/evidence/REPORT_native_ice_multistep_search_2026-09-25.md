# S4: complete 10-minute and one-hour native ice-substep censuses

## Result and attribution

The retained 5 km, 39-level initialization was run for a **predeclared 600 s**
at the original fixed 20 s timestep, one MPI rank and one thread. It used the
same isolated normalized-mp237 G4 census executable SHA-256
`799e389e4a5ae3e032607cb4bba59d881184d74798e90e63ee77f426381d6e3c`.
The three active canonical inputs have the same hashes as G4's older symlinks;
the new case links to the private host under the canonical workspace. Only
the run horizon, history interval (600 s) and restart-output interval (999
minutes, beyond this run) differ from the prior 40 s case. These output
controls keep the measured run below available disk space; they are recorded
as part of this experiment, not silently treated as identical namelists.

Two completed runs use the same binary and effective physics configuration:
one with census logging disabled, one with logging enabled. Both runner
receipts report valid `1x1` execution and identical canonical input SHA
`12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf`.
Their complete history SHA-256 matches exactly:

```
f1a45c7b8293994ce17fb6a7c1699f454dbb9e03f3a46cae3c269eac7efaf963
```

At the saved initial and terminal frames, all 253 numeric fields have equal
dtype, shape and array bytes, and `Times` agrees. This is evidence of
instrumentation noninterference for these outputs, not proof that every
internal temporary is unchanged. The full control/capture run identities,
source/build digests, output hashes and scope flags are in
`native_ice_multistep_10min_2026-09-25.json`.

## Complete SELECT/CONSUME coverage

The independently declared schedule is 30 outer steps × 280 owned `j` rows
× 232 owned `i` columns = **1,948,800 column-steps**. The compressed public
rank-0 log, `native_ice_census_10min_rank0_2026-09-25.txt.xz`, contains one
SELECT and its actual ice-loop CONSUME for every planned column-step. The
streaming replayer rejects missing/duplicate owners and ordinals, extra
steps/coordinates, wrong rank, malformed or unsupported mstep and changed
fixed-file provenance. It reports exactly 1,948,800 SELECT plus 1,948,800
CONSUME, with `mstep_i=1` for **every** selection. There is no `mstep_i>=2`
witness on this 600 s horizon. The original 0–40 s G4 census was also all
one, but its different output schedule is not reused as a bitwise comparison
for this longer run.

The public archive is lossless, XZ-compressed from the raw 91,065,600-byte
log. Its SHA-256 is pinned by `replay_native_multistep_10min.py` and the
evidence JSON. That replay checks public event arithmetic and recorded run
facts only; private NetCDF/source/executable hashes were inspected during
this run but are not independently re-read by a public clone. The streaming,
fixed-evidence and retained G4 contract checks pass together (20/20;
warnings as errors), including both gzip and XZ parser paths; Ruff passes.

## Separately predeclared one-hour extension

Before this longer run, `native_ice_1hour_plan_2026-09-25.json` fixed the
same retained input,
normalized-mp237 executable, 20 s timestep, 1×1/one-thread execution and a
3,600 s horizon. History is saved at 0 and 3,600 s; restart output is placed
beyond the horizon. Capture and later-added logging-off control both completed
with exit code 0. The decision to add that control after the no-witness
capture is recorded separately in
`native_ice_1hour_control_addendum_2026-09-25.json`; the original
`native_ice_1hour_plan_2026-09-25.json` remains unchanged. The local plan
records were made before their respective runs but have no independent
external timestamp authority.

The lossless XZ archive
`native_ice_census_1hour_rank0_2026-09-25.txt.xz` expands to the
562,763,520-byte rank log. Under the independent 180-step × 280-row ×
232-column plan, **11,692,800 SELECT and 11,692,800 CONSUME** records are
complete, with all `mstep_i=1` and no later-substep witness. The compressed
SHA-256 is `f7a4d6666f69b8f217eb5e6c4307f4441dabb46ad9d86e00a0985f432b33c4ad`;
the raw log SHA-256 is `6ab8eba23cb7234cf330a92418ea95e8205dc10b8e1dfac5fb28fd8933657ef1`.
Its first 91,065,600 bytes are identical to the independently captured 10
minute log, and the initial saved numeric frame also matches across the two
capture horizons. At the 3,600 s saved frame, `QICE` and `QNICE` are both
positive in 238,956 cells, so absence of all ice at the terminal time is not
an explanation for the all-one selection. That snapshot does not show which
earlier cells actively transported ice or what their `v/dz` values were.

The separate hour-archive test replays the complete public XZ log and passes
under warnings-as-errors. The full-hour control and capture share canonical
input SHA `12e132ec...`, executable SHA `799e389e...`, runner SHA
`175ade71...` and effective namelist SHA. At saved 0 and 3,600 s frames,
all 253 numeric fields and `Times` are raw-byte identical. Their complete
history SHA-256 is
`ddf3931dd7bd514d43455b4c83540e00e0cc14c258cbeab40148dbd4e17c639c`.
The public fixed hour replay pins the plan/addendum file hashes, run IDs,
input/build/output identities, 11,692,800-row schedule and negative approval
flags. It checks the public XZ archive and the first-ten-minute raw prefix;
the private NetCDF equality is a recorded direct check, not independently
reopened by a public clone. Complete metadata are in
`native_ice_multistep_1hour_2026-09-25.json`.
The focused 10-minute, one-hour, streaming-census and G4 contract suite passes
24/24 tests with warnings treated as errors; Ruff also passes.

## What remains open

`mstep_i=1` is the selected loop count, not a claim that all selected cells
contained active ice or moved ice number. The census does not include raw
fall speeds, per-substep `v/dz`, actual capped departure/arrival, or surface
export. S4 therefore remains **OPEN**. The result excludes only a naturally
selected second ice substep in this one retained state over 0–3,600 s. It does
not justify changing dt or prescribing fall speed while calling the result
the same meteorological case. Neither control/capture pair executes the
missing branch.
