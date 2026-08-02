# The fallout diagnostic is 6.6× its own limit under legacy; under the conservative interface it IS the water budget

**Revised twice.** The first version read the 6.5× as surface precipitation. The
second corrected that to "the diagnostic, not the water leaving" but still summed
`rain + snow + graupel`, which double-counts. This version has the species
accounting right.

## The species convention

F:1462-1464, verbatim:

```
fallsum     = fall(1)+fall(2)+fall(3)+fall(4)   -> rain    == the TOTAL
fallsum_qsi = fall(2)+fall(4)                   -> snow    == a SUBSET
fallsum_qg  = fall(3)                           -> graupel == a SUBSET
```

`rain` is the total surface fallout of all four species; `snow` and `graupel` are
**components of it**. The total is `rain` alone.

## Result

Each column as a ratio to **its own** finest member, so no unit convention enters:

| dtcld (s) | diagnostic legacy | diagnostic cons | −ΔW legacy | −ΔW cons |
|---|---|---|---|---|
| 100 | **6.556** | **1.146** | **1.307** | **1.146** |
| 50 | 6.355 | 1.125 | 1.143 | 1.125 |
| 25 | 4.394 | 1.116 | 1.022 | 1.116 |
| 12.5 | 2.330 | 1.040 | 0.989 | 1.040 |
| 6.25 | 1.400 | 1.002 | 0.994 | 1.002 |
| 3.125 | 1.000 | 1.000 | 1.000 | 1.000 |

### 1. Under the conservative interface the diagnostic IS the water budget

Its two columns are **identical at every step** — 1.146, 1.125, 1.116, 1.040,
1.002, 1.000. That is not a coincidence of ratios: the absolute check gives

    total fallout / (−ΔW_col) = 1.0000 at every timestep

so for the conservative interface the reported precipitation and the water that
actually left the column are the same number.

### 2. Under legacy they are not

The diagnostic is **6.56× its own fine-step limit at dtcld = 100 s** — an
operationally normal step, below the kernel's 120 s target — while the column water
loss is only **1.31×**. The absolute ratio total/(−ΔW) runs 4.97, 4.26 … 0.992,
converging only near 3 s.

**This is the P0-4b defect measured as a function of resolution.** `docs/STATUS.md`
records it as "a non-constant O(1) amount"; it is a strong function of the timestep,
and the conservative interface removes it entirely.

## Where it comes from

Per column, diagnostic legacy/conservative at dtcld = 100 s: column 1 is
**bit-identical** (288–290 K, no ice — the interface never acts, the control);
columns 2 and 3 carry it.

An earlier version called column 2 "the clean case" because its final-state branch
topology is identical across all six members while column 3's `qg` presence flips.
**That support does not hold.** Column 2 starts with condensate and ends with every
condensate species at exactly zero — it rains itself out. Its final topology is
therefore stable *because it is empty*, and says nothing about which branches the
members took during the integration. The topology record is final-state only and
was already documented as one-sided; this is that limitation biting.

So no column of this fixture is certified as a clean convergence domain: column 3's
topology demonstrably moves, and column 2's cannot be checked by the available
record. The ratios above stand as measurements; the claim that column 2's are
*trustworthy in a way column 3's are not* does not.

## What this does NOT establish

- **Not "the conservative variant precipitates 6.6× less".** The column water loss
  differs by 1.307 against 1.146 at the coarsest step — about 14%, not a factor of
  six.
- **Not a claim that legacy is wrong.** The reference defines the reference. What is
  shown is that its fallout diagnostic departs from its own water budget by ~5× at a
  normal step, and that the conservative interface's does not depart at all.
- Synthetic fixture, 300 s, microphysics only. Real-case precipitation,
  reflectivity, LWP/IWP, brightness temperature and DA cost remain unmeasured.
