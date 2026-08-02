# The `mstep ≡ 1` window and the resolvable window do not overlap enough to give an order

Correcting a claim this branch made. `FINDING_refinement_design_v1` / STATUS said
column 3's erratic orders make §9's obstacle a **sweep-design** problem, "not an
intrinsic property of the fixture — a chain over which `mstep` is constant would
give column 3 a valid domain."

Such a chain exists. It is **two members long**, and a successive order needs three.

## Measured: where `mstep` bottoms out

Rain-chain `mstep`, from the SHA-pinned overlay (`--dump`):

| nsplit | h (s) | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| 3 | 100 | 1 | 5 | 10 |
| 6 | 50 | 1 | 3 | 5 |
| 12 | 25 | 1 | 2 | 3 |
| 24 | 12.5 | 1 | **1** | 2 |
| 48 | 6.25 | 1 | 1 | **1** |
| 96 | 3.125 | 1 | 1 | 1 |

## Measured: where the fixture stops resolving

Extending the chain to N = 192, 384, 768 (h down to 0.39 s), the successive
differences stop falling and **start growing**:

| h (s) | 100 | 50 | 25 | 12.5 | 6.25 | **3.125** | 1.5625 | 0.781 |
|---|---|---|---|---|---|---|---|---|
| `th` | 2.98e-2 | 1.50e-2 | 8.42e-3 | 5.55e-3 | 2.72e-3 | **1.46e-3** | 2.69e-3 | 6.41e-3 |
| `mass` | 2.82e-5 | 1.90e-5 | 3.92e-6 | 2.21e-6 | 2.19e-6 | **6.46e-7** | 7.24e-7 | 2.37e-6 |

A consistent discretization cannot produce **growing** differences under
refinement. Re-running any member is bit-identical, so this is not
nondeterminism — it is accumulated f32 roundoff over an increasing number of
kernel calls, overtaking a discretization error that has become smaller than it.
The minimum is at **h = 3.125 s**, so members finer than that are noise-dominated
and the finest trustworthy member is h = 3.125.

## Why that leaves no order

`E_h = |X_h − X_{h/2}|`, and an order needs two consecutive `E`s — so a clean
order at `h_b` involves three members down to `h_b/2`, and needs `h_b/2 ≥ 3.125`.
The finest clean order is therefore **12.5 → 6.25**.

| column | `mstep ≡ 1` from | clean orders inside that window |
|---|---|---|
| 1 | h = 100 (always) | **four** — `+1.969, +1.002, +1.000, +1.002` |
| 2 | h = 12.5 | **one** — `+0.066` |
| 3 | h = 6.25 | **none** |

Column 1 confirms first order to three decimals over three consecutive levels.
Column 3 — the column the question is about — has a `mstep ≡ 1` window containing
members h = 6.25 and 3.125 only, which yields **zero** successive orders.

## What this corrects

The earlier claim is **withdrawn for this fixture**. Making `mstep` constant is
necessary and not sufficient: the chain must also be long enough *inside* that
window to estimate an order, and here the window opens (h ≤ 6.25) two levels
above where the fixture stops resolving (h < 3.125).

A fixture that would work needs sedimentation slow enough that `mstep` reaches 1
by **h ≈ 25 s**, giving three members (25, 12.5, 6.25) above the noise floor —
roughly 4× slower fall speeds than column 3's. That is a **fixture** requirement,
and it converges with the smooth-cold-fixture requirement already recorded under
§6, rather than being a separate need.

## One positive result

Column 3's ρΔz **ice number** does converge across the whole chain, including
where its water does not: `+1.173, +0.799, +1.461, +0.863, +1.121, +1.029, +1.052`
— first order, and cleanest in the fine regime. So the ice-number channel has a
measurable order on this fixture even though column water does not.

## Limits

- **Only the rain-chain `mstep` is instrumented.** Ice sedimentation runs on
  `mstep_i` (`module_mp_kdm6.F:1284`), which the overlay does not emit, so the
  table above does not establish the sub-step count governing the ice channel.
  Adding it is another anchored overlay site.
- The noise floor is a property of this fixture at f32 and this 300 s window; it
  is not a general statement about the kernel.
- Synthetic fixture throughout. Nothing here is a C4 verdict.
