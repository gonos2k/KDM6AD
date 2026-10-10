# PR399 adjacent-pair count audit

The V2 output recorded `adjacent_pair_count=891`. That value triple-counted the time dimension: `27` already means 9 columns × 3 saved times. There are 12 lower levels and 11 valid below-neighbor pairs per column/time, so the correct count is **297**. The V2 profile CSV has 324 total rows and 297 rows with `dT_vs_below_K` populated. The temperature-inversion flag count 51 and positive `dtheta_v/dz` count 216 were counted from those 297 valid pairs and remain correct.

The V2 source, raw result JSON, profile CSV, report, canonical derived NPZ, and their unsuffixed convenience aliases remain untouched. Treat the V2 report's adjacent-pair denominator as a historical reporting error and cite `VERTICAL_COUNT_AUDIT.json` for the correction. Future source `vertical_structure_v3.py` counts valid profile rows directly; it was linted/compiled but **not executed** against data.

No forecast was read, no arrays were re-extracted, and no model/M/H/optimizer ran for this audit. Hashes and file paths are in the JSON receipt.
