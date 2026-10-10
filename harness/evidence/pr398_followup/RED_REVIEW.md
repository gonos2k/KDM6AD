# PR398 final Red review

This read-only review covers the completed eight-iteration capture, its
preserved PR397 comparison failure, the saved-array control-balance artifact,
and the six-case V2 direct-H temporal/centroid sensitivity result. Red made no
native, KDM M, H, RTTOV, optimizer, or test calls. The native forecast was not
restarted. Original PR397 RESULT, DRIVER and private checkpoint remain
unchanged.

## Convergence experiment and signature status

The PR398 runner returned one `RETURNED_DIAGNOSTIC_ONLY` capture with the same
validated intake, background, forcing, seven observations, all-seven frozen
mask, and effective H configuration as PR397. The initial zero-control H BT
array is bitwise identical across the saved PR397 and PR398 callbacks; Jo0 is
`26.588575903055926` in both. The mask and callback quality flags also match.
The only difference in the JSON effective H configuration is the isolated
`fixture_case_dir`; the copied fixture files, executable, coefficient, and
other effective configuration fields match the hash-bound PR397 driver.

The original PR398 DRIVER receipt still has
`same_pr397_initial_signature=false` and status
`RETURNED_WITH_CHECK_FAILURES`. That failed check is preserved. The separate
`POSTRUN_INTERPRETATION.json` does not overwrite or relabel it. Its source
check is consistent with `oracle/kdm6/da_fulldomain.py`: `_h_signature()` hashes
the complete `rttov_cfg`, including the distinct absolute `fixture_case_dir`.
Within PR398, all trace signatures remain stable and its initial and final
accepted audit signatures match. I therefore interpret the cross-run raw hash
difference as path-sensitive metadata after verifying the saved BT/state/
forcing/mask, normalized effective H config, and source assets; I do not claim
that the raw signatures are equal.

The eight-iteration allowance actually used `max_eval=10`, `n_iter=4`, and
`func_evals=4`. PyTorch reported termination reason `UNKNOWN`. The accepted
audit gradient has L2 `3.1591637535e-6` and L-infinity
`1.1849362251e-6`, above `tolerance_grad=1e-10`. Final `Jtotal` is
`26.364090171757063`, only `-2.1871e-8` from PR397's final objective
`26.36409019362798`; the slightly smaller observation term is nearly canceled
by a larger state prior. This is a returned, short optimizer trajectory, not
convergence or forecast-skill evidence.

## Control-balance calculation

I checked `analyze_control_balance.py` against the immutable PR397 capture NPZ
(SHA-256 `8cfe28df…c904c59`). `State._fields` ordering in `oracle/kdm6/state.py`
matches the script's row order. The NPZ has 39 active `th` cells and exactly
qv levels 0–11 active; all other state controls, all inactive state rows,
`v_theta`, and `grad_v_theta` are zero. The computed
`Jb=0.5*sum(v_state**2)=0.22847379091279527` matches the capture. Concatenating
the state and parameter gradients exactly reconstructs the captured combined
gradient.

The saved-state formula `g_prior=v_state` and
`g_observation=g_total-v_state` follows from the existing dual closure's
`Jb=0.5||v_state||²` and total gradient `v_state + jac_CVT * adj_x0`. Thus
`g_observation` is the prior-subtracted normalized control-space contribution
through CVT/M/H, not a raw H adjoint or a named-process derivative. The
reported prior/observation cosine is `-0.999999962856`; it shows near
cancellation in these stored control vectors, not curvature, Hessian,
identifiability, or convergence. The `0.5||g_total||²` field is explicitly a
fixed-sign identity-Hessian surrogate, not an actual nonlinear cost decrease
or bound. The calculation source only reads NumPy arrays and records zero
KDM/RTTOV calls.

## V2 direct-H time and centroid sensitivity

The V2 result's plan SHA, current driver SHA, intake NPZ SHA, and baseline
receipt hashes match their files. All six predeclared cases returned, with
zero RTTOV quality flags on every channel of the frozen seven-channel mask.
I independently recomputed every Huber value from the saved BT and fixed
AMI-channel target; all match the recorded `Jo_huber_K_units`. Per-frame
State, Forcing, rho-d, and profile hashes in the plan match the intake arrays.
The result records zero KDM M and backward calls. The execution marker and
result are preserved in the private V2 directory.

| Native saved frame | UTC label | AMI-center cost | Native-center cost |
| --- | --- | ---: | ---: |
| 1 | 05:56:00 | 26.5976847821 | 26.6001479738 |
| 4 | 05:57:00 | 26.6246541045 | 26.6271161550 |
| 6 | 05:57:40 | 26.6414993999 | 26.6439606943 |

These are `H(host(t))` diagnostics, not the analysis's `H(M(xb))`. The later
two labels fall inside only the conditional file-level AMI time interval;
per-pixel UTC is unavailable. The two geometry cases hold the selected native
column and its actual HGT fixed while changing only the latitude/longitude
center supplied to the RTTOV viewing-angle calculation. They are centroid
viewing-angle sensitivities, not parallax corrections, footprint tests, or
pixel reassignment. Science acceptance remains false.

The canonical private host archive's manifest lists 40 files; I verified every
archived file digest and that original RESULT/DRIVER/checkpoint hashes are
preserved. No science, conservation, convergence, Hessian, or independent
retrieval claim follows from these completed experiments. Pixel-level time,
footprint overlap, CTH datum, scientific matchup, forecast skill, and a closed
water/heat budget remain unestablished.

### Review artifacts

- `harness/evidence/pr398_followup/RESULT_PR398_CONVERGENCE_8ITER_20261010.json`
- `harness/evidence/pr398_followup/DRIVER_PR398_CONVERGENCE_8ITER_20261010.json`
- `harness/evidence/pr398_followup/POSTRUN_INTERPRETATION.json`
- `harness/evidence/pr398_followup/CONTROL_BALANCE_PR397.json`
- `graphify-out/pr398-centroid-viewing-angle-v2-2026-10-10/private/RESULT.json`
- `harness/evidence/pr398_followup_2026-10-10/PREDECLARED_v2.json`
