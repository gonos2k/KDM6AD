# Legacy surface precipitation is 6.5× the converged value at an operational step; the conservative interface is not

The strongest meteorologically material result available from this fixture, and it
is on the quantity a forecast is scored on.

## Total surface precipitation after 300 s

Summed over species and columns, mm, against the kernel's internal step:

| dtcld (s) | legacy | conservative | legacy/cons | legacy/finest | cons/finest |
|---|---|---|---|---|---|
| 100 | 2.218e-01 | 3.514e-02 | 6.31 | **6.461** | 1.023 |
| 50 | 2.171e-01 | 3.660e-02 | 5.93 | **6.323** | 1.066 |
| 25 | 1.505e-01 | 3.740e-02 | 4.03 | **4.384** | 1.089 |
| 12.5 | 7.984e-02 | 3.534e-02 | 2.26 | 2.326 | 1.029 |
| 6.25 | 4.802e-02 | 3.431e-02 | 1.40 | 1.399 | 0.999 |
| 3.125 | 3.433e-02 | 3.435e-02 | 1.00 | 1.000 | 1.000 |

**Legacy over-predicts by 6.5× at dtcld = 100 s** — an operationally normal step,
below the kernel's own 120 s target — and converges down monotonically, reaching the
right answer only near 3 s. **The conservative interface is within 2–9% of the
converged value at every step tested**, including the coarsest.

The "converged value" is the finest member, and it is not an assumption: the two
legs agree there to **0.05%** (3.433e-02 against 3.435e-02). Two different
discretisations landing on the same number is what makes it the limit rather than
just the last point.

## Where it comes from, and why it is clean

Per column and species at the two ends of the chain:

| | dtcld = 100 s | dtcld = 3.125 s |
|---|---|---|
| col 1 rain | 1.000 | 1.000 |
| col 2 rain | **11.75** | 1.034 |
| col 2 snow | **19.86** | 1.039 |
| col 2 graupel | 0.626 | 1.003 |
| col 3 rain | 4.15 | 0.987 |
| col 3 snow | 4.50 | 0.986 |

(legacy / conservative)

- **Column 1 is bit-identical at every step.** 288–290 K, no ice, so the
  sedimentation interface never acts — the control.
- **Column 2 carries the largest effect**, up to **19.9× in snow**, and column 2 is
  the clean case: the branch-topology instability measured elsewhere in this
  evidence set is confined to column 3 (`qg` presence flipping with resolution).
  **Column 2's topology is stable across the whole chain**, so its numbers are a
  convergence result and not an artifact of the members integrating different
  physics.
- Column 3 shows the same direction at ~4×, with the standing topology caveat.

That column 2 is both the largest effect and the topologically stable one is what
makes this finding usable where §7 and §9 were blocked.

## What it means

At an operational timestep the two interfaces disagree about surface precipitation
by a factor of 6 overall and 20 in snow in a supercooled column, and the
disagreement is **not symmetric**: the conservative interface sits on the converged
answer at every resolution, while legacy needs a step ~30× finer to get there.

So on this fixture the conservative interface is not merely a conservation
bookkeeping change — it removes a large timestep sensitivity from the surface
precipitation of a supercooled column.

## What this does NOT establish

- **Synthetic fixture, 300 s, microphysics only.** No dynamics coupling, no cloud
  lifecycle. These are properties of `arithmetic_multisubcycle_v1`, not of a
  forecast.
- **Not a claim that legacy is wrong.** The reference defines the reference. What is
  shown is that its surface precipitation is far from its own fine-step limit at a
  normal step, and that the conservative interface is not.
- **No real-case measurement.** Precipitation, reflectivity, LWP/IWP, brightness
  temperature and DA cost on a real case remain unmeasured, and this result does not
  substitute for them.
- **Column 3's numbers carry the topology caveat** and should not be quoted without
  it. Column 2's do not.
