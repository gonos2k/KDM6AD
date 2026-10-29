# Selected QNC live guard: one native host step

This packet records a bounded research variant of the PR #475 host. The same
rule was enabled for the 54 previously failing liquid QNC donor layers in
control and α=0.25. It selected a scale from the **current** RK3 scalar state,
immutable pre-limiter faces, and mass/source operands, then applied each
rounded shared face to both cells. This is a selected-coordinate pilot on the
recorded two-tile, one-rank, one-thread geometry, not an operational
coordinate-independent limiter.

## Executed path

- Native 234×282×39 domain, READY40 → model time 00:01:00, one 20 s step,
  `mp_physics=137`, RK3 positive-definite scalar advection, IEVA disabled.
- Four completed host runs: control and α=0.25, each with face/RK tracing off
  and on. Each pair has an identical full checkpoint SHA-256 and applied ACK.
  The private build changes `module_advect_em.o` and `solve_em.o`, adds four
  guard/helper objects, and retains the pinned PR #475 KDM DSO. The executable
  and full checkpoints remain private; public receipts identify their hashes.
- The host guard checks a conservative binary64 sign certificate for the
  saved-word RK residual, all 192 source-compatible f32 arithmetic patterns,
  a mirrored face value for both incidences, all affected receivers after the
  simultaneous tile-local changes, and the actual RK output word. A selected
  donor failing any check aborts the run. The 192 patterns do not identify
  emitted compiler instructions. They are stricter than PR #476's modes
  filtered by each original output, so the ULP histograms differ.

| Current-state result | Control | α=0.25 |
| --- | ---: | ---: |
| Selected ULP steps | 0:38, 1:14, 2:2 | 1:25, 2:21, 3:6, 4:1, 5:1 |
| Distinct changed shared faces | 87 | 310 |
| Selected donors positive at RK3 and liquid-valid at finish | 54/54 | 54/54 |
| Original M0 lost profiles / channels at checkpoint | 0 / 0 | **1 / 7** |

The α run recovers all **53 liquid-failure profiles** from the preceding
candidate. The remaining M0 loss is the previously identified ice profile:
target `(i,j,k)=(1,168,33)` finishes with QI word `00000002` and NI=0.
This variant does not change the QI boundary path. Four previously existing
receiver cells with QC>0, NC=+0 before KDM finish with QC=NC=+0 in both runs;
they are not additional final moment failures.

Relative to the corresponding PR #475 same-input checkpoints, control changes
14 `QNCLOUD` elements. α changes 58 `QNCLOUD` and 54 `RE_CLOUD`
elements. The comparison covers 652 variables and 322,426,586 numeric
elements per case. Within this variant, trace off/on checkpoints are byte
identical. The between-variant changes are separate from that noninterference
claim.

## Offline replay

```bash
python3 -m harness.evidence.native_qnc_live_guard_2026-10-30.replay
```

The replay verifies packet files, currently executed calculation sources,
parent PR #475 evidence, and redoes the saved-word donor search, shared-face
mirroring, exact residual signs, f32 mode envelope, tendency/RK joins, and
selected final moment checks. It has **zero host, KDM, RTTOV, or optimizer
calls**. Full M0 counts and full checkpoint element comparisons come from the
four private host outputs and are linked by checkpoint and receipt hashes;
the complete private arrays cannot be reconstructed from this public packet.

The selected α checkpoint still loses one original M0 profile and seven
channel cells. Therefore a whole-M0 RTTOV cost, an accepted analysis, and a
second assimilation are **not** reported. The raw NC coordinate has no
certified physical particle-number unit or domain-wide conservation measure.
