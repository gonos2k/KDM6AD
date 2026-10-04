# One-hour prescribed-forcing KDM and live cost/VJP experiment

Baseline: PR #371, `d0e2e14bf617e88da2427614d0c86c2169a4b186`.
The requested long-run computational check completed. One column was integrated
for 3,600 modeled seconds (180 steps of 20 s), using the retained native C5 input
and fixed forcing. BASE, plus and minus each traverse a separate one-hour
trajectory; the descent trial and plain value replay each traverse another.
The complete final campaign took about 140 s of wall time on the local CPU.
This is one-hour model-time coverage, not a one-hour wall-clock soak test.

## Executed connection

[Runner](LONG_KMA_cost_source_2026-10-05.py),
[result](LONG_KMA_cost_result_2026-10-05.json) and
[arrays](LONG_KMA_cost_arrays_2026-10-05.npz) retain the actual calculation:

```text
initial qv -> 180 Python KDM steps with fixed forcing
           -> optics with the last step's own entry humidity
           -> actual RTTOV DOM32 / KMA BT -> fixed diagnostic cost
           -> VJP to initial qv
```

The profile retains 39 native layers plus 24 declared reference-top layers.
Each KDM step uses dry number, normalized ice handoff and conservative
sedimentation, with the same 10/10 thresholds. Each optical evaluation receives
the corresponding pre-step qv alongside the post-step state; the last call's
direct density path remains connected to initial qv. Forcing, pressure geometry
and the background layers are prescribed. No core physics or ABI was changed.

The memory-saving non-reentrant checkpoints contain only the pure KDM
transition. External RTTOV and evidence I/O are outside recomputation. A plain
value-only run reproduces all 12 state fields in raw binary64 bits at 20, 600
and 3,600 s. Derivative recomputation is not counted as extra modeled time.

## Results

The complete BASE/plus/minus trajectories use v=0.01 initial_qv and h=1e-4.
Ten actual RTTOV K runs were executed: three checkpoints for each trajectory
and one descent trial. Every forward step remained finite. All three gradient
checks pass the unchanged relative criterion 1e-5:

| Modeled time | BASE cost | VJP directional cost | Independent FD | Relative difference |
| --- | ---: | ---: | ---: | ---: |
| 20 s | 19.96343179787636 | -7.547137073936137 | -7.547137090693212 | 2.22032e-9 |
| 600 s | 19.954351004620488 | -7.425279222081113 | -7.425279355022241 | 1.79039e-8 |
| 3,600 s | 19.95440779362889 | -7.424764417054581 | -7.424764688277463 | 3.65295e-8 |

Quality flags remain zero for all nine channels, while the predeclared seven
cost channels and cloud fractions are unchanged between endpoints. The initial
humidity covector has nonzero entries at all 39 layers, but independent FD
coverage remains one proportional initial-qv direction, not all independent
state controls. The checkpoints' saved mass/number states are nonnegative;
finiteness was checked at every step, not a complete physical budget.

One predeclared trial uses alpha=0.01 along v, a +0.01% initial-humidity change.
After a fresh full-hour trajectory its diagnostic cost is 19.880751608938176,
down from 19.95440779362889 by 0.07365618469071222. The local linear prediction
was -0.07424764417054582. The trial keeps the same support/quality/cloud fractions
and is accepted as a computational descent trial. No state was written back to
the private host, and no repeated assimilation cycles were executed.

## Interpretation and reproducibility

This experiment establishes finite long-run forward calculation, initial-qv
gradient propagation through repeated microphysics and live radiation, and one
small lower-cost control trial. It does not establish a physical retrieval,
forecast improvement, time accuracy, native parity or DAWindow scheduling.

The retained nominal 00:00 observation is a fixed diagnostic target throughout
the hour, not a time-collocated hourly observing sequence. Sigma=1 K and Huber
delta=1 remain diagnostic; product/SRF compatibility, number calibration,
scientific analysis/error approval and operational approval remain unresolved.
No channel, observation, coefficient, threshold or error weight was tuned to
obtain the derivative agreement or trial acceptance.

The receipt pins source files, initial profile, observations/calibration,
30 fixture files, consumed coefficients, RTTOV executable and namelist, versions
and exact arguments. The script requires an unused output directory. Earlier
preliminary runs remain separate local outputs; the public record is the final
source-pinned campaign above. No additional unit-test framework was introduced.
