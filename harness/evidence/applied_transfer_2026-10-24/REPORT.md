# Applied snow/graupel transfer and actual cleanup sink

The three previously localized layer residuals are now connected to observed
internal update boundaries in the **same frozen actual-QR/norm_actual map**.
The measured sink is the actual internal QG threshold cleanup. The selected
cold snow/graupel-to-vapor rate applications conserve water to binary64 rounding
before that cleanup; they do not account for the unmatched endpoint loss.
No physical correction or default/install change is made in this observer PR.

## Executed source, input and noninterference

The original B512 chunks34/40,39 native levels and20-second input are retained.
Only coordinator.cpp is rebuilt over the pinned actual-QR archive;13/14 object
members remain identical and `-ffp-contract=off` is retained. The new generator
checks the public source/factorial rendering and exact actual-QR base bytes.
The coordinator change only inserts diagnostic code; original arithmetic lines
and operation order remain. Serialization and scalar extraction are confined
to the environment-gated helper's value-only NoGrad scope.

Four value calls compare new observer-off/on with each previously frozen
same-candidate full response: every response is byte-identical. Six separate
recorded forwards compare frozen candidate control, observer-off and observer-on
at hotspot columns281/250. All eight saved raw-state, applied-finish, JVP/VJP,
seed and direction products match bitwise. The selected mixed tangent/cotangent
comparison does not certify a whole Jacobian or add FD/HVP evidence.

The trace emits only chunk34,column281,bottom0 layers17/18 and chunk40,column250,
bottom0 layer17. Rates are sampled both before and after the sequential group
limiters, but the pre-group values are **already capped by their local process
kernels**. No uncapped C4/D2/D3 attempt was captured or reconstructed as observed.

## Actual signed rates and update boundary

Coordinates/levels in this table are native1-based; levels count upward from
the bottom. Rates are kg/kg per second in the executed water coordinate.

| Point/layer | psdep | pgdep | Branch | Group rate scaling |
| --- | ---: | ---: | --- | --- |
| (140,76),18 | −9.841105899035994e−8 | −1.8381621654687723e−11 | cold | none, factor1 |
| (140,76),19 | −2.0311128256869672e−7 | −9.52914144076398e−10 | cold | none, factor1 |
| (139,89),18 | −8.046196240955893e−7 | −1.6840171415379873e−9 | cold | none, factor1 |

At all three cells cold_mask=1,warm_mask=0; psevp,pgevp,prevp,pinud,pidep are0.
All four selected rates are unchanged by the14 group budgets. In particular,
cold snow/graupel source budgets4/5 have source below value, with factor1.
The recorded aggregate rate sums reduce to `dqv=-psdep-pgdep`, `dqs=psdep`,
`dqg=pgdep`; qg inline amount is0. Negative rates therefore consume QS/QG and
supply QV with matched nominal signed amounts. The reader separately reports
rate×dt pairs and actual summed state changes; it does not allocate rounding
of the aggregate update among individual processes.

All six raw moisture updates reconstruct exactly using source association:
QV/QS use `before + rate_sum*dtcld`, other fields use
`(before + inline_amount) + rate_sum*dtcld`. The returned state-update max
projection changes no water value at these cells. Fixed-measure total update
residuals are only+8.728026011855323e−17,−2.4367443826611712e−17 and
−8.575361558002537e−18 kg/m². Reclassification and satadj make no subsequent
water changes at these selected cells.

## The observed cleanup loss

| Point/layer | Entry dry mass weight rho×DELZ,kg/m² | QG immediately before cleanup,kg/kg | QG after | Actual cleanup change,kg/m² |
| --- | ---: | ---: | ---: | ---: |
| (140,76),18 | 465.4281181978131 | 6.249024687686985e−10 | 0 | −2.90847180096183e−7 |
| (140,76),19 | 461.0844635660463 | 9.78895847838864e−10 | 0 | −4.513536668878127e−7 |
| (139,89),18 | 464.36305507685444 | 8.984240569093862e−10 | 0 | −4.171949398209843e−7 |

These positive QG remainders are at/below the source cleanup cutoff1e−9.
The captured `post_satadj→post_threshold` transition zeros QG and preserves QV,
other water species and temperature. The final DSD boundary makes no water
change. This directly identifies the measured sink at these cells. It does
not explain why the earlier processes leave those particular subthreshold
remainders, nor certify a full energy/number/volume budget.

The earlier per-layer post_sed→post_micro losses are recovered by adding the
small source-order state-update rounding remainder to the cleanup changes.
Chunk34's two layers account for its maximum column deficit7.42200846e−7;
chunk40's layer accounts for its maximum4.17194940e−7, with other-layer
roundoff separately present in the accepted saved arrays. This is not a survey
of every residual in all65,988 columns or all other cells in these blocks.

Primary reported changes are **per-species endpoint deltas, rounded weight×delta
products, then math.fsum**. Subtraction of two large total inventories is only
a secondary cancellation diagnostic. Actual recorded entry/exit six-water
values and forcing geometry match the earlier public NPZ stages bitwise.
No posthoc hypothetical host cleanup array is used to infer this applied
internal cleanup. The two operations remain distinct.

## Replay and coverage limits

Both raw trace TSVs and analysis.json are public. Reproduce using
`python -m harness.analyze_applied_transfer_trace` with two `--input` paths,
chunk034/040 `--reference-npz` inputs and a new `--output` filename. The parser
requires the fixed v1 fields, all14 before/after limiter groups and the exact
three-cell target set. `dt` in TSV is the captured `dtcld_seconds`. Call IDs
count traced coordinator invocations locally within each source process;
merged equal ordinals from disjoint blocks are not a count of KDM executions
or absolute host timesteps. Execution receipts separately count the experiments.

Total new scientific calls:10 KDM (4 value+6 selected AD),0 RTTOV,0 native
host/DA/whole-domain repeats. This is an isolated one-TU diagnostic rebuild,
not a clean host build or operational f32 parity campaign. Existing accepted
QR conservation, native state feedback and selected T/Q→RTTOV first-order
milestones remain complete in their scopes; no new observation derivative or
full-host/RK/HVP validation is claimed.

The next physical design can separately decide how to handle subthreshold QG
while preserving water, energy and mass/number/volume consistency. This PR
retains the old rule and documents its applied sink; no compensating vapor or
latent-heat update is silently introduced.
