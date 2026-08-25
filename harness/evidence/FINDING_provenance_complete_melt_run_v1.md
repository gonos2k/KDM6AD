# The first run with complete provenance, and what it says about the melt arms

A ten-minute `np = 1` forecast made 2026-08-26 with the hardened runner. It is
the first run in this campaign whose binary, runner and decomposition are all
recorded IN the run rather than in a transcript, and it settles three things the
last review left open — including one where my own measurement was wrong.

## The provenance, which is the point of making it

    wrf_exe_sha256   before = after = a40bd80fae334c4b...   stable yes
                     path /Users/yhlee/KDM6AD+/KIM-meso_v1.0/main/wrf.exe
    runner_sha256    runner = canonical                     state match
    proc_grid        requested (unset)   actual 1x1   np 1

Each of the three is a review item closed by measurement rather than argument:
the binary is hashed BEFORE and after and agrees; the runner in the case tree is
the repository's, checked rather than assumed; and the decomposition is what WRF
actually reported in `rsl.error.0000`, not what was asked for. `parse_proc_grid`
read a real RSL log for the first time here.

## The domain reproduces exactly, which validates the chain

    cells 2 573 532        qg > 0            30 607
                           0 < qg <= qcrmin   2 580
                           ... and T > T0       987   in 217 of 8 102
                                                      graupel-bearing columns
                                                      (2.68 %)

Every figure matches `FINDING_graupel_trigger_prevalence_v1` to the digit. That
finding's numbers came from a run with no recorded binary; this one reproduces
them under a hash that is written down.

## The land/sea claim, with the denominator it was missing

| | land | sea | ratio |
|---|---:|---:|---:|
| candidate **cells** | 248 | 739 | **2.98** |
| `qg > 0` cells | 9 848 | 20 759 | 2.11 |
| **P(candidate \| qg > 0)** | **2.5183 %** | **3.5599 %** | **1.41** |

"Three times more common at sea" was a COUNT ratio, and most of it is that
there is simply more graupel at sea. Per graupel-bearing cell the window is
**1.41 times** as likely at sea, not three. Both numbers are real; only the
second is a propensity, and it is the one the sentence claimed.

## The arms, on a real failing column

Column `(281, 16)`, land, one of the 57 candidate columns carrying no negative
prognostic (the fixture generator refuses those, correctly -- 160 of the 217
candidates carry a negative `ni` somewhere).

| nsplit | step | legacy | g1 | g3 | g4 |
|---:|---:|---:|---:|---:|---:|
| 12 | 5 s | **24** | 0 | 0 | 0 |
| 6 | 10 s | **24** | 0 | 0 | 0 |
| 3 | 20 s | **20** | 0 | 0 | 0 |
| 2 | 30 s | **24** | 0 | 0 | 0 |

Non-finite f32 words in the emitted stream. **All three arms remove every one,
at every step.**

And this column fails at 5 s, which the earlier sample did not: `(100,142)`
failed at 20 s and `(71,147)` only at 30 s. The threshold is not universal, so
"the operational 20 s step" is where the sample happened to break, not where the
defect begins.

## Where my measurement was wrong

The first pass reported **0 non-finite for legacy as well**, which would have
said the column does not fail. It counted the strings `nan` and `infinity` in a
stream that encodes every float as a HEX WORD -- `G33F STAGE 0 ... f32 00000000`
-- so a NaN appears as `7FC00000` and matches nothing. Decoding the words and
testing the values gives the table above.

That error would have been reported as "the arms make no difference", which is
the opposite of what the data says. It is recorded here because the same
instrument produced the earlier `(100,142)` reading in this session, which is
also re-measured above and is genuinely 0 -- the INITIAL state carries no
defect (`nr_levels: 0` in its own manifest), so that column could never have
shown one.

## g3 and g4 remain indistinguishable, and there may be a reason

0 differing numeric lines at every step. The partial-melt branch is not reached.

A likely reason, stated as a hypothesis with its basis rather than a result:
`pgmlt` is capped at `-qg`, and inside the window `qg <= qcrmin = 1e-9` -- at
the top candidate columns it is 1e-43 to 1e-40, which is f32 SUBNORMAL. A melt
rate at `T ~ 289 K` exceeds that by many orders, so the cap binds and the melt
is complete. If that holds generally, the partial branch is unreachable INSIDE
the window and g3 = g4 there always; outside the window `rhox > 0` and both
reduce to legacy. Measuring `pgmlt` against `qg` per cell would settle it.

## What this does not close

The perturbation member. §8 needs the perturbed run made under the same runner
with its own recorded digest; this is the baseline half.
