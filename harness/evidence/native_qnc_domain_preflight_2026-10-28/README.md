# Native QNC failed-layer preflight packet

Run from the repository root:

```bash
python3 -m harness.evidence.native_qnc_domain_preflight_2026-10-28.replay
```

The replay validates its manifest, all public raw traces, current calculation
sources, and the PR #466/#471 parent packets before recomputing `analysis.json`
byte for byte. The offline replay makes **zero host, KDM6, RTTOV or optimizer
calls**. The execution receipt separately records **four accepted 20 s
full-domain host steps** with tracing off/on for control and α=0.25. It lists
eight KDM wrapper entries as expected from the established two-tile run path;
this packet does not independently count them in the private executable.

Each `advect.tsv` has one call record per tile and one operand row for each
of the 54 liquid failure layers. Each `rk_writer.tsv` adds those layers to
the previous ten targets. The replay checks that the previous PR #471
writer's **1,550 raw words per case** are unchanged. It also checks
source-compatible face→tendency and RK output arithmetic for the selected
layers, PD-prepared old-buffer handoff, and scalar-boundary QC/NC identity.
Trace rows use native `(i,k,j)` order; report locations use `(i,j,k)`.
The arithmetic mode check establishes compatibility with the stored words;
it does not identify the executed compiler instruction stream.

The selected-layer result is [reported here](../../../docs/NATIVE_QNC_DOMAIN_PREFLIGHT_20261028.md).
It classifies **48 α cells with negative exact applied-face numerators** and
**six α cells with positive exact numerators but negative stored RK3 NC**.
Control's stored NC is positive at all 54 layers, although seven control
exact numerators are negative. The exact numerators are rational calculations
on saved f32 operands; the number-unit measure is not certified.

The public receipt contains path-free source/build/step/trace hashes. The
private executable, full checkpoint comparisons, and RAM cleanup receipt
were checked locally and are not shipped. The unchanged α checkpoint still
loses 54 fixed-M0 profiles / 378 channel cells. No new correction variant,
whole-support RTTOV cost, or second assimilation is included.
