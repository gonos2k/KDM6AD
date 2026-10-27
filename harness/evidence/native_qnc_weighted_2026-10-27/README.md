# Saved QNC seven-cell weighted ledger — 2026-10-27

This **offline** packet uses the immutable PR459 19-file shared-face packet.
It checks the old manifest SHA-256 and every inventoried byte, then verifies
that the hardened current analyzer retains all previously published case
results and adds a passing target `MSFTY` join. It calculates an exact-rational
coordinate ledger using the saved seven-cell binary32 face, metric and
tendency words. No host, KDM, RTTOV or optimizer call is made.

The current Fortran trace producer clears owner state before selection can
return and requires current QNC/RK3 selection at every writer. A compiled
serial-call regression covers an owner followed by a nonselected scalar.
This correction has **not** been used in a new host execution. PR459's
published source/build/run identities stay historical; its numerical results
are compared without altering its packet or manifest.

## Reproduction

From the repository root:

```sh
python3 -m harness.evidence.native_qnc_weighted_2026-10-27.replay
```

The command validates this packet's files/source pins, the PR459 packet and
both analyses, then reproduces [analysis.json](analysis.json) byte for byte.
It prints `REPLAY_PASSED` with zero model calls.

The exact saved-face algebra uses
\(w_i=-1/(\mathrm{MSFTX}_i\mathrm{RDZW}_i)\). Six internal faces contribute
12 correction/low-order pairs; all cancel exactly under the recorded metric
coefficients. The weighted face total equals 30 recorded perimeter incidences.
The recorded tendency words differ slightly from the exact saved-operand
expression because they came through finite-precision stage updates:

| Raw numerical quantity | Control | Alpha0.25 |
| --- | ---: | ---: |
| Exact weighted face/perimeter sum | −27,767,629,636.3833 | −27,767,544,586.4499 |
| Weighted recorded tendency change | −27,767,630,848.1075 | −27,767,543,347.6306 |
| Recorded minus face expression | −1,211.7242 | +1,238.8193 |

See [the derivation and limits](../../../docs/NATIVE_QNC_WEIGHTED_LEDGER_20261027.md).
This is a numerical coordinate identity, **not** a certified physical NC
unit or closed state/domain number budget. No admissible candidate, candidate
RTTOV cost or second assimilation is established.
