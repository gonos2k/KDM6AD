# PR395 native T/Q intake

`intake_native_tq.py` is a bounded consumer for the fresh `run_ss_case.py`
archive. Before opening the forecast, it requires `exit_code` zero,
`experiment_valid.json` with `experiment_valid=true` and `model_completed=true`,
and a matching valid `run_identity.json` bound to the archived effective namelist.
The producer run controls, actual `1x1` grid, KDM6AD physics selector, 20 s
step/output controls, and `ncmin` values are checked, and the producer's
effective-namelist hash must match the archived namelist bytes. Fixed-step is
checked from the effective namelist; the producer's CLI `fixed_dt` bit is not
required to be true. It then reads `Times` first and refuses
to extract native state unless all eight exact target values from 05:55:40
through 05:58:00 are present as WRF model-time labels. They do not certify
the observation pixel clock. It does not launch or rerun the model.

After the run has passed that gate, invoke it with the exact archive directory:

```sh
python harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py \
  --run-dir /path/to/case_nominal/runs/<completed-run-id>
```

It reads only selected `(j=86,i=48)` NetCDF hyperslabs for the eight frames.
The selected reader and raw-field preservation each read small hyperslabs; the
same variable may be read twice for different provenance records.
Before the archived reader converts a selected array to NumPy, the intake checks
the selected state, pressure, geometry, surface, and required vertical-vector
slices for NetCDF masks, fill sentinels, non-finite values, and expected lengths.
Masks elsewhere in the 5 km grid are outside this selected-column contract.
The private NPZ defaults to
`graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz`;
the public manifest is `INTAKE.json` in this directory. Both outputs are
create-once. The NPZ includes the exact background `State` and one-entry
`Forcing` expected by `capture_tq_state.py`, all eight native State/Forcing
frames, raw native hydrometeor fields, native centers/interfaces, the RTTOV
profile arrays, separate raw `PH`/`PHB` interfaces, and the selected-column
host eta dry-layer mass measure in `native_window_host_dry_mass_kg_m2`
([8,39], float32) plus `host_dry_mass_background_kg_m2` ([39], float32).
That measure follows WRF's `C1H/MU/MUB/C2H/DNW` eta mass formula; it is not
computed as EOS `rho_m * delz` and does not certify a process budget.

Native center pressure uses float64-first `P+PB`. Temperature, dry potential
temperature, and EOS density follow the archived selected-column reader. Native
`P8W` is a Python REAL(4) transcription of the archived host `calc_p8w` source;
it is not an output read from the forecast or a claim that the host routine was
executed. Raw `PH` and `PHB` are preserved independently.

For the RTTOV grid, all 39 model layers are replaced with the current native
column. Only levels above the native top come from the fixed retained RTTOV
cloud-test reference fixture; its paths and hashes are recorded. No external
model or reanalysis data is used. The manifest keeps scenario A as nominal
center-sample slot alignment and marks pixel time unverified, analysis
unexecuted, and science approval false.

The manifest also records the fresh run's executable/library provenance from
its run identity and the live loaded-library observation. It records the
compiled source snapshot (`30931e52…`) separately from the checkout observed at
launch (`8e5aab06…`); the current-head build claim is false. The stored
`current_worktree_head` value is the launch-time checkout, not a later
extraction-time HEAD.

Once that native intake is ready, the bounded one-shot analysis driver is:

```sh
source /private/tmp/KDM6AD-research-rc-20261007/env/bin/activate
python harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py
```

The driver records the active Python/Torch/NetCDF versions and requires the
intake/observation hashes. It runs the existing `run_single_column_analysis`
through the state-capture adapter with `obs_time=1`, one 20 s forcing,
`max_iter=3`, sigma 1 K, zero bias, Huber delta 1 K, potential-temperature
prior 0.8 K (physical-temperature scale is 0.8 times Exner), lower-12
qv log prior 0.08, other state controls zero, parameters pinned, and
`ncmin_land=ncmin_sea=10`. It creates one durable exclusive run marker; later
invocations stop before H/RTTOV. Initial `Jo0` comes from the first zero-control
closure evaluating `H(M(xb))` at the nominal 05:56:00 slot. The separate
quality probe has an all-zero cost mask and cost 0; saved probe BT is
recombined with the actual frozen mask only as a cost cross-check. It does
not compute a direct `H` on the native
05:55:40 frame. The copied paired case supplies coefficient/template/static
surface parameters only; pressure, interfaces, T/Q and O3/CO2 profiles are
rewritten from the intake, cloud profiles come from each current State, and
the AMI geometry plus native dynamic surface are explicit per-H overrides.
The intake reads the run archive's effective `namelist.input` and requires
`ncmin_land=10`, `ncmin_sea=10`; it checks the archived wrapper source's two
argument-forwarding statements and records both hashes without generalizing
that those values are silent wrapper defaults.
The observation packet still does not establish per-pixel time or scientific
matchup acceptance.

The pre-edit Graphify query returned generic native/temperature/validation
nodes and no usable producer-to-consumer path. The intake and analysis edges
in `graphify-out/pr395-native-intake-green/semantic.json` are manually grounded
in the named reader, runner, observation receipt, and capture-helper sources;
the root refreshes the shared derived graph after the active evidence files
are complete.

`continue_case.py` is a detached continuation for the already-running exact
case. It never starts or restarts WRF. It waits for the runner's last-written
completion marker, pins consumer source hashes, and calls the gated intake and
analysis once. A durable claim marker prevents duplicate continuation, and
any invalid native run, changed source or consumer failure stops the sequence.
The public success/failure receipts remain the result authority; starting the
continuation is not a statement that any target output or analysis exists.

After analysis succeeds, the continuation invokes `diagnose_saved_state.py`
using the exact one-shot capture receipt token. It reads the bound private
arrays without evaluating M or H again. The report separates host/local
potential-temperature and Exner temperature effects and water increments on
the fixed first-frame host eta mass measure. Boundary/external fluxes remain
unmeasured; this is not a closed water budget or an attribution of the
host/local difference to microphysics error. A diagnostic failure preserves
the accepted capture receipt and is recorded separately, without retry.
