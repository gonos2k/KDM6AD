# Both ledgers: conservative closes them, refreshing coefficients loses on both

Owner review §8.2. The convergence experiment cannot select a thermodynamic policy
on this fixture — the domain where an order is well defined and the domain where the
policy acts are disjoint. The enthalpy ledger does not have that problem: a
conservation residual is a per-run quantity and needs no asymptotic regime, so it
works in the cold column where convergence does not.

## Construction

All constants from `module_model_constants.F`, the authority both legs compile
against: `cpd = 7·r_d/2 = 1004.5`, `cpv = 4·r_v = 1846.4`, `cliq = 4190`,
`cice = 2106`, `XLV = 2.5e6`, `XLF = 3.5e5`, `XLS = 2.85e6`.

Referenced to `T0 = 273.15`:

```
h_d = cpd (T-T0)          h_v = cpv (T-T0) + XLV
h_l = cliq (T-T0)         h_i = cice (T-T0) - XLF
```

so `h_v - h_l = XLV`, `h_l - h_i = XLF`, `h_v - h_i = XLS` at T0. `XLS - XLV = XLF`
exactly in the code's own constants, so this construction cannot disagree with the
code's latent heats at the reference temperature.

```
H_col    = Σ_k ρ_k Δz_k [ h_d + q_v h_v + (q_c+q_r) h_l + (q_i+q_s+q_g) h_i ]
residual = (H_end − H_start) + H carried out by precipitation
```

With no external forcing the residual should be zero.

**This is deliberately not the code's own `xlcal`/`cpmcal` approximation**, and that
is the point of §8.2: §3.1 observes the code's `dxlf/dT = c_l − c_pv = 2343.6` where
a Kirchhoff-consistent value is `c_l − c_i = 2084`, a 12.5% gap. A ledger built from
the code's own formulas would be nearly satisfied by construction and would measure
almost nothing. This one measures the distance from consistent thermodynamics.

Both endpoints are emitted by the driver rather than one being re-read from the
fixture, so the ledger's two ends come from a single source.

## Result

Residual relative to column enthalpy, `arithmetic_multisubcycle_v1`, 300 s:

| leg | h (s) | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| **Fortran** (call-fixed coefficients) | 100 | −1.107e-05 | −1.826e-02 | −5.763e-03 |
| | 50 | −4.581e-06 | −1.840e-02 | −5.111e-03 |
| | 25 | −5.424e-06 | **−8.284e-03** | **−3.690e-03** |
| **C++ legacy** (sub-cycle-refreshed) | 100 | −7.570e-06 | −2.704e-02 | −5.675e-03 |
| | 50 | −3.219e-06 | −2.717e-02 | −5.455e-03 |
| | 25 | −3.957e-06 | **−1.271e-02** | **−5.076e-03** |
| **C++ conservative** | 100 | −3.009e-06 | −1.045e-04 | −2.580e-04 |
| | 50 | −3.219e-06 | −8.864e-05 | −3.510e-04 |
| | 25 | −3.957e-06 | **−1.120e-04** | **−3.541e-04** |

## 1. The conservative interface closes the ledger far better

At h = 25 s, column 2: **−1.12e-04 against −1.27e-02**, about **110×** better than
C++ legacy and **70×** better than the Fortran reference. Column 3: −3.54e-04
against −5.08e-03 and −3.69e-03, roughly **10–15×**.

This is the first result in this line of work that favours the conservative variant
on physical rather than parity grounds, and it comes from a budget rather than a
comparison against another implementation.

The two behave differently under refinement as well. The legacy residuals **shrink**
with h — Fortran column 2 goes −1.83e-2 → −8.28e-3 — so they are largely
discretisation error. The conservative residual **does not**: −1.05e-4, −8.86e-5,
−1.12e-4 is a floor. So conservative has a small residual that refinement does not
remove, and legacy a large one that it does. On this chain legacy never gets close:
at the finest member measured it is still two orders out.

## 2. Refreshing the coefficients closes the ledger WORSE

C++ legacy against the Fortran reference, same variant, differing in the
coefficient policy among other things:

| | col 2 | col 3 |
|---|---|---|
| Fortran, call-fixed | −8.284e-03 | −3.690e-03 |
| C++, sub-cycle-refreshed | −1.271e-02 | −5.076e-03 |

The refreshed policy is **~1.5× worse** in column 2 and **~1.4× worse** in column 3,
at every h measured, not only the finest.

That is the direction owner review §8 raised as a possibility: a policy can improve
operator consistency — evaluating the coded formula more faithfully, more often —
while making the physical enthalpy budget worse. Here the physical ledger prefers
the reference's call-fixed policy.

