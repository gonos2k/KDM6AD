# G3.3-M S13 run package

This directory contains the verifier-complete four-leg evidence, the current
decision JSON, and a replay of the loop-2 QR target cell. The concise interpretation is in
[`../S13_G33M_FOURCASE_R1_2026-09-25.md`](../S13_G33M_FOURCASE_R1_2026-09-25.md).

`decision.json` is the original decision-valid artifact produced by
`gateb_g33m_check.py` on clean verifier commit `955d8f2a` under CPython 3.11.14 /
NumPy 2.4.6. Its four producer legs are pinned to source commit `955d8f2a`. After
the S13 branch rebased onto `origin/main` `90727ff9`, the current verifier reran
from clean commit `336c70f4`; it returned the same decision-valid
`INCONCLUSIVE` verdict and first-divergence identity. That separate recheck
receipt is recorded in `run_context.json`; the canonical decision was restored
unchanged. It consumes the exact bundle copies stored here; their manifest
SHA-256 values are in
[`run_context.json`](run_context.json). The C++ root manifest contains an
`evidence_tree_sha256` for each algorithm. The Fortran manifests bind and
re-verify each A/B/C stream, executable, build provenance, and fixture.

The Fortran A/B/C executables are retained because the verifier hashes them.
Generated `.o`/`.mod` intermediates and the generated `module_mp_ovl.F` copies
were omitted: they are unnecessary to re-verify the saved run, and the overlay
files contain derived copies of private host source. The current verifier was
rerun on this trimmed package; it still returns `INCONCLUSIVE` for the same first
divergence.

`qr_update_replay.json` was derived with the checked-in
`harness/g33_update_replay.py` from the verified normalized bundles. It records
the raw bits and shows exact replay of the four loop-2 QR updates and the
loop-2 freeze-heat inputs. A replay miss count of zero does not promote the
G3.3-M verdict: the verifier still classifies the shared first divergence as
INCONCLUSIVE because other `xlf` consumers are not sealed by that replay.

The Fortran A/B/C bundles use the historical module pair pinned by the Gate A
report copied here. The active private host modules have different hashes; this
package is not their certification. No host/native WRF run was performed.

The original S13 exceedances remain **77,852 > 77,312 ULP** and
**2,188 > 1,164 ULP**. This run does not relax the gate or change defaults.
