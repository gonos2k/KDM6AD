---
title: KDM6AD S16 freeze-heat replay 2026-09-25
type: source
date: 2026-09-25
---
# KDM6AD S16 freeze-heat replay — 2026-09-25

The retained v14 arithmetic fixture reports a loop-2, column-3, level-0
one-ULP temperature difference. Both backends start from `t=0x43739698` and
have identical f64 `pinuc`, `pfrzdtc`, and `pfrzdtr` bits. Fortran records
`xlf=0x488740A0`, `cpm=0x447B5809`; C++ records
`xlf=0x488911E0`, `cpm=0x447B36A5`. Given the retained operands and declared
source-order model, an independent replay reproduces the Fortran post-freeze
`t=0x437396BA` and C++ `t=0x437396BB` exactly. The executables did not emit
intermediate products/sums, so this demonstrates sufficiency under the model,
not the actual runtime operation sequence. The replay trace is in
`harness/evidence/REPORT_S16_freeze_heat_replay_2026-09-25.md`.

The v14 source finding attributes the operand difference to Fortran fixing
`xl` and `cpm` at kernel entry while C++ recomputes them at each subcycle. This
is a conditional explanation for the retained fixture, not a decision-grade
current-source finding; under the replay model, the f32 store turns the
sub-ULP coefficient contribution into one ULP in this fixture.
This is separate from [[KDM6AD Forward Parity]]'s C4 G3.3 ULP-envelope gate.

The v14 four-case result remains withdrawn. A current debug-only verifier load
of the retained bundles fails closed because the Fortran manifests omit the
required `evidence_tree_sha256`. The exact Gate A report is present in the
source tree, but the raw bundles do not satisfy the current evidence contract.
The retained legacy module hash (`9354141b…`) also differs from the current
private host source hash (`fc0a72d3…`), so the archived run does not attest the
current source bytes. Therefore this bounded replay does not close S16 or
approve parity.

Sources: `harness/evidence/FINDING_cpm_xl_recompute_v14.md`,
`harness/evidence/REPORT_S16_freeze_heat_replay_2026-09-25.md`, and
`harness/evidence/CHECKLIST_system_gates_2026-09-25.md`.