**This does not isolate the policy.** The two legs differ in every part of the port,
not only in where `cpm`/`xl` are computed, so the 1.5× is the two implementations
compared, not the two policies. Isolating it needs the reference-faithful C++
counterfactual — C++ arithmetic with kernel-call-fixed coefficients — which is
inside frozen code and needs a scoped freeze-lift. What the measurement does
establish is that **"refreshes more often, so it is more physical" is not supported**:
on the one physical budget available, the refreshing leg is the worse one.

## What the numbers do and do not mean

Approximations, stated because they bound the reading:

- Mixing ratios are treated as per unit dry air while ρ is moist density.
- The precipitation enthalpy flux is evaluated at the bottom-level temperature.
- The reference enthalpies are the Kirchhoff-consistent set, not the code's.

All three are **common to every leg**, so a comparison of residuals between legs is
meaningful even where an absolute residual is not. No claim is made that any leg
"should" have closed to roundoff against this ledger.

Column 1 is near-identical across all three legs (−3e-6 … −5e-6) and does not
discriminate — the same structural reason as the convergence experiment: 288–290 K,
no ice, so the cold-phase terms the policy scales are inactive.

## The operator-consistency ledger (§8.1), on the same data

§8 asks for two ledgers because they answer different questions and can disagree:

* **§8.2 physical** — does the code agree with *consistent* thermodynamics?
* **§8.1 operator** — does the code agree with *its own equations*?

The second is the same column integral built from the code's own forms
(`cpmcal` F:818, `xlcal` F:819, `xlv1 = cl − cpv = 2343.6` F:3406):

```
h_op = cpm(qv) (T-T0) + xl(T) qv - xlf(T) q_ice
```

Every one of the code's heat updates has the form `cpm dT = L dq`, so a conversion
leaves `h_op` flat: vapour→liquid gives `cpm dT + xl dqv = 0`, liquid→ice gives
`cpm dT − xlf dq_ice = 0`. Liquid carries coefficient zero because the code applies
no latent heat to it, and departing ice carries `−xlf` out because sedimentation
moves mass with no temperature change. **One** `cpm` for the whole parcel, not
per-phase heat capacities — that is the code's own "neglect the changes during
microphysical process calculation" approximation (F:886-888), and reproducing it is
the point.

`xl`/`xlf` are evaluated at the **local** temperature for every leg. The reference
holds them at the kernel-entry value and the port refreshes them per sub-cycle;
using one convention here keeps the ledger from encoding either policy's answer.

Relative residual at h = 25 s:

| leg | | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| Fortran (call-fixed) | §8.1 | +3.342e-05 | **−7.227e-03** | −1.296e-03 |
| | §8.2 | −5.424e-06 | **−8.284e-03** | −3.690e-03 |
| C++ legacy (refreshed) | §8.1 | +3.399e-05 | **−1.115e-02** | −2.024e-03 |
| | §8.2 | −3.957e-06 | **−1.271e-02** | −5.076e-03 |
| C++ conservative | §8.1 | +3.399e-05 | **+3.225e-06** | +5.117e-04 |
| | §8.2 | −3.957e-06 | **−1.120e-04** | −3.541e-04 |

### The feared trade-off does not appear

§8 raised the possibility that a policy improves the operator ledger while making
the physical one worse. **On this fixture the two ledgers agree**, in both
directions:

- **Conservative wins on both.** Column 2: `+3.2e-06` against the reference's
  `−7.2e-03` on the operator ledger — about **2200×** — and `−1.12e-04` against
  `−8.28e-03` on the physical one, about **74×**.
- **Refreshing loses on both.** C++ legacy against the Fortran reference is
  **~1.5× worse** on the operator ledger and **~1.5× worse** on the physical one,
  at every h measured.

So there is no compensation to weigh: on this fixture the refreshing leg is worse
against consistent thermodynamics *and* against the code's own equations. That is a
cleaner negative result than §8 anticipated, and it removes the "improves one,
worsens the other" reading from the table.

The same caveat governs it: the two legs differ in every part of the port, so
"refreshing loses" is implementation against implementation until the
reference-faithful C++ counterfactual exists.

Column 1 shows a small residual on both ledgers (+3.3e-05, −4e-06) that is
identical across all three legs and does not shrink with h. It is a floor of the
construction, not a discriminator — consistent with column 1 having no ice.

## Not established

- The 1.5× is implementation against implementation, not policy against policy.
- The operator-consistency ledger of §8.1 — does the code agree with its OWN
  equations, per process — is not built. Both are needed for a policy decision, and
  they can disagree.
- Why the conservative residual sits at a floor rather than shrinking is not
  diagnosed.
- Synthetic fixture, 300 s, microphysics only. No operational claim.

Policy selection remains owner adjudication.
