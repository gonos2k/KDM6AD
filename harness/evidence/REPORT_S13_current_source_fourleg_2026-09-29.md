# S13 current-source four-leg follow-up

**S13 remains OPEN / FAIL.** This run follows the call-entry `cpm/xl` correction
without replacing the historical Gate A result or the failed G3.3 ULP envelope.

The Fortran runner now has an explicit `active-20260929` source selection. It
checks the private mp37 SHA-256
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`
and mp237 SHA-256
`4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648`
before building. The default historical pins are unchanged. The verifier accepts
the new producer's complete source list and rejects an unknown source scope or
a selected module hash mismatch.

At public producer commit `74df01d2f46465a66a6d41303ef12906f1c12f6c`,
the `arithmetic_multisubcycle_v1` kernel fixture completed A/B/C for all four
legs. Both Fortran variants had equal A/B/C final physics (legacy 7,141 and
conservative 6,956 operation records). C++ completed three two-pass schedules,
with main `mstepmax` 9/10/7 and ice 1/1/1. The bundle manifest SHA-256 values
are:

| Bundle | SHA-256 |
| --- | --- |
| C++ A/B/C | `316ec7bfa83f632898c4f838703677f83d870722ebcd5026c411068c16d304ca` |
| Fortran mp37 A/B/C | `4876c11ad9ff89447df10e5dbd23b520b132a7ddc3d845eb54dd0e5044c8fde6` |
| Fortran mp237 A/B/C | `580de0fe73a61f9c067a22b06cc8599968bccca4fe99c798744f239847728f64` |

The current-source four-leg **debug-only, unanchored** comparison at verifier
commit `2cd7e85a1935b9617c81debe2ad037c1b3fc892a` is **INCONCLUSIVE**.
Both pairs first flag outer loop 1 `micro_freeze_heat.xlf`. Only `xlf` differs
in the selected operand group; `cpm` agrees. The C++/Fortran derived
`xlf/cpm` values in that cell are 387.4201965/348.1402893, while
the three sequential freeze-temperature stores all round to the same f32
word `0x43910000`; this observation does not resolve the later `xlf` consumers.
The debug result SHA-256 is
`a1e9da7b416855275646793464597cb18e3e56a5f386149213792a620d361791`.

The unchanged historical Gate A manifest fails against the active private
mp37 and wrapper SHA pins. Its four allowed edit clusters and two handoff
blocks still match, but that structural comparison is not a new authorization.
Thus the debug result is **not** a Gate B decision, and the original
77,852 > 77,312 and 2,188 > 1,164 ULP failures remain open. No production
physics, QC, tolerance, default path or physical number basis changed here.

Local verification ran the Fortran bundle, gate and verifier-identity focused
tests (115 passed)
and replayed the retained historical Fortran bundle plus both new active
bundles through the updated verifier. The private builds and raw bundles are
local and are not independently reproduced by public CI. The current-source
selector and verifier can be tested publicly without private host sources.
