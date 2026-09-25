# v14 hypothesis: sub-cycle `cpm` and `xl` explain the retained freeze-heat difference

> [!warning] Status: withdrawn evidence; bounded, conditional interpretation only
>
> The four-case artifact `g33m_v14_fourcase_result.json` is withdrawn with
> `valid_for_decision: false`, and current bundle validation rejects the retained
> Fortran manifests because they lack `evidence_tree_sha256`. The captured
> streams and replay below support a **conditional** explanation for this
> fixture: if the retained operands and source-order model describe the executed
> arithmetic, differing `xlf`/`cpm` values are sufficient to reproduce the
> stored one-ULP difference. The old run does not establish a current-source,
> decision-grade root cause. See
> `REPORT_S16_freeze_heat_replay_2026-09-25.md` for the current evidence boundary.

Protocol v14. The retained capture is consistent with a semantic difference in
the coefficient operands; f32 storage turns its sub-ULP contribution into a
one-ULP state difference under the replayed operation sequence. This is a
bounded arithmetic interpretation, not an approved production root cause or
parity disposition.

Both halves matter and were previously run together as "semantic divergence, not
rounding" (owner review §6). The continuous coefficient contribution at the seed
cell is

    Δc · Σrates ≈ 7.1e-06 K        against   ULP(t at 243.6 K) = 1.526e-05 K
                                             ⇒ ≈ 0.46 ULP

so the analytic difference is **sub-ULP**; under the replay model it appears as
a whole ULP in the stored state because it lands across a rounding boundary.
The retained operands and replay leave no residual difference in that model,
but the executables did not emit each intermediate store, so this cannot rule
out an unrecorded runtime order/width difference at decision grade. The observed
1 ULP is still a storage-rounding outcome. Both numbers belong in the record:

| quantity | value |
|---|---|
| analytic coefficient contribution | 7.1e-06 K ≈ **0.46 ULP** |
| stored f32 state difference | **1 ULP** (`0x437396ba` → `0x437396bb`) |

## The reference

```fortran
!  latent heat for phase changes and heat capacity. neglect the
!  changes during microphysical process calculation
!  emanuel(1994)
   do k = kts,kte_in
     do i = its,ite
       cpm(i,k) = cpmcal(q(i,k))      ! F:893
       xl(i,k) = xlcal(t(i,k))        ! F:894
     enddo
   enddo
```

F:893–894 sit **before** `do loop = 1,loops` (F:934), and no outer loop encloses
them. `cpm` and `xl` are therefore fixed for the whole kernel call — the comment
states the approximation explicitly.

## The port

`preamble()` computes them from the state it is given:

```cpp
auto cpm = thermo::compute_cpm(state.qv, params.thermo);   // coordinator.cpp:416
auto xl  = thermo::compute_xl(state.t,  params.thermo);    // coordinator.cpp:417
```

and `runtime.cpp:625` calls `preamble(cur_pyc, …)` **inside** the sub-cycle loop,
with that sub-cycle's state. `pre_core_view(pre)` is annotated "ENTRY xl/cpm/…
(Fortran-fixed)", and within one micro step it is fixed — but "entry" there means
the entry of THAT OUTER LOOP, not of the kernel call.

Under the source versions and retained captures used by v14, the reported
behavior is: **the reference fixes them once per kernel call; the port
recomputes them at each sub-cycle entry.** That predicts agreement on the first
sub-cycle and divergence from the second onward. The withdrawn artifact reports
this pattern:

| loop | `cpm` cells differing | Fortran distinct | C++ distinct |
|---|---|---|---|
| 1 | **0 / 12** | 3 | **3** |
| 2 | 12 / 12 | 3 | 12 |
| 3 | 12 / 12 | 3 | 12 |

The retained Fortran capture reports three values (1005.34186, 1005.35870,
1005.37555) byte-identical across all three loops. Because the underlying
Fortran manifests fail current attestation, this is not a current-source claim.

## The retained measurement (`micro_freeze_heat`, loop 2)

The retained capture reports `cpm` as each backend used it:

| | distinct values across the 12 cells |
|---|---|
| Fortran | **3** — one per column, constant in k |
| C++ | **12** — one per cell |

The three captured Fortran values (1005.34186, 1005.35870, 1005.37555) order exactly with
the **kernel-entry** `qv` (1.000e-3, 1.020e-3, 1.040e-3, each k-constant per
column on this fixture). The twelve C++ values track the loop-2 `qv`, which has
evolved away from entry — most in column 3, where `qv` has fallen to 3.2–4.2e-4.

At the seed cell (loop 2, column 3, k 0):

