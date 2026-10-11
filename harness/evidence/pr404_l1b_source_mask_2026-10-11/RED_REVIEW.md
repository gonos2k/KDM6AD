# PR404 GK2A L1B source-mask repair Red review

## Result

The additive repair is safe and remains separate from the executed PR403 packet. The original PR403 plan, helper, result, source files, CSVs and fixed-point NPZ retain their recorded hashes. PR404 reads only the already downloaded 18 source files and the original 5×5 raw-word patch; it does not alter the source files or payload, download new data, run a full-scene decode, or call a model/RTTOV/H/K/M/optimizer path.

I checked the repair source, v2 helper, result receipt, synthetic NetCDF tests and sidecar bytes. The repair helper SHA-256 is 6d041297692ea0a82344f57dbcc46095d89e6a1e47bfcf7baab1f74e272f9713; the future writer SHA is 30a9f166757570f3b77f18582bfbcdfee2b8f7ac7b3fa3e692e0203fb144ded5; the source-mask NPZ SHA is 5257baba8553247519b74abe088aa24fe6f5829b270f999c59861926e993cad6. The original PR403 payload still hashes to d24bb3a5d029ec13d1b25d0afdae95637a971d6d304f38bcc73dae461220bd90, and the result binds the original plan SHA.

I independently matched all 18 source SHA-256 values in the repair receipt against the original download progress receipt. The repair sidecar raw words and embedded DQF are byte-value equal to the original sidecar arrays for both dates. In these exact L1B files, there are no _FillValue, missing_value, or valid-range source-mask attributes, no reader mask cells, no source-missing cells, and no padding cells at the interior 5×5 point. All original 5×5 DQF codes remain zero. This explains why the repair changes provenance representation, not the observed values or quality results.

## Counterexample coverage

The new netCDF4 tests cover the original failure mode where set_auto_maskandscale(False) yields raw words without NetCDF's mask; default fill plus explicit scalar/array missing_value; scale/offset metadata while preserving packed uint16; missingness independent of packed DQF (including missing with DQF 0, error DQF 3 without missing, and valid raw DN 0); edge padding independent of source missingness; and rejection of signed-int16/float inputs rather than coercion. The implementation obtains the packed raw word with mask/scale disabled, separately asks netCDF4 for a mask with scale disabled, and stores source mask and padding in distinct arrays. Packed DQF remains a separate bit decode.

The source-mask scope is now explicit in the helper documentation and coordinator report: it includes NetCDF fill, missing_value and validity-range masking, distinct from packed DQF and canvas padding. The new valid_range counterexample confirms that behavior; I reran that focused real-netCDF test and it passed. The actual PR403 files have none of these mask attributes and no source-missing cells, so the additive sidecar values are unchanged.

The “no new plan, acquisition or model execution” claim is supported by the repair script's scope: it reads only fixed slices from 18 files already bound to the original receipt, requires the original plan/payload hashes, and writes a new private sidecar under a separate PR404 root. It has no download or full-scene execution call. The v2 helper is a future writer and must require its own new frozen plan before any future download/decode; the old PR403 plan is not bound to its changed helper hash.

No production source was edited and no additional tests or model/radiation runs were needed for this review.
