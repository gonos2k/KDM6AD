# Independent Red audit: PR404 raw source masks

Date: 2026-10-11
Audited head: `4b65577f7c2062ab99dffe50ced233a092457184` (`codex/pr404-l1b-source-mask`)
Scope: `read_packed_source_patch`, `source_patch_canvas`, the actual netCDF inputs, source-mask tests, `repair_source_mask.py`, and its private additive NPZ plus axis contract. No acquisition, full-scene BT decode, native run, H/K/M call, or optimizer was performed. Frozen PR403/v2 payload and receipt were not edited.

## Result

No source-mask algorithm defect found in the scoped path. The raw read returns a copied `uint16` array with automatic masking and scaling disabled. A second read disables scaling and enables netCDF4 masking, then restores raw-word mode in a `finally` block. The canvas maps the clipped source slice into a 5×5 canvas while storing source missingness and padding independently. Packed DQF is decoded from raw words as its own field.

The focused test file passed under the specified research Python environment with `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and `OMP_THREAD_LIMIT=1`: **9 passed**. It exercises default fill, scalar and vector `missing_value`, raw preservation with `scale_factor`/`add_offset`, validity-range exclusion, zero DN, source missingness independent of DQF, production reader quality, edge padding, and rejection of non-`uint16` data. As an extra check, actual netCDF4 fixtures with `valid_min`, `valid_max`, and combined range attributes agreed with netCDF4 mask behavior.

I independently read the bounded 5×5 windows from all 18 existing files named in the repair receipt. Every file matched its recorded SHA-256 and had a `(500, 500)` `uint16` `image_pixel_values` variable. None declared `_FillValue`, `missing_value`, scale/offset, or validity-range attributes. These windows contained zero source-masked cells. The private additive NPZ exists and matches SHA-256 `5257baba8553247519b74abe088aa24fe6f5829b270f999c59861926e993cad6`; arrays have the expected two dates, `(5, 5, 9)` shape, and `uint16`, `bool`, `bool`, and `uint8` dtypes. Both saved masks are all false for these interior windows. This confirms preservation and separation, while the actual windows do not exercise a true source-missing cell or edge padding; synthetic actual-netCDF4 tests cover those cases.

## Axis-contract review: prior P3 resolved

The previous report noted that the NPZ did not self-describe channel-axis ordering or window position. The additive `SIDECAR_AXIS_CONTRACT.json` now resolves that omission without rewriting the frozen payload or repair receipt. Its `payload_sha256` matches the private NPZ, its canonical private copy is byte-identical to the public evidence copy and mode `0600`, and its metadata matches the audited repair source:

- Prefixes: `20250720`, `20250721`; array axes `(patch_row, patch_column, channel)`; shape `(5, 5, 9)`.
- Channel indices 0–8: `wv063` (AMI ID 8, 12 valid DN bits), `wv069` (9, 13), `wv073` (10, 13), `ir087` (11, 13), `ir096` (12, 13), `ir105` (13, 13), `ir112` (14, 13), `ir123` (15, 13), `ir133` (16, 13). These valid-bit values agree with the original source-file headers.
- Raster rows 318–322 and columns 46–50; source center `(320,48)` maps to canvas `(2,2)`.
- Raw words are packed `uint16` with scaling disabled; DQF bits 14–15 remain separate from the valid DN bits. The source mask follows netCDF4 fill/missing/validity masking and excludes edge padding; padding marks only canvas cells outside the original raster.

P3 status: **resolved for the additive sidecar artifact**. The contract binds to the existing NPZ hash and names array suffixes. No claim is made that this metadata validates downstream scientific use.

## Evidence and limits

- Graph query run before audit: `graphify query "How do heldout_l1b_v2 read_packed_source_patch and source_patch_canvas preserve source masks, netCDF metadata, and pad validity through repair_source_mask?" --budget 1200`. It identified source reader/canvas and oracle AMI reader nodes; implementation claims were checked against source.
- Focused test command: `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 PYTHONPATH=oracle /private/tmp/KDM6AD-research-rc-20261007/env/bin/python -m pytest -q harness/evidence/pr404_l1b_source_mask_2026-10-11/test_source_mask.py` → 9 passed.
- Actual file reads were restricted to the repair's existing five-by-five slices. No external data or truths were used.
- This audit does not validate the unexecuted v2 acquisition/full-decode path, native model linkage, RTTOV, physical interpretation, or any future consumer of the sidecar.
