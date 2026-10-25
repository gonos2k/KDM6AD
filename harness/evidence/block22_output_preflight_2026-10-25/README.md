# Block22 saved-analysis output preflight

The prior analyzer/test were preserved from `857e9e48e4476da9a0b682a2ec71479bb2e48f3e` (SHA-256 `985ad6508154215d0941288f3e5822760d527eb44582b098814823fd4c73bd65` / `29c32c7fdfcd7d485357986e39ac666530ef0d7140a30d59d31ae5e5d3d4b9d4`).

The current CLI preflights both destinations before `analyze()`: existing or symlinked paths and equal/nested JSON/plot paths are rejected. Exclusive JSON creation and plot-directory creation remain as race guards.

The [validation receipt](validation.json) records occupied-directory rejection before analysis, unchanged existing plot contents, no JSON artifact left, and a successful fresh run. Numerical fields are unchanged; the PNG is byte-identical; focused tests pass 12/12; model calls are zero.

This is not a transaction across a later arbitrary plotting failure. Historical PR449 data and manifests remain unchanged.
