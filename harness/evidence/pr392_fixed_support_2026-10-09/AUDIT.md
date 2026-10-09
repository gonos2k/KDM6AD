# PR392 fixed-support QC trial audit

## Finding

The full-domain evaluator does freeze support at the background probe. It does **not** verify that trial RTTOV quality still supports those same channels. In the routed path, `run_fulldomain_analysis` calls `make_fulldomain_obs_eval` and passes it to `run_dual_minimizer` ([da_fulldomain.py](../../../oracle/kdm6/da_fulldomain.py#L1179)). There is no `make_frozen_obs_eval` symbol on this branch; the full-domain factory is `make_fulldomain_obs_eval`.

`make_fulldomain_obs_eval` probes `rad_quality` at `x_slot_bg` and defines fixed `mask`, `n_valid`, and `signature` from that background result ([da_fulldomain.py](../../../oracle/kdm6/da_fulldomain.py#L708), [mask/signature](../../../oracle/kdm6/da_fulldomain.py#L718)). At each trial it calls `sharded_allsky` with that same `mask`, then builds `ObsEvalResult` with the same `n_valid` and `signature` ([trial callback](../../../oracle/kdm6/da_fulldomain.py#L739)). The all-sky worker receives trial `rad_quality` from `RttovObsOp`, stores and returns it, but computes `_part_loss` using the supplied frozen `mask` without comparing the returned quality to that mask ([allsky_shard.py](../../../oracle/kdm6/obs/allsky_shard.py#L135), [quality return and loss](../../../oracle/kdm6/obs/allsky_shard.py#L156)).

The dual minimizer’s existing guard compares `n_valid` and signature across closures ([da_dual.py](../../../oracle/kdm6/da_dual.py#L491)); because this evaluator reports the frozen values, newly flagged trial channels pass that guard. The full-domain route then gives L-BFGS a scalar closure and uses `strong_wolfe` without a trial-quality check ([da_dual.py](../../../oracle/kdm6/da_dual.py#L634)). The general `run_minimizer` path has the same scalar-objective/strong-Wolfe structure ([da_minimizer.py](../../../oracle/kdm6/da_minimizer.py#L153)). The companion `make_dual_frozen_obs_eval` also obtains trial `rad_q` from `_h` but discards it when evaluating loss with the frozen mask ([da_dual.py](../../../oracle/kdm6/da_dual.py#L925)).

## Controlled reproduction

[The reproduction script](repro_fixed_support_qc_loss.py) reuses the existing normalized-dry full-domain test fixture and actual `make_fulldomain_obs_eval`, `sharded_allsky`, and `RttovObsOp` protocols. Only the profile builder and injected `run_k` are synthetic. The fake runner is configured for channels 8–16: channels 8 and 9 start flagged but are pre-excluded by the explicit support gate, and it emits 300 K BTs for the seven channels in S. After a one-kelvin state change it clears those pre-excluded flags, flags active channel 10 with quality 32768, and emits an artificially perfect 280 K BT for channel 10. No binary RTTOV, KDM6 integration, or optimizer is called.

The evaluator retains `S=7/7` and the same signature even though the two pre-excluded flags clear. Its baseline Huber cost is **136.5**; the trial cost is **117.0** even though channel 10 is newly flagged. This proves that the callback can return a lower cost for a trial with new QC loss because the invalid trial BT still contributes on the frozen mask. It does not show that real RTTOV always lowers BT when it flags, or that an optimizer accepted a particular trial. The machine-readable receipt is [RESULT.json](RESULT.json).

The audit keeps the PR391 channels 12–15 intersection diagnostic-only; it never replaces the fixed seven-channel objective. This is a conditional evaluator-contract finding on branch `5a7701e`, not a new production/default P2 finding. R2 observation correspondence remains a separate future-validation requirement; this fake-runner result makes no observation-match claim.

## Minimal contract if optimization is enabled

If the owner enables strict fixed-support QC, add it as an opt-in policy on the existing full-domain evaluator. For each trial, validate BT/quality shapes and quality values on the full expected column/channel field, assemble the trial usable-mask for both all-sky and clear partitions, and require it to match the frozen support `S` before computing loss or returning `ObsEvalResult`. This rejects a lost channel, a same-count replacement, and a shape mismatch; channels already excluded from `S` by observation quality or the predeclared gate remain excluded and do not by themselves invalidate the trial. On usable trials the reported `n_valid` stays equal to `|S|`.

Do not call a thrown exception “backtracking”: current L-BFGS invokes `opt.step(closure)` directly and has no evaluator-error recovery here. A first minimal guard can fail closed on a quality mismatch. If the requirement is to continue with a smaller step, that needs an explicit trial-invalid signal integrated with the existing strong-Wolfe handling; do not change the mask or signature to make the trial look usable. The same trial-quality rule belongs in both `make_fulldomain_obs_eval` and the companion `make_dual_frozen_obs_eval`. This was the pre-implementation contract proposal. The followup below records the later implementation separately.


## Followup implementation

The saved `RESULT.json` and script digest identify pre-fix source at
`5a7701ed` (the same source tree as merged `ce77afa2`), not the later changes.
The full-domain factory now has `require_frozen_quality=False`;
`run_fulldomain_analysis` selects it for `normalized_dry=True`. The reachable
normalized-dry companion `make_dual_frozen_obs_eval` checks the same condition.
Legacy policy and signatures are preserved. Background quality is validated
before S is formed, with zero support at that check, so flagged background
channels can still be excluded normally. Trials require quality zero on S;
excluded flags may change without admitting any new channel.

Current L-BFGS propagates the exception and does not automatically retry a
smaller step. Tests and final review are recorded separately in
[VALIDATION.md](../pr392_interpretation_2026-10-09/VALIDATION.md). The earlier fake
reproduction remains a pre-fix witness. Its saved result was not rerun or
replaced after the fix. Its historical runner writes that receipt directly;
use an isolated copy if reproducing it, preserving this original output.
