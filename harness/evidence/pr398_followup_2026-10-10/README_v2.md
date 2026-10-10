# PR398 V2: saved-frame time and centroid viewing-angle sensitivity

The earlier, non-executed V2 draft with a stale driver hash is preserved as
[`PREDECLARED_v2_draft_unexecuted.json`](PREDECLARED_v2_draft_unexecuted.json).
The authoritative current plan is [`PREDECLARED_v2.json`](PREDECLARED_v2.json),
whose driver hash matches `run_time_geometry_sensitivity_v2.py`.

`run_time_geometry_sensitivity_v2.py` defaults to `--plan-only`. It writes
[`PREDECLARED_v2.json`](PREDECLARED_v2.json) before any new BT is produced. The
six predeclared cases cross native saved frames 1, 4, and 6 (`05:56:00`,
`05:57:00`, `05:57:40`) with two source-supported viewing centers:

- the fixed AMI candidate pixel center and its retained GEOS metadata;
- the selected saved native cell's own `XLAT`/`XLONG`, passed only to the RTTOV
  viewing-geometry builder.

Both geometry paths keep native `HGT` as the RTTOV surface elevation. The two
later labels fall inside the observation receipt's conditional file-level AMI
scene interval only under its stated epoch/synchronization assumption; this is
not verified per-pixel UTC. No state interpolation occurs.

Every row evaluates `H(native saved State_t, Forcing_t)`, with the same
`j=86, i=48` model column and the row's own saved State, pressure centers,
REAL(4)-transcribed `P8W` interfaces, surface values, and optical dry density
`rho_d=Forcing.rho/(1+State.qv)`. The driver rebuilds that frame's 39-native
plus 27-upper-reference RTTOV profile, updating isolated pressure and trace-gas
files before each H call. It uses the same seven AMI channels, dry-number and
KMA BT options, and 10/10 moment floors. It never runs WRF or KDM M.

The fixed quality mask is taken from the accepted PR395 initial zero-control
closure and must remain all seven channels. Every case must return zero RTTOV
quality flags on all seven channels before the driver reports Huber cost with
sigma 1 K, zero bias, and delta 1 K. It never shrinks support in response to a
new H result. The cost is recomputed from returned BT with the prescribed mask;
no callback's placeholder cost is used.

`ami_geometry()` computes view angles at the latitude/longitude supplied to its
ellipsoid line-of-sight calculation and records surface elevation separately.
The comparison therefore measures sensitivity to the two centroid locations
used for RTTOV viewing angles while holding the same native column and actual
surface HGT fixed. It does not move the model column, infer a pixel time, apply
parallax, or establish footprint overlap. The observation receipt's cloud-top
height is not used as surface elevation.

The plan additionally pins the current intake, target, mask, full six-case
matrix, profile/geometry sources, baseline preflight, original upper-reference
files, static skin file, RTTOV template files, executable, and coefficient.
The executor recomputes those bindings and rejects stale or changed plan inputs
before creating its one-shot marker. It ran cases serially, with one external
RTTOV call per row and no retry. The immutable V2 predeclaration document
keeps status `PREDECLARED_NO_RTTOV_EXECUTED`; the separate
`graphify-out/pr398-centroid-viewing-angle-v2-2026-10-10/private/RESULT.json`
records the one completed batch. It contains six returned H cases, all with
zero model-quality flags on the fixed seven-channel support. The result records
zero KDM M and backward calls and keeps scientific acceptance false. The
`STARTED_ONCE.json` marker means this batch must not be run again. These
diagnostics do not establish per-pixel observation time, footprint overlap,
parallax, or scientific matchup acceptance.
