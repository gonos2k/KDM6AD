# Bounded native-domain KO7 satellite case

The first case is the unchanged KO nominal `202507190000` scene and the MP137
checkpoint `2025-07-19_00:00:40`, based on main `792e890e`. It evaluates a local
20-second microphysics map and a satellite objective over all native columns.
This is not a host timestep, a forecast valid at 00:01, a time-window adjoint,
or a native assimilation cycle.

## Fixed case

| Item | Contract |
| --- | --- |
| Native domain | 234 × 282 = 65,988 columns, 39 mass levels / 40 interfaces |
| KDM partition | Original 128 × B512 plus one B452; no padding or boundary crop |
| Channels | AMI 10–16: WV073, IR087, IR096, IR105, IR112, IR123, IR133 |
| Physical map | `norm_actual`, actual-departure QR, existing cleanup and finish |
| Direct controls | Native moist-theta perturbation and dry QV mixing ratio |
| Held inputs | MU/PH, remaining initial state, geometry, surface, constants |
| Control scales | 0.2 K in native theta_m; 0.02 × baseline QV; QV=0 is frozen |
| Trial budget | One descent direction; alpha = 1, 0.5, 0.25, always from baseline |
| Observation loss | KMA-coordinate BT; Huber delta=1, sigma=1 K, zero bias |
| Prior | lambda=1 in scaled control coordinates; not a certified covariance |

Prep and post-finish EOS remain live functions of the controlled state.
In particular, holding MU/PH does not mean fixing the temperature-dependent
pressure and Exner paths. The native centers/interfaces are retained, with
the existing fixed upper reference: 26 full layers and one live partial layer
above the 39 native layers. O3/CO2 and other template auxiliaries stay fixed
on their recorded layer indices. Pixel UTC and original-provider navigation
are not certified; the nominal slot / checkpoint offset is recorded.

The source inventory records all 16 local KO channels at their actual raster
resolutions; only the seven selected channels enter this experiment. Model
source validity, profile validity, RTTOV quality, and objective support are
separate saved arrays. Every model column receives an output or exclusion
reason. The current mapping has 65,988 unique pixel owners, so weights are 1.
The objective helper also supports global 1/k ownership before partitioning.

## Number coordinates and exclusions

All original KDM rows remain in their full batch, including rows with negative
initial NC/NI. Such rows cannot enter the observation objective or T/Q control
set. BG is not a particle count and is diagnosed separately.

The held initial number payload is the recorded legacy/raw kernel coordinate.
The output optical coordinate is explicitly

```
NC_opt = NC_raw_out / rho_d_post
NI_opt = NI_raw_out / rho_d_post
```

The same live `rho_d_post` is passed to the cloud bridge. Its derivative
therefore includes the quotient and cloud-mapping paths. This is a research
coordinate definition, not a migration or certification of historical host
number units. Active mass/number pairs must pass the existing bridge checks;
invalid pairs are recorded rather than repaired with an invented floor.

## Streaming objective and derivative

For `x = x_b + S z`, freeze baseline support `m0` after the baseline profile
and RTTOV evaluation. With fixed owner weights `w`, use

```
Z = sum(m0 * w)
J = [sum(m0 * w * Huber_1(BT_KMA - BT_observed)) + sum(z_active**2)/2] / Z
```

Each block saves the unnormalized numerator and native T/Q gradient. Divide
once by the global Z after all blocks finish. In particular, do not add
per-block mean costs or give B452 the weight of B512. Unsupported columns and
zero-baseline-QV controls remain frozen.

One full-B recorded C ABI forward supplies a JVP and then a VJP. The Python
custom autograd boundary explicitly enables the internal C++ graph: custom
forward/backward otherwise inherit disabled Torch GradMode. The external
checkpoint supports one reverse pass and no higher-derivative contract.

The global native-input probe is defined independently of the gradient.
JVP/VJP dots are saved per block and globally. Independent central differences
use one sparse mixed T/Q direction on the active controls in blocks
0, 34, 40 and 128, with two epsilon values (16 extra KDM/direct-RTTOV forwards).
Unchanged blocks cancel; the symmetric prior is included. Saved K rows and
profile tangents permit independent BT/cost contraction replay.

The first pilot probes at epsilon=1e-3 and 3e-4 crossed observable cleanup and
cloud-presence branches and failed the independent FD check. Their outputs
remain preserved. At 1e-6 and 3e-7 the four-block pilot checks pass with the
same numerical tolerances and support. The example request uses those smaller
steps. This is a local, selected-direction check; it does not certify every
internal branch or arbitrary perturbations.

For a trial, form `d = -g_z / max(abs(g_z))`; retain exactly m0 and w. Newly
valid observations are diagnostic only. A loss of baseline-supported
profiles/channels makes a trial invalid. Branch changes alone do not reject a
trial. Evaluate every original block, then compare the actual global cost
using the fixed acceptance threshold `1e-10 + 1e-12*abs(J_baseline)`.

## Execution

The compact pipeline consists of case preparation, existing-map batch
composition, streaming execution/objective, and saved-result summarization:

* `harness/prepare_native_satellite_case.py`: input pins, original partitions,
  checkpoint-to-packet comparison, raw channel inventory and row metadata.
* `harness/native_batch_microphysics.py`, `harness/native_observation_batch.py`:
  prep → full-B KDM → cleanup/finish → EOS → profile → actual RTTOV-K/direct.
* `harness/native_satellite_objective.py`, `harness/run_native_satellite_case.py`:
  fixed support, numerators, products, bounded trials and immutable receipts.
* `harness/summarize_native_satellite_case.py`: full-index audit, metrics,
  gradients/increments and native-grid maps.

An example request is in
`harness/cases/native_satellite_case_20250719_0000.json`. Private input paths
can be overridden through its `paths` mapping. Run outputs must be outside
the public source checkout. Start with one worker and a finite RTTOV wall
limit; inspect measured RSS/time before increasing independent block workers.
Each worker and RTTOV child is restricted to one thread.

```sh
python -m harness.run_native_satellite_case --case-json CASE.json \
  --output-root PRIVATE_RUN --stage pilot --pilot-chunks 0 --workers 1
python -m harness.run_native_satellite_case --case-json CASE.json \
  --output-root PRIVATE_RUN --stage pilot --resume --workers 3
python -m harness.run_native_satellite_case --case-json CASE.json \
  --output-root PRIVATE_RUN --stage all --resume --workers 3
```

The first measured B512 RTTOV-K pilot exceeded a 180-second wall limit.
The next immutable source/request version uses a 900-second limit and a
K-only copied template (the original template is unchanged). Changing a wall
limit does not change the cost or derivative criteria. Failed attempts and
their original source snapshots are retained.

## Restart and completion

Chunk receipts bind case/source/runtime, stage/chunk, frozen baseline artifact,
and trial controls. Decode only the bytes whose SHA was checked. Publish a
completed receipt after its NPZ is durable; interrupted attempts do not count
as completed blocks. A different alpha, source, or input cannot reuse it.

`FINAL.json` is published only after all 129 blocks, positive global support,
global/per-block dot gates, sparse FD, the fixed trial budget, assembled outputs,
maps, summary hashes and final source recheck. A partial summary is retried in
a new directory. Completion distinguishes an accepted update from no acceptable
update; it never implies convergence or forecast skill. A pilot, input inventory,
zero-mask cost, incomplete gradient, or merely started process is not completion.
