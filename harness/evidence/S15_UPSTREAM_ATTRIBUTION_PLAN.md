# S15 upstream attribution: bounded confirmation plan

**Status: OPEN. Plan only.** This defines the next public-side capture contract
after PR #283. It records no native operands, changes no host defaults, and
makes no physical-cause claim.

## Evidence boundary

The step-2 owner-5 capture recorded 87,937 nonnegative-to-negative QIB update
occurrences and six first-event witnesses. Those rows replay the RK store
exactly, but expose no upstream face operands. The same discovery emitted 258
melt rows, each with `rhox_valid=0`; they cannot support melt thermodynamic
attribution. Keep both findings as context only. S15 remains OPEN.

## Source-pinned path

The private runnable host was inspected read-only. These anchors identify the
future overlay points; only source paths, line ranges, and SHA-256 pins are
published here, never private source text or runtime operand values.

| Private source anchor | SHA-256 | Capture purpose |
| --- | --- | --- |
| `dyn_em/solve_em.F:2847-2863` | `d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f` | Owner-5 call site and RK-store handoff |
| `dyn_em/module_em.F:1265-1344, 1680-1724, 1750-1774` | `7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7` | Advection dispatch, source-order tendency construction, and RK update |
| `dyn_em/module_advect_em.F:3452-3547, 3549-3649, 4230-4346` | `58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d` | Ordinary Y, X, and Z face fluxes and divergence contributions |
| `dyn_em/module_advect_em.F:7733-7779, 7790-7885` | same file pin above | Positive-definite branch low-order flux limiter and Z/X/Y tendencies |

The overlay should carry one witness from each already pinned step-2
owner/RK/tile slot into the upstream producer and back to the RK store. Record
the actual executed branch at dispatch. RK1 and RK2 use the ordinary Y/X/Z
advection path without the positive-definite limiter. RK3 uses that branch only
when `rk_step == rk_order` and active `adv_opt == POSITIVEDEF`; the confirmation
contract pins `rk_order=3`, `adv_opt=POSITIVEDEF`, and the observed dispatch.
Do not infer branch execution from the RK number alone.

For ordinary RK1/RK2, retain the actual signed Y, X, and Z face-flux operands
that enter the selected cell's divergence and each source-ordered directional
contribution. For RK3 positive-definite advection, retain the corresponding
low-order and high-order face fluxes, low-order outflow / available-state
limiting decision and scale, and the final source-ordered directional
contributions. Preserve the executed direction sequence explicitly: ordinary
Y/X/Z, PD Z/X/Y. In both paths, retain the aggregate `advect_tend` at the
`rk_update_scalar` boundary, its `msfty` multiplier, then `sc_tend` as a
separate input and the resulting source-ordered tendency before the RK store.
Also capture the existing RK inputs and output as raw f32 words. Instrument
the executed path in place; replay must not reconstruct hidden intermediates
from rounded text or recompute a different operation order.

## Six-slot and coordinate contract

The exact source-declared schedule is pinned independently of discovery keys:

| Timestep | RK | Owner | Tile J range | Tile slot |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 1 | 5 | 1–142 | 1 |
| 2 | 1 | 5 | 143–283 | 2 |
| 2 | 2 | 5 | 1–142 | 1 |
| 2 | 2 | 5 | 143–283 | 2 |
| 2 | 3 | 5 | 1–142 | 1 |
| 2 | 3 | 5 | 143–283 | 2 |

The ordered six coordinates are projected into
[`s15_upstream_coordinate_projection_2026-09-27.json`](s15_step2_public/s15_upstream_coordinate_projection_2026-09-27.json),
SHA-256 `d3c84443c3f095eedfd435dd7f780350cdc2d4126eb0c550b3cf281585bbfc11`.
This projection is derived from the public discovery file
[`s15_native_step2_qib_witnesses_public_2026-09-26.json`](s15_step2_public/s15_native_step2_qib_witnesses_public_2026-09-26.json),
SHA-256 `6faed36e9f16354d117a8227fecff3a44d6f33839fb58782547f87b431cbc2aa`.
Treat coordinates only as repeatability targets: they are data-selected and do
not define the expected schedule or establish an independent physical
expectation. Confirmation must validate the separate projection digest and
require producer and RK-consumer records for the exact same six full
stage/tile/cell identities. A missing transition at a target, duplicate record,
slot mismatch, or unexpected branch fails confirmation; do not select a
replacement coordinate.

Every record should link the tuple `(step, rk, owner, tile, i, j, k)` across
dispatch, each selected face, directional tendency, aggregate `advect_tend`,
separate `sc_tend`, and RK store. Keep face orientation, neighboring-cell
side, active limiter flags, and the raw f32 values explicit. Tests should also
exercise zero-valued faces and sign changes so a serializer cannot silently
omit a face operand.

## Synthetic contract checks before any native work

- Pin the six summary keys from the source schedule, independently of the
  six coordinate targets.
- Require exactly one producer and one RK-consumer record per slot, joined by
  the full step/owner/RK/tile/cell key. Reject coordinate drift and stage mix.
- Accept only ordinary Y/X/Z records for RK1/RK2; require the RK3 branch flag
  and limiter fields when the pinned active config selects positive-definite
  advection.
- Require separate `advect_tend`, `msfty`, `sc_tend`, source-order tendency,
  and RK-store fields; reject omission, duplication, or stage mixing.
- Exercise signed face words, binary32 accumulation of already computed
  directional terms in the pinned Y/X/Z or Z/X/Y order, a changed coordinate,
  missing `sc_tend`, stage mixing, and dispatch mismatch. The standalone
  `harness/s15_upstream_contract.py` tests establish record shape, identity,
  and tendency-sum order only. They do not verify face-to-tendency divergence,
  the `advect_tend * msfty + sc_tend` operation against captured operands, or
  the RK-store equation.

Full face-divergence and RK source-order numerical replay remains OPEN and is a
required acceptance gate before treating a native capture as upstream
attribution. Structural contract success alone is not attribution evidence.

Only after the contract is reviewed should a separate native plan pin fresh
source/preprocess/object/link/executable identities, exact step-2 inputs and
run settings, the six discovery-coordinate targets, and a same-executable
logging-off control plus capture. Compare populated outputs bit-for-bit and
require byte-identical confirmation records. A passing capture can attribute
the observed store transition to recorded upstream terms; it does not by
itself establish mass conservation, thermal closure, a physical cause, or a
graupel policy.
