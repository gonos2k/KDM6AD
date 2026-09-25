# S16 freeze heat: bounded replay and current evidence status

This note preserves the v14 freeze-heat attribution and records an independent
source-ordered replay of its retained seed cell. S16 remains **OPEN**: the old
four-case result is withdrawn, and the retained Fortran bundles do not satisfy
the current evidence-tree attestation contract.

## Retained capture

The v14 fixture is `arithmetic_multisubcycle_v1`, fixture SHA-256
`71083cb34efacc112010d11a2365113cde00dca0810d8be882a812089e118d93`, manifest
SHA-256 `290ddce105b60deec9fbfa6d097842405b24c6aa920632e552572bd7b17aa271`.
The four captured legs are under `/Users/yhlee/kdm6ad-g33m-v14/`: C++ bundle
manifest SHA-256 `f323a7f9c4c612b9094a73de2d0ada6b5291a3b58cbae6142b3f7b12daca5270`, Fortran legacy manifest SHA-256
`ddc65e280bc0beb8dc32c8d1ca9b42a53dada375c2eca8279602104a51f26012`, and
Fortran conservative manifest SHA-256
`bf5f46965cde5c3ab8541211576f6d11ba43912ad0a9673f2da69d69c768869b`.
The Fortran manifests record GNU Fortran 15.2.0 and source commit
`fcb97638066a5233d4738c1c15fc19adbb46e8ad`; the compiled module hashes are
`9354141b…` (legacy) and `364a1319…` (conservative). The C++ producer commit is
the same, and the diagnostic executable SHA-256 is
`f2682e4dfae75238555b41b0d067ded01492490c0d88ec26eeedbd3a8d5cf907`.
The retained legacy Fortran binary is bound to module source SHA-256
`9354141b9e93aceb4a1c35e06bf673a5d4d916028877c0f84f729a301876b7dc`. The
current active private host file hashes to
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`, so the
retained executable is not bound to today's private source bytes. The current
file still has the kernel-entry `xl`/`cpm` assignments before the subcycle
loop, but that source read does not retroactively attest the older binary.

At loop 2, column 3, k 0, both Fortran legs have `t_pre_freeze=0x43739698`,
`xlf=0x488740A0`, and `cpm=0x447B5809`; both C++ legs have the same incoming
temperature but `xlf=0x488911E0` and `cpm=0x447B36A5`. All three applied
f64 rates are bit-identical on all four legs:

| Rate | Captured f64 bits |
| --- | --- |
| `pinuc` | `0x3E1C30E25582CD5D` |
| `pfrzdtc` | `0x3EBEFAE7A7F5767D` |
| `pfrzdtr` | `0x3E61E05D0E2E83BD` |

Fortran stores `t=0x437396BA`; C++ stores `t=0x437396BB` (C++ is one ULP
higher). The source branch facts at this cell are: `t_pre_freeze <= T0C` is
true; the homogeneous-freeze condition `t < T0C-40 K` is false and captured
`phom` is zero; and all three D2–D4 applied rates are positive. The v14 capture
does not emit boolean mask fields, so these masks are reconstructed from the
captured temperature/rates and checked against the source predicates, rather
than presented as independently emitted flags.

## Source-ordered f32/f64 replay

The replay uses f32 `c = f32(xlf/cpm)`, then for each declared f64 rate forms
an f64 product and f64 sum from the preceding f32 `t`, storing f32 after each
statement. These are independent replay intermediates derived from the retained
operands; the old executables did not emit each intermediate as a separate
record.

| Step | Fortran product f64 | Fortran sum f64 | Fortran stored f32 `t` | C++ product f64 | C++ sum f64 | C++ stored f32 `t` |
| --- | --- | --- | --- | --- | --- | --- |
| `c=xlf/cpm` | — | — | `c=0x4389C20B` | — | — | `c=0x438BAE78` |
| D2 `pinuc` | `0x3E9E570EC2C30D66` | `0x406E72D300F2B876` | `0x43739698` | `0x3E9EC382AA5C78FD` | `0x406E72D300F61C15` | `0x43739698` |
| D3 `pfrzdtc` | `0x3F40ABC1713798A4` | `0x406E72D72AF05C4E` | `0x437396B9` | `0x3F40E758D74306E7` | `0x406E72D739D635D1` | `0x437396BA` |
| D4 `pfrzdtr` | `0x3EE33D3D2F7F46B8` | `0x406E72D7333D3D2F` | `0x437396BA` | `0x3EE38202CE3D0796` | `0x406E72D7538202CE` | `0x437396BB` |

Given the retained operands and declared source-order model, the independent
replay reproduces each captured post-freeze value. In that replay, the one-ULP
difference first appears at D3's stored temperature and remains after D4. The
matching incoming `t` and rates, with differing `xlf` and `cpm`, make the heat
coefficient difference sufficient to explain the captured result under this
model; the production intermediates were not emitted, so the replay does not
independently establish the executables' operation order and widths. The
coefficient difference contributes about `7.1e-6 K` (0.46 ULP at this
temperature) before storage; f32 rounding turns it into a one-ULP state
difference. The v14 source finding traces the coefficient operands to
kernel-entry-fixed `xl`/`cpm` in Fortran versus per-subcycle recomputation in
C++, but the retained Fortran module hash differs from the current private
source. This remains a conditional port-behavior explanation pending current
attested evidence and owner review.

## Verification boundary

`g33m_v14_fourcase_result.json` is marked withdrawn and `valid_for_decision:
false` because its recorded verifier-semantics hash no longer matches the
current verifier. A current, non-mutating `--debug-only` load of the retained
bundles at source commit `4c417238` also fails closed as `INVALID_EVIDENCE`: the
legacy Fortran manifest is missing the current required `evidence_tree_sha256`.
The same required field is absent from both retained Fortran manifests. The
current verifier-semantics SHA-256 is
`7e6dfdcce4c1a057a638a8a1a59ba7aa520d8e1e86e981eb229f68f2d428e95a`; the
withdrawn v14 artifact records an older verifier contract. The Gate A report is
present in this source tree and its SHA-256 exactly matches the anchored value
`cff6cb64f36f818f4eeb655ab8e5ffe3423195bdd4509b88bf4c128d0564dbd2`; its
availability is not the blocker. No build or native campaign was run for this
recheck, and no replacement decision artifact was written.

The independent replay regression is in `harness/tests/test_g33_update_replay.py`.
It verifies the exact rate, product, sum, and store bits for both coefficient
sets. This is bounded arithmetic evidence only. It does not close the separate
C4 G3.3 legacy ULP-envelope comparison, certify operational host parity, or
authorize a default change. S16 stays OPEN pending current evidence bundles and
owner review.
