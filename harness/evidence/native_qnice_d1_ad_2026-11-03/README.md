# Conditional D1 melt derivatives on the native level-15 call

This packet extends the [same-call D1 QI record](../native_qnice_d1_qi_2026-11-03/README.md).
It uses the same 2025-07-19 00:00:40 input, 20 s mp137 call, `(164,242)`
column, 39 native levels, and `runtime_call=one_step_call=2`. A new isolated
DSO adds D1 QC, NC, heat-capacity, capped snow/graupel melt and temperature
operands/stores. The copied host executable and numerical physics are
unchanged. The run uses the experimental `norm_actual` sedimentation variant
and the native fp64 value bridge.

```bash
python harness/evidence/native_qnice_d1_ad_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_d1_ad_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_d1_ad_2026-11-03 -v
```

The capture contains **3,978** rows. All **3,471** parent rows retain their
dtype and raw word; **507** rows are new. The normal CLI authenticates the
original capture with a fixed SHA-256. For test-only rehashed overrides, the
verifier rejects wrong call/tile/level/dtype/order, missing fields, changed
parent words, and selected source-order arithmetic contradictions. It does
not certify the original bits of every new operand: changing level-15
`qv_before` by one f64 step can round to the same `pre_cpm` and pass an
override replay with identical results. This numerical collision is a
documented limit of the override check, not of the fixed-hash CLI.
It reconstructs the sole added C++ capture block on top of the pinned parent
source and checks the resulting source hash against the isolated build
receipt. It also checks the private run/session receipts and loaded DSO path.
The private executable, DSO, objects and complete checkpoints are identified
by hashes and run records; public CI does not rehash or rebuild those bytes.

## Source-order baseline

For all 39 levels, the replay reconstructs the D1 ice-melt producer from
captured QI/T, the NI melt selection, source-order `pre.cpm` from captured QV,
`cpm_safe=max(pre.cpm,1e-9)`, and the QC/NC/T stores from captured process
amounts in executed order. The C++ thermo and two-rounding accumulator
sources and their object hashes are pinned in the build receipt. At native
level 15:

| D1 field | Captured value |
| --- | ---: |
| QI before / applied `pimlt_qi` | `6.109135817357022e-11` |
| QC before → after | `3.2093291224555287e-7` → `3.209940036037264e-7` |
| T before → after | `275.62344271948496` → `275.62344269828947 K` |
| `cpm_safe` | `1008.7971032572444` |
| NI before; NC before | both `0` |
| QI after; NI after | both `0` |

Snow/graupel capped melt amounts and D1 freeze terms are zero at this level.
The state difference `QC_after−QC_before` is slightly different from the
applied QI amount because subtraction of two stored f64 numbers rounds. The
**source-order addition** `QC_before+pimlt_qi` matches the recorded QC word.

The verifier also forms a new fixed-speed conditional chain: captured
sedimentation operands → freshly computed D1 `pimlt_qi/pimlt_ni` → snap A →
fixed captured D2–D4 rates → snap B → C3 input NI. It uses no hard-coded
15-level QI splice. Its 39 C3 NI outputs match the native record in raw f64
bits. This is a baseline and selected-operand chain, not the full host AD.

## Local conditional derivative

At the D1 input, the map varies QI or NI while fixing T, QC, NC,
`cpm_safe`, snow/graupel melt amounts and other D1 rates. The branch
`T>273.15 K, QI>0` remains active at every tested QI endpoint. In the
output order `(QC,QI,NC,NI,T)`, the unit **relative QI** direction has JVP

```text
(+6.109135817357022e-11, 0, 0, 0, −2.1195516216006763e-8 K).
```

The unit **absolute positive NI** direction has JVP `(0,0,+1,0,0)`.
Independent source algebra, Torch JVP/VJP, represented-gap QI central
differences (`h=0.1,0.01,0.001`), and positive one-sided NI differences
(`h=1,0.1,0.01`) agree under the stated resolution bounds. The QI `h=0.001`
temperature endpoint signal is about 745 f64 spacings; the replay reports
each signal, spacing, and FD–JVP difference rather than imposing a single
relative-error threshold. [Saved diagnostics](results.json)

Baseline NI is exactly zero while QI is positive. The NI tangent is a
**conditional numerical one-sided direction**, not an admitted physical
number-moment perturbation or evidence of a two-sided derivative at that
boundary. The local D1 map holds the **verified baseline `cpm`** fixed rather
than differentiating QV→cpm. It also does not recompute snow/graupel melt rates,
upstream sedimentation speed, or later process-rate producers as QI/NI change.
The new no-splice chain is checked at the recorded baseline; its full
JVP/VJP through later processes is not certified here.

A later [conditional speed→D1 chain replay](../native_qnice_d1_chain_ad_2026-11-04/README.md)
checks selected QI16 and QI23 directions through the combined map. It
preserves this packet's fixed-cpm and fixed-other-rate interpretation.

Both capture-off and capture-on endpoints hash to
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`,
also the PR #528 endpoint hash. `scientific_status: INCONCLUSIVE` and
`physical_unit_status: INCONCLUSIVE`; operational f32, QNICE production and
restart units, full host derivatives, and RTTOV sensitivity remain open.
