# S10 C-arm design: zero-rate graupel density guards

**Status: source-level design only; no implementation build or native run.** The S10 A/B counterfactuals are isolated research variants and both fail their all-consumer validity replay. Retention reaches nonfinite `brs=-Infinity`; midpoint reaches `rhox=0` at a direct consumer with `qg=0`. S10 remains OPEN, and the native lane is released to S8.

## Question this arm isolates

Test whether guarding zero graupel-volume numerators removes the `0/0` reads without suppressing any nonzero transfer. This C arm is an additional compile-time shadow, separate from canonical host source and defaults. Keep its zero-qg rule independent of the positive-trace density policy. For the first matched counterfactual, use the existing midpoint positive-trace branch unchanged so the comparison against B changes only the zero-qg division handling; that does not approve `rho_mid=400 kg m-3`.

## Source-order contract

The canonical source initializes process rates to zero before their production (`module_mp_kdm6.F:1044–72`). The density-dependent process rates are produced only inside positive-graupel tests:

- `pgmlt` is initialized at `:1068`, produced under `qrs(:,:,3)>0` at `:1398–1406`, changes qg/rain/T at `:1415–17`, and contributes `pgmlt/rhox` to `brs` at `:1418`.
- `pgdep` is initialized at `:1044`, produced under `qrs(:,:,3)>0` at `:2557–70`, may be scaled in the graupel limiter at `:2715–21`, and contributes `pgdep/rhox` inside the source-ordered `brs` update at `:2819–28`.
- `pgevp` is initialized at `:1072`, produced under `qrs(:,:,3)>0` at `:2616–22`, may be scaled at `:2877–82`, and contributes `pgevp/rhox` to `bgevp` at `:2911–15`.
- `pgeml` is initialized at `:1070`, produced under `qrs(:,:,3)>0` at `:2472–73`, may be scaled at `:2877–82`, and contributes `pgeml/rhox` to `bgeml` at `:2911–16`.

The later volume update preserves non-density terms (`biacr`, `braci`, `bsacr`, `bracs`, `bgaci`, `baacw`, `bgacr`) at `:2819–26`; C must not skip or zero those conversions merely because the current qg value is zero. Likewise, the latent terms remain in the existing source order at `:1417`, `:2828–35`, and `:2934–35`. They contain process-rate operands, not `rhox` divisions. Capture and validate those operands; do not blanket-gate heat or qg production by current qg.

## Guard rule

At each of the four `rhox` division sites, skip only the exact zero numerator when the current `qg` is exactly zero. Otherwise retain the existing division and require finite positive `rhox` before the operation:

```
if (qg == 0 .and. rate == 0) then
  contribution = 0             ! no mass/volume transfer exists to apply
else
  contribution = rate / rhox   ! preserve every nonzero numerator
endif
```

For the in-place `pgdep/rhox` expression, keep every non-density addend and the original expression order on the divide arm; on the zero arm omit only `pgdep/rhox`. For `pgevp`/`pgeml`, set `bgevp`/`bgeml` to zero only on the same exact-zero predicate. Do not clamp qg, brs, rates, or rhox. If qg is zero but a numerator is nonzero, do not suppress it: execute the original division and fail closed if its density is invalid. This condition proves the C guard cannot silently discard a nonzero process transfer by construction.

`pgmlt/rhox` is already inside a producer branch entered only for positive qg at `:1398`; retain that path and add a zero-numerator guard only if the generated source can demonstrate the qg-zero branch is reachable at the use. Never move it outside the positive-qg branch.

## Capture and acceptance before any C run

Add a macro-only `S10ZG` event at each candidate division with `(step,site,loop,substep,i,k,consumer_id,qg,rate,rhox,action)`. Action 0 means exact zero-rate bypass with qg zero; action 1 means original division executed. Replayer requirements:

- Every bypass has `qg==0` and exact `rate==0`; bypass contribution is exactly zero.
- Every nonzero rate has action 1 and source-order contribution equals `rate/rhox`; no event may convert a nonzero rate into a bypass.
- Every action-1 divisor is finite and positive. Any action-1 `qg==0` event with nonzero rate and invalid density fails closed.
- Enumerate every reached site/loop/substep/level from the fixed schedule; reject missing, duplicate, or relocated events with code-fixed keys/counts and payload hash.
- Add `S10HEAT` operands at the three source-ordered temperature updates. Preserve each process rate and coefficient; demonstrate that C skips no nonzero latent term. Compare source-order f32 operands and applied updates, not just end-state temperature.
- Log `pgmlt`, `pgdep`, `pgevp`, and `pgeml` before their volume/heat consumers plus the paired qg mass, brs volume and temperature updates. Compute signed departure/arrival terms, limiter-scaled amounts, and residuals in source order. The current S10 capture contains no explicit phase-rate or latent-heat operands; its history differences cannot substitute for this ledger.

## Matched experiment

After S8/S15 release the native lane, compare B midpoint against C midpoint on the same retained LC05 inputs, same 20 s timestep, one rank/thread, identical executable family settings and effective namelist. Run logging off/on per arm. Acceptance requires within-arm `253 numeric raw-bit fields + exact Times` equality; the C replay gates above; and separately reported B↔C changes in qg mass, brs volume, velocity, phase rates and latent heat. Do not require between-arm parity. Retain both failed A/B outcomes unchanged. Keep the positive-trace density rule exposed as an independent option; any alternative value or projection needs physics-owner review.

No C source overlay, object, executable, or run exists yet. This report establishes the guard semantics and proof obligations only; it does not close S10 or select a physical policy.
