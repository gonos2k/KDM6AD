# Frozen selected-donor QNC scale pilot, 2026-10-29

Base: PR #475 head `12445d15716c8e981f661ad970cfe1aec10f7d6b`, whose
[input packet](../harness/evidence/native_qnc_candidate_inputs_2026-10-28/README.md)
records unchanged pre/post face and RK operands. The [companion packet](../harness/evidence/native_qnc_selected_adaptive_2026-10-29/README.md)
evaluates a **frozen-input, selected-54-donor** numerical pilot. It makes no
host, KDM, RTTOV or optimizer calls and changes no operational source.

## Selection and simultaneous application

For each selected donor independently, the analyzer inspects its recorded
positive binary32 `SCALE` word and then each representable lower word in
order, up to 256 ULP. A trial rounds each sign-selected outgoing correction
face as `RN32(PRE × trial_scale)` and mirrors that word to its receiver. The
first trial is selected only when the donor's exact residual from those
rounded face words is positive **and** every binary32 RK result compatible
with its recorded original arithmetic is positive. The replay enumerates
eight directional FMA choices and 24 RK choices: separate or fused tendency,
old factor and new factor, crossed with separate, left-fused or right-fused
numerator arithmetic. It retains choices matching the original recorded
word; these are source-compatible possibilities, not identified executed
instructions. The search does not
assume that binary32 pass/fail is monotone; reaching the cap without a pass
would report an unresolved donor, not prove that no lower solution exists.

The final proposal recomputes each affected face from the immutable PRE
word and all selected scales, rejects duplicate face ownership, and checks
**all 382 captured cells together**. The four existing QC-positive receiver
states with exact residual 0 and stored NC `+0` are compared with the
candidate as existing failures; the gate rejects any *new* receiver failure.
This is a numerical selected-neighborhood gate, not a domain-wide physical
number budget.

## Frozen result

| Same selection procedure | Control | α=0.25 |
| --- | ---: | ---: |
| Donors passing at original scale | 47 | 0 |
| Donors needing 1 ULP | 7 | 30 |
| Donors needing 2 / 3 / 4 ULP | 0 / 0 / 0 | 19 / 4 / 1 |
| Donors unresolved within 256 ULP | 0 | 0 |
| Changed distinct outgoing face words after simultaneous application | 39 | 306 |
| Selected donors passing exact and compatible f32 signs afterward | 54 / 54 | 54 / 54 |
| Captured cells passing both sign checks afterward | 378 / 382 | 378 / 382 |
| New QC-positive receiver failures | 0 | 0 |

The four remaining receiver cells are `(i,k,j)=(152,12,268)`,
`(214,14,181)`, `(214,15,182)` and `(225,20,205)`. They have exact
residual 0 and QNC `00000000` in both original and candidate calculations.
They are not newly invalidated by the selected face changes. In the
**unchanged host executions** recorded by PR #475, their QC remains positive
and NC zero at `PRE_MICROPHYSICS`; all four reach QC=NC=`00000000` at
`POST_MICROPHYSICS` and retain those words at `POST_FINISH`. The changed-scale
candidate has not run through KDM or a final checkpoint, so its later state
is unknown.

For a separate **same fixed coordinate table** comparison, take at each
donor the maximum of its control and α ULP counts. This table equals α's
counts and uses one spatial table in both experiments. It changes **297**
control face words, versus 39 under control's own state-based selection;
50/54 control donor offsets differ from their own first passing choices.
The α result is unchanged at 306 changed face words. Both table cases leave
the same four prior receiver zeros and create no new captured receiver
failure. This fixed table is a diagnostic of control impact, not a proposed
coordinate-independent runtime rule.

## What remains before a host rule

The same *decision procedure* was applied to both saved cases, but its
inputs cover only the declared 54 donors and immediate receivers. Other
active QNC donors, simultaneous whole-domain interactions, nonzero source
paths, changed tile seams and multi-rank halos are not covered. The f32
paths are compatible with original records; the compiled FMA instruction
sequence has not been identified. The exact ledger uses raw numerical RK
coordinates whose physical number basis is unresolved across host, KDM and
RTTOV. The QI donor subnormal is separate.

An isolated host variant must compute scales from live state with one
shared face word per sign-defined donor, verify post-rule RK states and
trace off/on checkpoint identity, and evaluate the whole fixed M0. The
executed α checkpoint still loses **54 profiles / 378 channel cells**; no
whole-support RTTOV cost, accepted update or second assimilation follows
from this offline pilot.
