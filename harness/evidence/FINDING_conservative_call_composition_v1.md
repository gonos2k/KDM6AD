# The conservative call-composition defect: the `ni` entry clamp, propagated by the interface's inflow

Owner P0. The conservative variant does not satisfy time-step composition:

```
Φ_legacy(300)  ==  Φ_legacy(100) ∘ Φ_legacy(100) ∘ Φ_legacy(100)      bitwise, 132/132
Φ_cons(300)    !=  Φ_cons(100)   ∘ Φ_cons(100)   ∘ Φ_cons(100)        18 records, ΔT ≤ 2.67e-03 K
```

Both arms refresh `cpm`/`xl` three times, so this is not the thermodynamic policy.

## It is one boundary, and the design space is exhausted

Holding dtcld at 100 s forces every segment to be a multiple of 100, so boundaries
can only fall at t = 100 and t = 200. Both are measured:

| boundaries | conservative |
|---|---|
| t = 100 (`100,200`) | **0 / 144** — free |
| t = 200 (`200,100`) | **18 / 144** |
| both (`100,100,100`) | 18 / 144 — **bitwise identical to `200,100`** |

The whole effect is **one boundary, at t = 200 s**.

## What fires there

Of the ten prognostic clamps `kdm6_step` applies once per call
(`runtime.cpp:424-436`), exactly one is out of range at t = 200:

```
ni in [0, 1e6]   fires at 4 cells, extreme value 4.8151e+06
```

Every other clamp is inert. **The same clamp fires identically in the legacy run**,
which is why cap-firing alone was refuted as the explanation — it is necessary, not
sufficient.

## The propagation path, measured

| set | cells |
|---|---|
| `ni` clamped at the boundary | col 3 **k0, k1, k2, k3** |
| diverging by t = 300 | col 3 **k0, k1, k2** |
| divergence ⊆ clamped | **true** |
| clamped but not diverging | **k3 only** |

**k3 is the top level.** It is the cell with no inflow from above — established
independently by the mean-particle-mass control, where the top level reads exactly
1.0000 in every run while every level below departs.

So the two conditions and their conjunction match the measurement exactly:

1. the `ni` clamp perturbs the state at a call boundary — fires in **both** variants;
2. the conservative interface's **inflow transfer** carries that perturbation
   downward — acts in **every cell except the top**;

and the divergence is precisely `clamped ∩ has-inflow`. Legacy satisfies (1) and not
(2), and shows zero divergence.

## What this does and does not establish

**Established.** The effect is confined to one call boundary; the only clamp active
there is `ni`; the diverging cells are exactly the clamped cells that receive
inflow; and the one clamped cell without inflow does not diverge.

**Not established — sufficiency.** Showing that *suppressing* the clamp removes the
divergence would make this causal rather than a matched-conditions argument, and
that needs a code change inside frozen C++. The argument here is that two
independently-measured necessary conditions intersect exactly in the observed set,
with the non-intersecting cell behaving as predicted.

**Operational relevance.** A host that splits a microphysics call — a DA window, a
checkpoint/recompute adjoint, a different tile or rank decomposition — changes how
often the per-call `ni` clamp fires. Under legacy that is free; under the
conservative interface it is not. That is the reason this matters before C5 rather
than being a synthetic curiosity.

**Not measured.** Whether the same holds on a real case, at operational `ni`
magnitudes, or for the other nine clamps on a fixture that pushes them out of range.
