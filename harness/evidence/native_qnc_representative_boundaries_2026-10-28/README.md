# Representative QC/NC and QI/NI boundaries, 2026-10-28

This packet compares the same four native `(i,j,k)` layers in full-host control
and the previously rejected alpha=0.25 T/Q candidate. It extends PR #467's
same-layer checkpoint comparison to recorded RK, microphysics and finish
boundaries. The common origin is READY40 and the endpoint is 60 s. The donor
scale change from PR #465 remains active in both cases.

The private host ran the full 234×282 domain with 39 mass layers, one rank,
one thread, one 20 s step and `mp_physics=137`. Forward microphysics heating
was enabled (`no_mp_heating=0`); longwave and shortwave radiation ran in the
configured full-physics step. The exact other options are in
`execution_summary.json`. Four independent runs comprise control and alpha,
each with representative tracing off and on. The off/on checkpoint SHA-256 and
application ACK agree within each case; both endpoints also match the earlier
PR #465 variant. Only `solve_em.o` changed in the isolated trace build. The
public receipt records source, object, executable, input and trace hashes;
the private full checkpoint and executable are not distributed.

Each trace contains **568 typed records: 544 f32 words and 24 boolean words**.
The reader requires every expected target, stage and field. The analysis joins
`POST_FINISH` raw QC/NC/QI/NI words to the PR #467 control and PR #466 candidate
checkpoint witnesses at the same `(i,j,k)`.

## Liquid witnesses

The following NC values are raw numerical coordinates with uncertified
physical units. Both cases have negative NC after RK1 at all three layers;
the first recorded NC *bit difference* is after RK2. The first recorded
liquid-pair validity split occurs after RK3, while QC remains positive.

| Native `(i,j,k)` | First differing recorded `ADVECT_TEND` | RK3 NC: control | RK3 NC: alpha | After microphysics: control / alpha |
| --- | --- | ---: | ---: | ---: |
| `(153,111,4)` | RK1 before | +0.587423801 | −0.305852234 | +0.587423801 / 0 |
| `(113,70,12)` | RK2 before | +0.001692894 | −0.006369510 | +0.001692890 / 0 |
| `(155,120,15)` | RK2 before | +0.010239942 | −0.003562272 | +0.010234918 / 0 |

At RK3, `SCALAR_OLD`, `SCALAR_TEND` and all other inputs to the **numerator**
apart from `ADVECT_TEND` have identical bits between cases at these layers.
`MU_NEW` differs, but the reconstructed new mass factor is positive in both
cases and only appears in the denominator. Exact real arithmetic on the saved
binary32 operands gives a positive numerator for control and a negative one
for alpha at all three layers, agreeing with the observed sign. This is a
saved-operand sign check. It does not reproduce the compiled binary32
operation sequence or establish a physical conservation budget.

In the alpha run the negative NC reaches `PRE_MICROPHYSICS`. It is zero in
`POST_MICROPHYSICS` and stays zero through `POST_FINISH` and the checkpoint,
while QC remains positive. This identifies the transition to zero at the
KDM call boundary. It does not name the internal KDM process responsible.

## Ice witness

At `(1,168,33)`, control QI is zero. Alpha QI first differs in the recorded
`RKSCALAR_BEFORE` stage of RK3 as binary32 word `00000002`
(2.80259693×10⁻⁴⁵). The preceding `RKSCALAR_AFTER` stage of RK2 has zero QI
in both cases. NI is zero throughout the sampled stages. The alpha QI word
persists through microphysics, finish and the checkpoint. The trace brackets
the divergence between these two stages; it does not identify an individual
operation within the interval.

## Replay and limits

From the current repository tree:

```bash
python3 -m harness.evidence.native_qnc_representative_boundaries_2026-10-28.replay
```

The replay checks packet/source hashes, the path-free native run receipt,
historical PR #465–#467 packet identities, all stage records, checkpoint-word
joins, the saved-operand sign and the expected first recorded validity splits.
The replay itself makes **zero host, KDM, RTTOV or optimizer calls**.

This diagnostic does not change the rejected alpha=0.25 outcome: the candidate
still loses 54 profiles and 378 channel cells from the fixed full-domain M0.
Its full-support RTTOV cost remains undefined; no analysis was accepted and no
second assimilation was run. The selected traces do not certify raw NC units,
domain conservation, named-process causality, an entire host Jacobian, or
forecast skill.
