# PR398 saved-frame time and profile-elevation sensitivity

> **Superseded, not executed.** This V1 plan used a CTH-as-surface-elevation
> assumption that the RTTOV geometry source does not justify. Its predeclaration
> remains preserved for review and is marked in
> [V1_WITHDRAWN.json](V1_WITHDRAWN.json); the old runner entrypoint fails closed.
> The revised centroid viewing-angle experiment
> is [README_v2.md](README_v2.md) with
> [PREDECLARED_v2.json](PREDECLARED_v2.json).

`run_time_geometry_sensitivity.py` defaults to `--plan-only`. The generated
[`PREDECLARED.json`](PREDECLARED.json) pins a six-case matrix before any new BT
is produced: three native saved frames (`05:56:00`, `05:57:00`, `05:57:40`)
crossed with two RTTOV profile-elevation inputs. The driver reads the existing
hash-bound eight-frame native NPZ and fixed observation packet; it never opens
the forecast or runs WRF/KDM6.

Every case evaluates `H(native saved State_t, Forcing_t)`. Each time uses its own
native State, pressure centers, REAL(4)-transcribed `P8W` interfaces, surface
values, and dry optical density `rho_d=Forcing.rho/(1+State.qv)`. It rebuilds
the saved reader's 39-native-layer plus 27-upper-reference RTTOV grid and updates
the case's pressure and trace-gas vectors for that frame. The copied RTTOV
fixture supplies the coefficient/test-driver and static sea-surface parameters.
The call is value-only: RTTOV returns BT/quality (and its usual K result), but
the sensitivity driver does not run a backward or a KDM integration.

The quality gate uses exactly the seven-channel mask recorded by the accepted
PR395 initial zero-control closure; it never recomputes a smaller subset. The
same AMI channels 10–16, DQF, 1 K sigma, zero bias, and 1 K Huber delta apply to
every row. A cost is emitted only when all seven RTTOV quality flags remain zero.

The nominal `ami_geometry` line of sight is derived from the fixed AMI candidate
center and retained GEOS metadata. The native WRF `HGT` is the RTTOV profile
elevation; it is 0 m for the three selected frames. The second case substitutes
the receipt's CTH value, 587.7369384765625 m, into RTTOV's `&angles.elevation`
field while holding the candidate coordinates, viewing angles, column, surface,
and atmospheric inputs fixed. The receipt does not establish the CTH vertical
datum. This is an explicitly conditional RTTOV profile-elevation sensitivity,
not a cloud-top parallax calculation, corrected geolocation, or footprint
test. No VIIRS corrected coordinate is used and no native column is reassigned.

The two later saved labels lie inside the observation receipt's conditional
file-level AMI time interval only under its stated epoch/synchronization
assumption. That interval is not verified per-pixel UTC. No native state is
interpolated, and the results must not be called `H(M(xb))`; that is the
separate PR395 one-step analysis slot.

After reviewing the predeclaration, the one permitted batch command is:

```sh
source /private/tmp/KDM6AD-research-rc-20261007/env/bin/activate
python harness/evidence/pr398_followup_2026-10-10/run_time_geometry_sensitivity.py --execute-one-shot
```

Execution has a durable one-shot marker, runs cases serially with one RTTOV
call per matrix row, and records results under
`graphify-out/pr398-time-geometry-sensitivity-2026-10-10/private/`. It has no
retry path. This packet's current plan has `status=PREDECLARED_NO_RTTOV_EXECUTED`;
it contains no sensitivity BT results and makes no physical matchup or science
acceptance claim.
