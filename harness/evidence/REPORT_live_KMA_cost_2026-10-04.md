# Live KMA-coordinate forward, cost and first-order VJP

Baseline: PR #369, `7c7534beadc9e47fbdffcf9bcd5f488015f5f747`.
The selected live numerical connection is now implemented and tested. Physical
product/SRF compatibility and scientific observation-error approval remain OPEN.

## Calculation

`make_live_run_k(..., ami_kma_bt=True)` selects one research coordinate: the paired
KMA v3.0 BT definition. Inside the existing case lock it resolves the consumed
AMI coefficient file and reads TOTAL radiance from the same fresh K output as
native BT, quality and K. At each model radiance L:

$$
B_K=\Phi(L),\qquad D=\Phi'(L)/\Psi'(L),\qquad K_K=D K_R.
$$

The existing `RttovObsOp` backward therefore evaluates K_R^T D^T lambda_K. All K
fields, including temperature, humidity and cloud content/size slots, are scaled
once along their profile/channel axes without mutating shared input arrays.
The consumed coefficient identity and native BT replay are checked. The bundled
KMA calibration is snapshotted when the factory closure is created.

The original native RTTOV factory mode is unchanged. This explicit research mode
supports thermal AMI IDs 8–16 and requires every TOTAL row to be finite and
positive, including flagged rows. It rejects zero/nonpositive flagged placeholders
instead of repairing them. Quality flags remain unchanged. Solar/mixed observables,
alternative calibration tables and higher-order cached-K derivatives are outside
this first path. No general coordinate or covariance framework was added.

## Actual retained experiment

[Source](LIVE_KMA_cost_source_2026-10-04.py),
[result](LIVE_KMA_cost_result_2026-10-04.json) and
[arrays](LIVE_KMA_cost_derivatives_2026-10-04.npz) retain the final three actual
RTTOV DOM32 calls, BASE/plus/minus. The preselected C5 sea column `(73,157)` at
20 seconds retains its 39 native layers and 24 reference-top layers. The fixture's
30 files and profile bytes match the existing C5 receipt. KO pixel `(411,338)` is
decoded with the current source-paired reader, without replacing DN, QC or pixels.
The prior common seven-channel support is frozen; DOM32 quality is identical
across all three calls and is zero for all nine channels. The 7/9 cost support is
the predeclared common set, not two new quality failures. Sigma=1 K and Huber
delta=1 are fixed diagnostic scales.

The differentiated path is now executed by the production components:

```text
native NC -> Torch optical profile -> RttovObsOp.apply(live KMA runK)
          -> compute_obs_loss -> autograd.grad(loss, NC)
```

| Quantity | Final result |
| --- | ---: |
| BASE diagnostic cost | 19.385128029451394 |
| VJP contracted with 0.01 NC | -0.004502693069516858 |
| Independent loss FD, h=1e-4 | -0.004502693133900948 |
| Relative difference | 1.4299017978485989e-8 |
| Existing criterion | 1e-5 |
| Fixed supported channels | 7/9 |

J is dimensionless because its BT residuals are divided by sigma in Kelvin. The
VJP/FD values above are cost derivatives with respect to the dimensionless
direction parameter, not BT sensitivities in K/control.

The stored direction and NC covector have nonzero support only at native
top-to-surface index 34 (0-based): v_NC=1167212.24 and
lambda_NC=-3.857647234334056e-9. The demonstrated active control is this liquid
layer; independent coverage of all 39 NC elements or the full state Jacobian is
outside this result. With v=0.01 NC and h=1e-4, endpoint changes are +/-1e-6 NC
(+/-0.0001%), or +/-116.721224 at the active element. The experiment verifies a
local derivative rather than the response to a finite 1% NC change.

The same two supported channels (WV073, IR096) stay in the Huber quadratic region,
and the other five stay in the linear region, for BASE/plus/minus. This verifies
cost-branch stability for these endpoints; it is not an upstream branch census.

IR105 model BT is 291.879409298424 K and observed BT is 286.160920783162 K,
leaving 5.718488515262 K. Successful gradient connection does not remove this
residual or establish forecast improvement. The current cost is not claimed to
be the exact probability-density transformation of a previously calibrated loss.

The result pins generator/helper/writer/operator/loss/profile-builder sources,
profile, original observation receipt, calibration, consumed coefficient,
RTTOV executable, run script and executed namelist. It records exact CLI arguments.
No KDM time step, private native host or DAWindow trajectory was run here; this
is one optical NC direction and first-order cost covector. The earlier shared-entry
KDM/qv experiment retains its separate scope. Accepted scientific cost, physical
SRF compatibility, number calibration and operational approval remain false.

Run the recorded command with an unused output path and the retained private
fixture available. The script pins the retained profile, observation receipt and
fixture; it is a bounded evidence runner rather than a general forecast driver.

Focused public validation: **27 passed**, including coefficient/derivative checks,
same-run factory wiring with asymmetric profile/channel rows and cloud slots,
default/solar preservation, and the existing observation operator/cost tests:

```sh
python3 -m pytest oracle/tests/test_ami_bt_coordinate.py \
  oracle/tests/test_live_ami_kma_wiring.py oracle/tests/test_rttov_obs_operator.py -q
```

Green and Red reviewed the final source and executed result. This numerical
closure adds no release, scientific covariance, spectral substitution or host claim.
