# PR #216 follow-up — ordered verification checklist

Baseline: merged main `0f6243abfa85fa699a49c6e046b96c2cce0ae193`.
Target: differentiable KDM hydrometeor processes and their first-order
GK2A–RTTOV observation/cost sensitivities. Forecast skill and unattended cycling
are separate objectives. Preserve the closed PR #215/#216 findings.

Close each item only with executed evidence for its stated scope. Code changes,
zero responses, scalar cost agreement, and remote CI counts do not establish
unmeasured scientific coverage. Reuse existing evidence and two Luna-high
Green/Red agents; final changes receive independent review.

| Order | Item | Completion evidence | Status |
| --- | --- | --- | --- |
| 1 / A1 | Separate signal resolution from AD–FD agreement | Equal nonzero AD/FD at one output spacing remains unresolved; zero/zero remains a zero response; consumer regression | Verified locally; final Green/Red review passed |
| 2 / A2 | Compare same-alpha-zero primals | Exact value-only/graph state and applied-rate equality; graph-only mass-neutral state offset and rate offset fail despite unchanged derivatives | Verified locally; final Green/Red review passed |
| 3 / A3 | Discriminate melt observation channels | Preserve original selected case; asymmetric T/Q K, unequal signed residuals, channelwise JVP/VJP/FD; K-only row permutation fails | Verified locally, synthetic first-order scope |
| 4 / A4 | Locate freeze nccn mismatch | Epsilon sweep with recorded branches and CCN activation/return values and derivatives; distinguish nccn mismatch from th output spacing | Selected boundary localized; JVP/VJP and regression verified |
| 5 / A5a | Actual observation auxiliaries | Provenance and applied pressure/upper profile/angles/surface/UTC; fixture substitutions remain partial | Open; reuse R6 inventory |
| 5 / A5b | Physical number/mass units | Resolve host/kernel measure and process source/sink contracts before physical-budget closure claims | Open; reuse R7 |
| 5 / A5c | Nonzero applied transport | Matched-source binaries and nonzero departure/arrival ledger with neutrality evidence | Open; reuse R8 external prerequisite |
| Final | Green/Red review and regression | Independent final review, focused executed checks, evidence paths and remaining limitations recorded | Passed; execution details below |

## Preserved results and limits

- PR #216 merged at `2026-09-19T01:37:14Z` (GitHub query this session).
- Previous NaN/Inf rejection, bounded signed divergence regression, and required
  LCC comparison remain closed. Divergence regression does not resolve the
  underlying cross-tree derivative difference.
- Existing melt test verifies one synthetic clear-sky fixed-K first-order path.
  It does not certify live RTTOV, cloud K, higher derivatives or identifiability.
- Newly included zero-response donor/receiver variables are negative controls,
  not evidence of representative active nonzero pathways.
- Prior M1 zero-transport capture neutrality is not nonzero transport closure.
  Xcode license remains an external build prerequisite; no acceptance is implied.
- N1 refinement is an executed study, not established sensitivity convergence.

## Evidence log

Implementation and execution results will be appended here in checklist order.

### A4 — selected freeze CCN-return diagnosis

- Executed the current cold fixture at dt=20 s, observing the real
  `apply_satadj_step_torch` call without replacing its calculation. All six
  epsilon pairs (1e-6 through 1e-1) retained the recorded branch masks and
  subcycle metadata. This does not certify unrecorded internal branches.
- Activation is off and complete cloud evaporation is on. The measured boundary
  is exactly `nccn_out = nccn_in + nc_in`, with nc_out=0 and no active clamp.
  Baseline nccn_in=1e9, nc_in=96143949.6189031; nccn_out=1096143949.6189032.
- Reverse derivatives: incoming nccn=0; incoming nc and outgoing nccn both
  -0.24534573037022733. At epsilon=1e-4 incoming nc FD=-0.24534761905670166;
  outgoing nccn FD=-0.24557113647460938. The additional discrepancy at the
  reservoir addition is within its endpoint output-spacing bound.
- Final nccn FD at epsilon=1e-3 is -0.2453327178955078 and at 1e-2 is
  -0.2453446388244629: both meet the existing 1e-4 relative criterion. The
  original 1e-4 result remains a derivative mismatch; its threshold is unchanged.
  This diagnoses a selected finite-difference resolution/truncation window,
  not a new physics or AD correction and not a bound on all upstream rounding.
- th remains separate: AD=6.290674850728013e-11, FD=0 at epsilon=1e-4.
- Reproducible probe and full endpoint values:
  `graphify-out/pr216-review-20260919/freeze_probe.py` and `freeze_probe.json`.
  Portable boundary regression (including genuine forward-AD/VJP agreement):
  `oracle/tests/test_freeze_ccn_return_sensitivity.py`: **1 passed, 18 existing Torch deprecation warnings** (1.50s).

### Reused external evidence

GitHub PR #216 checks were re-read this session: all five passed. Port run
35412240475, oracle 35412240508, harness 35412240547. These are previous
revision results, not tests of this follow-up. A5a–A5c retain the explicit
missing evidence in R6–R8 and the main sensitivity checklist; no synthetic
substitution or zero-transport result closes them.

### A1/A2 — consumer-level verification contract

The comparison retains zero/zero as a selected zero response, but equal nonzero
AD/FD at one output spacing is unresolved. No post-hoc multiplier or wider
agreement tolerance is introduced. The spacing estimate covers final outputs,
not upstream evaluation error.

A separate same-control alpha=0 value-only evaluation is compared exactly with
the graph evaluation for all state fields and the selected applied process-rate
fields. `controls=None` remains the separate intervention baseline. Mismatches
are reported with state/rate deltas and prevent verified field/aggregate labels.
State-only mass-neutral and rate-only constant-offset injections are tested
separately; neither can hide behind unchanged directional derivatives.

### A3 — channel-discriminating synthetic melt test

Retained the original selected fixed-K case and added rank-2 T/Q coefficients
with unequal signed observation residuals. Channelwise JVP/VJP and two central
FD directions are compared, as is the scalar cost derivative. Permuting only K
rows leaves forward BT unchanged but fails both derivative comparisons.

The asymmetric case uses epsilon=1e-3 and 3e-3. The initial 1e-4 probe had maximum
channel relative error about 1.49e-5 and did not meet the unchanged 1e-5 criterion;
it is not counted as successful validation. No absolute-error floor was added.
AD/AD uses rtol=1e-10, atol=0; FD uses rtol=1e-5, atol=0. Each channel and cost
AD/FD signal must exceed its own endpoint-spacing estimate. These are final
output spacing checks, not universal bounds on upstream evaluation error.

### Final local verification and independent review

- Related eight-file regression: **110 passed, 18 existing Torch deprecation
  warnings** (7.42s). Includes process controls, process/profile/observation and
  cross-tree tests. Existing local native library was reused, not rebuilt.
- After restoring the explicit scalar-cost FD assertion, final changed-path
  group: **23 passed, 18 warnings** (4.05s). This overlaps the above count;
  do not add the counts. `git diff --check` passed.
- Reused Luna-high Green and Red teams independently reviewed final changes;
  neither reported a remaining blocker in A1–A4's stated scope.
- Public Graphify updated: 11824 nodes, 20159 edges, 917 communities.
- A5a–A5c and representative nonzero coverage/N1 remain open. No operational
  f32 equation, native ABI or forecast-performance claim changed.
