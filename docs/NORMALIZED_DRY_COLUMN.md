# One normalized dry-number column experiment

Run the same **fp64 selector 2 / dry-number 1** map for the graph forward,
value-only forward, JVP/VJP and independent centered differences. This is an
experimental microphysics diagnostic. Physical number/threshold policy, host
transport, RTTOV accuracy and observation approval remain open.

## Explicit Python window research mode

`WindowConfig(normalized_dry=True)` and
`WindowLinearization(..., normalized_dry=True)` select the existing normalized
ice handoff, conservative sedimentation and dry-number boundary together.
Collection, forward execution and adjoint recomputation use the same selection.
Omitting the flag preserves the legacy transition. The value-only parallel
window also accepts the flag explicitly.

`run_fulldomain_analysis(..., normalized_dry=True,
observation_coordinate="kma_v3_0")` passes this model choice to its window and
selects dry-number optics plus KMA BT/K in the all-sky worker. The first supported
configuration requires channels 8–16, Huber delta=1, diagnostic sigma=1 K, zero
bias and no pseudo-RH. A supplied binary `ColumnObs.channel_gate` narrows the
frozen QC-valid support. If omitted, all background/observation QC-valid channels
are kept; the retained experiment's seven-channel gate is not an automatic default.
The density used by optics is frozen from the initial background and forcing;
it is not recomputed from the trial or slot humidity. This contract differs
from the live entry-density one-hour experiment.

Supply `grids["cloud_fixture_case_dir"]`; any retained clear partition also
requires `grids["clear_fixture_case_dir"]`. The shared optical center grid must
retain the exact native center pressures of every selected column, possibly with
declared reference layers above the model top. Different native column grids
are rejected in this mode. Native interfaces are authoritative caller inputs
in `p_half`: this API cannot reconstruct or certify them from center pressure.
The generic OSSE shard builder likewise requires an explicit fixture and native
grids; its synthetic observations use the same KMA runner as its model.
In this mode both reference-blend widths are zero: reference T/Q are used only
strictly above the native model top, while native T/Q and their sensitivities
remain model-provided. Legacy callers keep their historical positive widths.
The normalized OSSE worker uses the cloud-enabled evaluator; the older generic
`run_osse_sensitivity` API remains clear-sky only.

These choices do not calibrate the thresholds, bias, background covariance or
observation errors. Reports label the consumed number/BT/density settings and
retain false scientific-observation and operational approval. No host writeback,
restart or cycling is performed by this research mode.

The [corrected native-path experiment](../harness/evidence/REPORT_native_KMA_window_2026-10-05.md)
uses the original native grid to select one C5 column, executes a two-iteration
single-step diagnostic optimization, and separately checks a 180-step recomputed
window against independent cost differences. It does not optimize the entire
domain or certify a time-collocated observing sequence.
The [PR #373 audit](../harness/evidence/CHECKLIST_pr373_team_audit_2026-10-05.md)
preserves the original blended-operator evidence and records the missed paths
and their corrections separately.

The [signed inventory interpretation](../harness/evidence/REPORT_native_analysis_inventory_2026-10-05.md)
separates the initial analysis water/heat changes from the two model trajectories
on a declared fixed measure. These are conditional endpoint inventories, not
closed boundary-flux budgets. The report's `cloudy_clear` label is the existing
IR105 threshold proxy, not an independently observed clear scene.
The [host-coordinate mass audit](../harness/evidence/REPORT_native_host_mass_reference_2026-10-06.md)
distinguishes the snapshot hybrid dry-mass measure from diagnostic density times
height. The latter remains the declared optical/inventory policy; this audit
does not silently replace it or close the host flux/enthalpy ledger.

```sh
python oracle/scripts/run_normalized_dry_column.py \
  --input /path/to/native_5km_history \
  --library /path/to/libkdm6_c.2.0.0.dylib \
  --time-index 1 --i 3 --j 272 --output /path/to/new_result
```

The input is the retained model's native 5 km NetCDF frame. Coordinates are
zero-based; layers remain in native bottom-up order. The existing frame reader
derives temperature, pressure/Exner, moist density and thickness from the saved
fields. This is a snapshot-derived offline call, not a replay of a host physics
call's exact staged operands. QNCCN is read as stored, with no synthesized CCN.

The fixed candidate uses dt=20 s, existing ProgB behavior and internal volume
number thresholds `ncmin_land=ncmin_sea=10`. The dry-number boundary interprets
the four input QN fields per kg dry air; that interpretation is conditional and
does not settle S2. The selected direction is entry `qi` plus 1% entry `qv` and
`nc`; zero reservoirs remain unperturbed. VJP uses `u=Jv/max(abs(Jv))`. The
centered width is 1e-4. Each field's max-norm relative JVP/FD difference must be
at most 1e-5; JVP/VJP duality must be at most 1e-12. Endpoint spacing is reported
as a quantization estimate and does not relax the FD gate. Branch certification
is not measured by this command.

The command rejects nonfinite/negative states, nonpositive forcing, unsupported
mass/number or mass/volume pairs, an empty ice profile, invalid coordinates and
an existing output directory. It saves `arrays.npz` (inputs including XLAND,
graph/value-only outputs, both FD endpoints, direction, JVP/VJP/FD arrays) and
`result.json` (configuration, artifact hashes and checks).
A failed numerical check saves an explicit failure result and exits nonzero.
No observation cost or operational approval is granted by a successful run.

## fp64 NCCN return arithmetic

Build the library from the same source revision used by this command. The
opt-in dry-number fp64 path preserves an exact zero volume update with
`n_in + (N_out-N_in)/rho_d`; its live delta keeps a nonzero process tangent at a
zero-valued update. Every representably nonzero update still uses direct
`N_out/rho_d`. This is a numerical representation change for NCCN only. f32,
other number fields, selectors and physical process formulas are unchanged.

A successful result requires the same strict paired-state admission and
numerical gates as before. Results now expose numerical input preconditions,
executed finite outputs, strict pairs and unapproved observations separately.
KDM's defined fallback states may be numerically executable yet rejected by
this diagnostic's support rule. The rule is not weakened to admit them.

The original retained history column (i=3,j=272,time=1) passes after rebuilding
this source, while its archived direct-return failure remains evidence for the
older library. Library ABI version 2 alone cannot identify the return arithmetic;
use source revision/library hash. The numerical selector still has neighboring
floating quantization; return-mask locality measured in the selected native
case does not certify every microphysics branch, physical number basis or
observational/operational accuracy. No releases or deployment are included.
