# The precipitation DIAGNOSTIC is 6.5× its own limit under legacy; the water leaving is not

**Revised after a self-check that changed the conclusion.** The first version of this
document reported the 6.5× as surface precipitation and called it the strongest
meteorologically material result available. It is not that. The 6.5× is in the
**fallout diagnostic**; the physical column water loss behaves quite differently, and
the distinction is exactly the P0-4b defect already recorded in `docs/STATUS.md`.

## Two quantities, and they are not the same quantity

`docs/STATUS.md` already records that the operator-implied column water loss and the
WRF `rain_increment` fallout diagnostic **disagree by a non-constant O(1) amount**,
100% attributed to the post-update-reservoir inflow cap. Measuring both against the
internal step makes that disagreement a function of resolution:

| dtcld (s) | −ΔW legacy | −ΔW cons | diagnostic legacy | diagnostic cons |
|---|---|---|---|---|
| 100 | **1.307** | **1.146** | **6.461** | **1.023** |
| 50 | 1.143 | 1.125 | 6.323 | 1.066 |
| 25 | 1.022 | 1.116 | 4.384 | 1.089 |
| 12.5 | 0.989 | 1.040 | 2.326 | 1.029 |
| 6.25 | 0.994 | 1.002 | 1.399 | 0.999 |
| 3.125 | 1.000 | 1.000 | 1.000 | 1.000 |

each column as a ratio to **its own** finest member, so the comparison is internal to
one quantity and carries no unit convention.

## What is actually established

1. **The fallout diagnostic under legacy is 6.5× its own fine-step limit at
   dtcld = 100 s** — an operationally normal step, below the kernel's 120 s target —
   and converges down only near 3 s. **Under the conservative interface it is within
   2–9% at every step tested.**
2. **The underlying column water loss is far less sensitive in both**: 1.31 for
   legacy and 1.15 for conservative at the coarsest step, converging by ~12 s.
3. So the conservative interface's effect here is concentrated in **the diagnostic**,
   not in how much water leaves the column. Since the diagnostic is what a forecast
   reports as precipitation, that is still consequential — but it is a different
   claim from "the two variants precipitate differently", which the column water
   loss does not support at anything like that size.

## An offset I have not explained

At every step and in **both** legs the diagnostic is about **2× the column water
loss** (e.g. at 3.125 s: legacy 3.433e-02 against 1.740e-02, conservative 3.435e-02
against 1.726e-02). That factor is suspiciously stable and is present in the leg
whose diagnostic is otherwise well behaved, so it is more likely a convention
difference in this comparison — vertical index or per-column normalisation — than a
second defect. **It is not diagnosed, and no closure claim is made from it.** The
ratios in the table above are unaffected, since each is internal to one quantity.

## Where it comes from

Per column at dtcld = 100 s, diagnostic legacy/conservative:

| | ratio |
|---|---|
| col 1 rain | 1.000 |
| col 2 rain | **11.75** |
| col 2 snow | **19.86** |
| col 3 rain | 4.15 |
| col 3 snow | 4.50 |

- **Column 1 is bit-identical at every step** — 288–290 K, no ice, the interface
  never acts. The control.
- **Column 2 carries the largest effect** and is the clean case: the branch-topology
  instability measured elsewhere is confined to column 3 (`qg` presence flipping
  with resolution), and **column 2's topology is stable across the whole chain**.
- Column 3 shows the same direction with the standing topology caveat.

## What this does NOT establish

- **Not "the conservative variant precipitates 6.5× less".** That was the first
  version's error. The column water loss differs by ~15% at the coarsest step, not
  by a factor of six.
- **Not a claim that legacy is wrong.** The reference defines the reference. What is
  shown is that its fallout diagnostic is far from its own fine-step limit at a
  normal step, and that the conservative interface's is not.
- Synthetic fixture, 300 s, microphysics only. Real-case precipitation,
  reflectivity, LWP/IWP, brightness temperature and DA cost remain unmeasured.
- The ~2× diagnostic-to-ΔW offset above is unexplained.
