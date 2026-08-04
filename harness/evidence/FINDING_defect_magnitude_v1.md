# The 9–15% is 0.2–0.7% of the initial column — and the "final column" figure was undefined

**Correction (owner P0-2).** The first version of this finding divided by
`closures()`'s `start` and `final`, which **accumulate over calls**: they are
`Σᵢ Nᵢ^pre` and `Σᵢ Nᵢ^post`, an inventory counted once per call, not the column's
initial and final state. Two consequences, and they are not the same size:

- **`of_final_column` = 0.2200 / 0.4507 / 0.7256% is withdrawn outright.** This
  fixture's column ends **empty** — window-final inventory is `0.000e+00` — so
  that fraction is undefined. What was published under that name is `R / N₁^post`.
- **`of_initial_column` survives, and now says why.** Exactly **one of twelve**
  calls carries any rain: the remaining microphysics empties the column between
  call 1's post-sed and call 2's pre-sed, so calls 2–12 have `start = final =
  R = 0`. Hence `Σᵢ Nᵢ^pre = N(t₀)` *on this fixture* and the number is unchanged
  — but it was right by coincidence, and the coincidence is now reported
  (`active_calls 1/12`) instead of being invisible.

On a fixture where several calls carry inventory the two quantities differ, and
the aggregate would be an inventory-weighted per-call mean rather than a fraction
of the initial column. Both are now computed and named separately.

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-MAGNITUDE-001` | **withdrawn → G33-MAGNITUDE-002** | — | The denominators were misnamed (owner P0-2). closures() accumulates x0 and x1 over calls, so `start`/`final` are sum_i N_i^pre and sum_i N_i^post -- an inventory counted once per call -- not the window's initial and final column. "Of the final column" is the worse error: this fixture's column ends EMPTY, so that fraction is undefined and the figure published under that name was R / N_1^post. |
| `G33-MAGNITUDE-002` | **active** | confirmed-with-scope | g33_fixture_multisubcycle_v1, legacy, h = 25 s, main chain. R/N(t_0) coincides with the inventory-weighted per-call mean ONLY because one call is active; on a fixture where several calls carry inventory the two differ and must not be conflated. The frozen-trajectory size bounds require a corrected-number counterfactual run to become forecast statements, which needs a production physics change and is not done. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §11. The headline number is `R_N / F_surface` — the creation residual over
the surface number **outflow**. That is the right denominator for *"is the
transport accounting closed"* and the wrong one for nearly every sentence a reader
writes next. Left alone, a number with one denominator invites the reader to
supply their own.

## The same residual, against every denominator that means something

Legacy, h = 25 s, main chain:

| denominator | col 1 | col 2 | col 3 |
|---|---|---|---|
| **/ surface flux** (the headline) | **15.0036%** | **13.3377%** | **11.8402%** |
| / interface throughput | 3.8606% | 3.4975% | 3.1963% |
| **/ initial inventory `N(t₀)`** | **0.2173%** | **0.4379%** | **0.6884%** |
| / summed call starts `Σ Nᵢ^pre` | 0.2173% | 0.4379% | 0.6884% |
| / final inventory | — | — | — |

The middle two coincide only because `active_calls = 1/12`. The last is
**undefined**: the window-final inventory is `0.000e+00`.

The same defect is a **large fraction of what left** and a **small fraction of
what is there** — a factor of 20–50 between the two readings. Both are true; only
one of them is what "the scheme creates 15% number" sounds like.

## What it does to particle size

A number error reaches reflectivity, fall speed or a radar diagnostic **only**
through the mean particle mass `q/N`. So that is where a meteorological argument
has to start — and it has to start from the right part of it:

All three rows below are **frozen-trajectory and segment-local**: `q` is held at
what this run produced, and the feedback of a corrected number on fall speed, the
size distribution and therefore `q` on every later sub-step is **not** included.
They bound nothing about a forecast (owner §5).

| | col 1 | col 2 | col 3 |
|---|---|---|---|
| total Δ(q/N) across the segment | −1.87% | −4.30% | −7.81% |
| defect's share, frozen | −0.22% | −0.45% | −0.72% |
| defect's implied Δ(diameter), frozen | −0.073% | −0.150% | −0.241% |

Turning these into forecast statements needs a **corrected-number counterfactual
run** — a production physics change, not done.

**The total is not the defect.** Sedimentation genuinely size-sorts — large
particles fall faster, so the mean particle mass of what remains really does drop.
Most of that −1.9…−7.8% is physics. The defect's share is the part attributable to
spurious number, and because a characteristic diameter goes as `(q/N)^(1/3)`, the
same fraction reaches diameter as a **cube root**.

So the specific readings the owner warned against are quantitatively excluded on
this fixture:

| tempting reading | actual |
|---|---|
| "column number rose 9–15%" | **0.22–0.69% of `N(t₀)`** |
| "mean diameter fell 3–5%" | 0.07–0.24%, **frozen-trajectory only** |

## Why the mass control matters here

The mass row closing is what lets the whole `q/N` argument be made at all: `q` is
unaffected (its control closes to f32 roundoff), so the entire error lands on the
ratio and `defect Δ(q/N) = 1/(1+ε) − 1` with `ε = R_N/N_final`. If mass did not
close, the mean-mass bias could not be attributed to number.

Rows whose mass control fails carry **no magnitudes at all** — not a tidy set of
percentages with a warning — so an unusable row cannot be copied as a result.

## Limits

- **This is a per-call segment magnitude on one fixture, not a forecast bias.**
  It says what fraction of the column the sedimentation operator invents per
  call. It does not say what a 12-hour forecast's reflectivity or precipitation
  does, which needs the real case — the §14-8 gate.
- **It does not compound over calls here.** These are single-segment ratios; the
  ~20% figure for `ni` over 300 s in `FINDING_number_transport_creation_v1.md` is
  a different, cumulative statement and is unchanged.
- **Ice rows are excluded**, as everywhere: their mass control fails for the
  post-update cap.
- **`Δ(diameter)` assumes `D ∝ (q/N)^(1/3)`** — a mass-diameter relation with
  exponent 3. The scheme's own `m(D)` relation for each species is what a
  reflectivity calculation would need, and this is not that calculation.
