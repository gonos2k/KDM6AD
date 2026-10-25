# Actual binary32 analysis preparation and one-block value check

This packet resolves checklist C1/C2's preparation and synthetic protocol
boundaries and checks C3's value-evaluation connection on one original B512
block. It does not complete the full-domain iterative analysis or a native
host step. The original operational install is unchanged.

## Exact state application

For native moist-theta perturbation and dry-air QV, the wire rule is

```
wire = float32(requested_delta)
effective = background if wire == 0 else float32(background + wire)
```

The zero-component branch preserves the original signed-zero bits. The shared
`prepare_effective_analysis` predicts this rule, rejects invalid/overflowing or
underflowing requests, removes bitwise no-op pairs and components, and retains
strict `apply_pair` and acknowledgement checks for transmitted updates.

| Full-domain saved candidate | Count |
| --- | ---: |
| Requested nonzero T/Q pairs | 1,679,418 |
| Actually changed pairs | 561,407 |
| Requested pairs with no bit change | 1,118,011 |
| Changed theta components | 346,604 |
| Changed QV components | 508,839 |

The 66.57% pair no-op rate is a count of points, not the fraction of water,
increment amplitude or observation information removed. The persisted request
and `candidate - background` are separate recipes because their last binary64
bits can differ. The audit records both, without replacing the original request.

The optimizer-facing preparation uses fixed scales
`S_theta = 0.2 K`, `S_q = 0.02*qv_background` and computes

```
z_eff = (effective_state - original_background) / S
prior_numerator = sum(z_eff_active**2) / 2
```

Effective controls outside the total `[-1,1]` box are rejected. The current
candidate has no such escape: maximum absolute effective theta/QV controls are
0.7019901275634766 and 0.9999997359027764. Its effective prior numerator is
1.950563490552541 (original proposed-coordinate prior: 1.950564619163444).
This prior calculation alone is not an observation-cost reevaluation.

## Binding and command integration

`bind_satellite_control` maps `flat=j*nx+i` column controls to `(i,k,j)` and
requires the complete source checkpoint SHA. Equal T/Q and coordinate arrays
are insufficient: a changed MU/PH or other fixed input means a different
background. A non-square NetCDF test changes only MU, preserves T/Q and the
previous geometry fingerprint, and verifies refusal. The physical evaluator
also compares the candidate's full checkpoint SHA with the case source pin.

The live stepper reads native `THM_2` and `QVAPOR` once each, prepares effective
pairs, and uses cached arrays for command checks. It records requested/applied/
omitted counts and validates old and new acknowledgement bits. All-no-op
proposals produce an explicit no-applied-update status and an empty packet.
Synthetic process tests establish these code boundaries; they are not WRF runs.

## One actual full-B512 value pilot

The new pilot retains original block22 `[11264,11776)`, all 512 columns and
39 native levels. It evaluates the effective binary32 input widened exactly
to binary64 through the admitted `norm_actual + actual_departure QR` research
KDM map, cleanup/finish, live EOS/profile and direct RTTOV. It does not round
every subsequent physical operation to binary32 or certify the native host.

The completed v2 pilot retains all **2,037** baseline-supported observations.
At target flat11632, IR105 is:

| Quantity | K |
| --- | ---: |
| Historical baseline | 277.2934836204166 |
| Effective-input candidate | 265.8883686151449 |

The block's observation numerator is **30404.26723152965**. The complete
domain's observation cost was not reevaluated; the other 128 blocks have not
been replaced by inferred or cached new-candidate results.

V2 performs **1 KDM value forward + 1 direct RTTOV call**, with zero JVP,
VJP, RTTOV-K, optimizer iterations and host steps. V1 performed one forward
and one direct call but failed in KMA postprocessing because the frozen Python
source packet omitted its calibration JSON. Its prepared receipt, exact source
snapshot and failure receipt remain in `pilot/v1`; v2 includes and prechecks
that data dependency. Total new calls across both attempts are therefore
**2 KDM forwards + 2 direct RTTOV**, not one of each.

The exact executed pilot sources are in `pilot/execution_sources/`. Later
current-source admission checks additionally bind the full checkpoint and
validate z_eff before model evaluation; the historical snapshots are not
rewritten to pretend those later guards executed in v2.

## Remaining work

The CLI's original one-direction experiment is unchanged. This patch adds the
shared effective-state preparation/evaluation boundary, not an implemented
cumulative optimizer. Fresh actual-direction checks, accepted-point
relinearization, all-129-block reassessment, a correctly linked paired native
host step and second assimilation remain separate checklist items.

Current validation: **250** focused/related boundary tests passed including the
full-checkpoint guards; **5** independent audit tests passed. Ruff passes the
changed sources and new test modules. The publication manifest pins source,
inputs and outputs; these are local results, not yet GitHub CI or host evidence.

## Public arithmetic replay

The final audit is `audit_v6/audit.json`; its compact NPZ is below 50 MiB.
It reads the already published native background and support arrays. This mode
does not claim to reconstruct 129 private baseline receipts. An earlier private
cross-check did reconstruct them; superseded development outputs are archived
privately and are not the final public producer or result. Historical v1/v2
auditor producer snapshots were not retained, so those drafts do not supply
final provenance. The final current auditor and manifest are pinned exactly.

```sh
python -m harness.audit_effective_analysis \
  --public-baseline harness/evidence/native_satellite_case_2026-10-25/data/native_state_controls.npz \
  --output-dir /tmp/effective-analysis-replay-new
```

The output directory must be new. The reader hashes input bytes and decodes
those same bytes, rather than reopening a mutable path after checking its hash.
The replay executes zero KDM, RTTOV, host or optimizer calls.
