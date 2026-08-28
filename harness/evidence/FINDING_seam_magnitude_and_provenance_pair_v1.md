# The seam's size, measured, and the provenance pair that closes §8

Two experiments made 2026-08-26 under the hardened runner, so every member
records its own binary, runner and decomposition.

## §8 -- the perturbation premise is now recorded, not inferred

The earlier closure argued from a re-made BASELINE: the current binary
reproduces the 08-22 baseline bit-for-bit. That shows `F_B'(X0) = F_B(X0)` and
says nothing about which binary produced the 08-24 PERTURBED trajectory, because
two binaries can agree on one trajectory and diverge on a perturbed one.

Both halves have now been made together:

| | baseline | perturbed |
|---|---|---|
| `wrf_exe_sha256` | `a40bd80f…` before = after | **identical** |
| `runner_sha256` | `bab922f4…` state match | **identical** |
| `proc_grid` | actual 1x1 | **identical** |
| `namelist.input` | — | **identical** |
| exit | 0 | 0 |

The perturbation is the same one: `nextafter` toward `+inf` on `THM` over
`i = 109..125`, verified **186 966 cells, ULP distance min 1 max 1**, every cell
moved. `wrfinput_d01` was restored from a hash-verified copy afterwards and the
restore checked (`5a9ae8da…` in, `5a9ae8da…` out).

The comparison reproduces `FINDING_mpi_growth_is_not_distinguishable_v1`:
**104 differing fields at minute 1, 106 at minute 10**, against that finding's
104 and 106.

**Graded: the perturbation comparison's premise is now a recorded fact.**

## §6.2 -- field COUNT is not divergence SIZE, and the measurement says both

Three fresh one-minute members, `np = 1`, `np = 4` as `2x2`, and `np = 4` as
`4x1`. `proc_grid` confirms the requested grid was the grid used -- the first
time that check has answered in the affirmative:

    requested 2x2   actual 2x2   matches yes
    requested 4x1   actual 4x1   matches yes

| | 2x2 | 4x1 | ratio |
|---|---:|---:|---:|
| differing fields | **77** | **77** | 1.00 |
| differing cells | 7 497 949 | 7 701 473 | 1.03 |
| relative L2, **median** over differing fields | 7.40e-05 | 8.76e-05 | **1.18** |
| relative L2, **max** | **3.61e-01** | 2.45e-02 | **0.068** |

Relative L2 is `||x - baseline||_2 / RMS(baseline)` per field, so fields with
different units are comparable.

**So both readings are right about different halves.** The COUNT is identical
and the TYPICAL field diverges by the same order -- a median ratio of 1.18. The
TAIL does not: `2x2`'s worst field is **15 times** `4x1`'s.

And the tail is not scattered. It is the number fields:

| field | support 2x2 | support 4x1 | rel L2 2x2 | rel L2 4x1 |
|---|---:|---:|---:|---:|
| `QNCLOUD` | 115 567 | 62 374 | **3.61e-01** | 8.86e-03 |
| `QNCCN` | 717 570 | 405 487 | 8.11e-02 | 6.65e-03 |
| `QNRAIN` | 74 226 | 43 098 | 5.14e-02 | 1.75e-02 |
| `QICE` | 26 492 | 33 413 | 4.89e-02 | 9.08e-05 |

**And the denominators are large, so the ratio is not an artefact.** Checked,
because a relative norm inflates without limit when the field it normalises by
is near zero:

| field | RMS(baseline) | RMS(diff) 2x2 | RMS(diff) 4x1 |
|---|---:|---:|---:|
| `QNCLOUD` | 4.7757e+08 | **1.7243e+08** | 4.2295e+06 |
| `QNCCN` | 1.3978e+09 | 1.1331e+08 | 9.2919e+06 |
| `T` | 7.1635e+01 | 9.5014e-04 | 7.2352e-04 |

`QNCLOUD`'s baseline RMS is `4.8e+08` -- not small -- and the `2x2` difference
is `1.7e+08` of it. **At one minute, the `2x2` decomposition changes the cloud
droplet number by 36 % in RMS against `np = 1`**, while `4x1` changes it by
0.9 %, a factor of 41 in absolute terms as well as relative.

That is not a rounding-scale seed amplified by the flow. `T` and `QVAPOR`, in
the same runs, differ by 1e-05 relative -- which IS rounding scale. The number
fields are three to four orders above them.

`QNCCN` and `QNCLOUD` are exactly where this campaign already has a
decomposition-dependent defect on record
(`FINDING_ccn_overwrites_microphysics_v1`). The seam-direction sensitivity
concentrates in the fields that were already known not to be
decomposition-invariant, which is a connection the field count could not show.

**Graded: field-count equality MEASURED. Median magnitude equality MEASURED.
Direction-independence of the SIZE -- REFUTED in the tail, and the tail is the
CCN/number family.**

## Paired, per field -- which changes the numbers again

A ratio of medians is not the median of ratios, and nothing had checked that the
two grids differ in the SAME fields (owner review 8). Both matter here.

**The field sets are not identical.** 76 fields differ under both grids; `SNOWH`
differs only under `2x2` and `TML` only under `4x1`. "77 = 77" is 76 + 1 + 1.

Per COMMON field, with `r_f = log10(E_4x1 / E_2x2)` and
`E = RMS(x - baseline) / RMS(baseline)`:

| | value |
|---|---:|
| median `r_f` | **+0.038** (ratio 1.09) |
| median \|`r_f`\| | 0.177 (a typical field differs by ~1.5x) |
| p90 \|`r_f`\| | **1.017** (a tenth differ by 10x or more) |
| max \|`r_f`\| | **3.074** (`SNOW`, a factor of 1185) |

The ratio of medians over the same set is 0.852. The paired median is 1.09.
**They are different statistics and the earlier section reported the first one
as if it answered the second.**

## And by field family, which is where the structure is

| family | n | median `r_f` | max \|`r_f`\| | worst |
|---|---:|---:|---:|---|
| dynamics / thermo | 8 | +0.050 | **0.154** | `MU` |
| number-moment | 4 | **-1.017** | 1.610 | `QNCLOUD` |
| water-mass | 9 | -0.580 | 2.731 | `QICE` |
| surface / accumulation | 11 | +0.130 | **3.074** | `SNOW` |
| radiation / diagnostic | 14 | +0.154 | 3.074 | `ACSNOM` |

**Every dynamical field agrees between the two grids to within 0.154 decades --
a factor of 1.43.** That is the "same order" result, now measured field by field
instead of through a ratio of medians.

**The number-moment family is systematically an order larger under `2x2`** --
median `r_f` of `-1.017` across all four, not one outlier.

**And the extreme is not `QNCLOUD`.** The earlier section called the tail "15x"
by comparing the largest relative-L2 VALUES; per-field ratios put `SNOW` and
`ACSNOM` at `-3.074` (1185x) and `QICE` at `-2.731` (539x), with `QNCLOUD` at
`-1.610` (41x). `SNOW` and `ACSNOM` carry the same absolute RMS to three digits
and are the same accumulated quantity, so they are one signal, not two.

So the tail was understated by roughly eighty-fold, in the direction of making
the two grids look more alike than they are.

## A method note, because the first pass would have said something else

Summing `L1` and `L2` across all differing fields gave `2x2` a total L1 **162
times** `4x1`'s. That number is real and it means almost nothing: the sum is
dominated by whichever field carries the largest units, so it measures unit
choice rather than divergence. The per-field relative norms above are what the
comparison needs, and they say something considerably more specific.
