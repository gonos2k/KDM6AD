# Four defects that a green suite did not see

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-PROTOCOL-003` | **active** | confirmed | The G33P/G33N protocol contract, the matched-closure denominators, the enthalpy ledger basis, and the evidence-chain check. The plain G33R stream still does not carry the density arm and is NOT changed here: doing so would invalidate 72 archived member files, the pinned non-invasiveness baseline and the four-case comparator's decision inputs, which is an owner decision. The gap is closed by construction instead -- the producer refuses a non-default rho-profile on a path that would not record it. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner review of `main@7e2d8f8`. Each of these passed every test, and the reason
each passed is more useful than the fix.

## P0-1 — the driver emitted a schema its own parser refused

`SCHEMA` moved to 4 in `g33_probe_read.py`; the Fortran literal stayed at 3. So
every `--probe` and `--f64` run produced a stream that `pr.read()` rejected, and
the entire probe/f64 bundle path was unproducible.

**Why nothing failed.** The parser's tests build **synthetic** streams at the
parser's own version, so they can never disagree with it. The only tests that run
the real driver are local-only. A protocol version written independently in the
Fortran literal, the Python constant and the test default has three places to
drift and no check that they agree.

Two checks now, deliberately at different levels:

- a **static** one comparing the driver's literal to `pr.SCHEMA` and `nt.SCHEMA`,
  which runs in public CI where the Fortran build cannot;
- `test_g33_probe_pipeline.py`, which builds the real `--probe` and `--f64`
  drivers and feeds their actual output to `pr.read()` — the end-to-end check
  whose absence let this through.

## P0-2 — the magnitude denominators were not what they were called

`closures()` accumulates `x0` and `x1` across calls, so `start` and `final` are
`Σᵢ Nᵢ^pre` and `Σᵢ Nᵢ^post` — an inventory counted once per call. They were
published as "of the initial column" and "of the final column".

Measured per call, this fixture turns out to have **one active call of twelve**:
the remaining microphysics empties the column between call 1's post-sed and call
2's pre-sed, so calls 2–12 are identically zero. Therefore

- `Σᵢ Nᵢ^pre = N(t₀)` **here**, and 0.2173 / 0.4379 / 0.6884% is unchanged — but
  it was right by coincidence, and `active_calls 1/12` now reports the
  coincidence instead of hiding it;
- the window's **final inventory is `0.000e+00`** — the column ends empty — so
  "0.2200 / 0.4507 / 0.7256% of the final column" divides by zero. That figure is
  **withdrawn**; what was published under the name was `R / N₁^post`.

The size figures are relabelled **frozen-trajectory** and segment-local: they
hold `q` at what this run produced and exclude the feedback of a corrected number
on fall speed, the size distribution, and therefore `q` on every later sub-step.
`G33-MAGNITUDE-001` is withdrawn; `G33-MAGNITUDE-002` carries the corrected form.

## P0-3 — the "physical" enthalpy ledger was a mixed measure

`_ledger` weighted its endpoints by ρ_d under `basis="physical"`, while
`_water_out` was fixed at ρ_m. So the physical enthalpy residual differenced a
**dry** column change against a **moist** outflow.

That mixture *manufactured a signal*: the previously reported "at most 3%" basis
sensitivity was 2.6–2.8% on column 2, and it was the dry/moist mismatch. With the
basis threaded through the outflow too:

| ledger | col 1 | col 2 | col 3 |
|---|---|---|---|
| consistent thermodynamics | 3.3e−11 | 1.5e−12 | 1.3e−12 |
| the code's own equations | 3.4e−12 | 7.8e−13 | 3.2e−13 |

Basis-invariant to 1e−11 or better. The absolute terms still move by the
column-mean `q_v` (−0.0999 / +0.1019 / +0.1039%), so the conversion is applied —
it is the *relative* residual that is invariant.

## P0-4 — a bundle could lose every file and still certify

`--check` failed on `MISMATCH` and not on `absent`, so once a claim's manifest was
present and matched, its raw streams and analyses could all be **deleted** and the
evidence chain still exited 0.

The two absences are now distinguished, because they mean opposite things:

| state | verdict |
|---|---|
| the pinned manifest itself is absent | `unavailable` — bundles live outside the repo |
| the manifest is present and matches, a file it declares is missing | **FAIL** — incomplete or corrupt bundle |

## What was NOT done, and why

**The plain G33R stream still does not carry the density arm.** Closing that by
changing the G33R header would invalidate **72 archived member files**, the
pinned non-invasiveness baseline, `G33-TURNOVER-002`'s artifact pins, and the
four-case comparator's decision inputs — G33R is the *decision* protocol, and its
parser rejects unknown records. That is an owner decision, not a producer's.

So the gap is closed **by construction** instead: `produce()` refuses
`--rho-profile` other than `as-is` unless the run carries a protocol that records
it (`--nflux`, or a probe/f64 arm). An unidentifiable density bundle cannot be
published, which is the property that mattered.

Separately, `_argv` hardcoded a tile width of `3`; it now reads the column count
from the fixture, so a profile arm on any other fixture no longer fails the
driver's tile-sum check.