| field | Fortran | C++ | |
|---|---|---|---|
| `t_pre_freeze` | 0x43739698 | 0x43739698 | identical |
| `pinuc` (f64) | 1.64092947e-09 | 1.64092947e-09 | **identical** |
| `pfrzdtc` (f64) | 1.84655769e-06 | 1.84655769e-06 | **identical** |
| `pfrzdtr` (f64) | 3.32974268e-08 | 3.32974268e-08 | **identical** |
| `xlf` | 276997.0 | 280719.0 | **+1.3%** |
| `cpm` | 1005.37555 | 1004.85382 | **−0.05%** |

The retained operands report all three freeze rates bit-identical at f64. Under
those operands, the coefficient `c = xlf/cpm` is 275.52 against 279.36,
**1.4%** different.

Under the source-order replay, that coefficient difference is sufficient to
account for the captured `t` difference:

    Δc · pfrzdtc ≈ 3.84 × 1.847e-6 ≈ 7.1e-6
    ULP(t) at 243.6 K            = 1.526e-5
    ⇒ ≈ 0.46 ULP  →  1 ULP in the stored t

## What the retained replay supports

The per-leg freeze replay

    c  = f32(xlf/cpm);  t2 = f32(t_pre + c·pinuc);  t3 = f32(t2 + c·pfrzdtc)
    t4 = f32(t3 + c·pfrzdtr)   ==   micro_post_freeze.t

the withdrawn artifact reports **0/12 misses on all four legs, all three loops**.
For the seed cell, the follow-up replay independently reproduces each retained
post-freeze `t` from the raw operand bits. This supports the interpretation
that the captured `xlf` and `cpm` values are sufficient under the declared
arithmetic model. It does not prove the actual executables emitted these
intermediates: the capture records operands and final `t`, not each production
product/sum/store, and the old Fortran module hash differs from the current
private source hash.

## Scope and caveats

- **Reported variant-independent behavior.** The retained Fortran legs agree
  and the retained C++ legs agree at the seed, so the bounded observation is
  shared across the two variants. It does not adjudicate conservative-interface
  parity.
- **The measured 1-ULP is fixture-specific.** Under the retained operands, the
  coefficient contribution is about 0.46 ULP and crosses an f32 storage
  boundary. This does not establish materiality in a real case.
- **Which behavior is correct is unresolved.** The reference source states its
  approximation deliberately (Emanuel 1994). Selecting either coefficient
  policy requires owner adjudication; this finding authorizes no code/default
  change.

## A comparator gap this exposed, and closed

The v14 comparator first reported the divergence at loop 1, column 1, `xlf` — a **warm**
cell (289 K) where Fortran applies the `xlf = xlf0` override at F:1517 and the
C++ does not. All three freeze rates are zero there, so the coefficient is
multiplied by zero and cannot move `t`. The comparator had no branch-activity
filter for stage records, so it named a value the arithmetic did not use — the
same class of defect owner review §3 raised for `micro_qr_operands`.

`g33_activity` closes it. The REFERENCE defines activity (taking it from the port
would let a port bug decide which port bugs are visible), and non-causal records
are routed to the same diagnostics-only channel the gate-inactive op lanes
already use — kept in the artifact, out of the verdict.

In the withdrawn artifact, the filter moved the reported answer:

| | first divergence | diagnostics |
|---|---|---|
| before | `micro_freeze_heat` L1 col 1 `xlf` | — |
| after | `micro_freeze_heat` **L2 col 3** `xlf` | 44 legacy / 43 conservative |

and the withdrawn artifact reports the same identity for both variants. Two
activity rules are implemented:
`xlf`/`cpm` are read only where some freeze rate is nonzero, and a qr operand is
read only on the arm its cell takes — with the branch recomputed from the base
state rather than taken from the producer's own `cold_gate`, which stays visible
precisely because it is the producer's claim.

## Also retracted here

The v14 design was motivated by a precision hypothesis — the C++ comment calls
D4's rate an "f32 rate" where the reference declares all three
`double precision`. That is a real documentation defect, but it **cannot** be the
mechanism: `t += c·rate` rounds to f32 on every store, so the width of `c·rate`
can only change the result when `step ≳ t`, i.e. `rate ≳ 0.73 kg/kg` against the
~1e-8 rates here. A search over 400 000 values found zero discriminating cases;
at 1.5 kg/kg they do differ, confirming the comparison works.
`test_the_rate_precision_CANNOT_move_t_at_physical_magnitudes` pins it.

The withdrawn artifact's verdict is `INCONCLUSIVE`; it is not valid for a
decision. S16 remains OPEN pending current-source attested bundles and owner
review. Attribution is not approved by this finding.
