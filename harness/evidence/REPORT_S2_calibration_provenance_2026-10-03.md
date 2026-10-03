# S2 threshold calibration provenance follow-up

This is a source/history audit, not a new physics experiment or unit approval.
Operational values and acceptance gates are unchanged.

The active private `Registry.EM_COMMON` lines 2530–2531 declare land/sea
`ncmin_land=100`, `ncmin_sea=10`, with blank units. Its SHA-256 is
`6741720cba12ad7ee1c172339bd8def5973b22f4e88ab9cd152f3ba3df456e37`.
The accompanying `.var` declares QNCLOUD/QNRAIN/QNICE/QNCCN in number/kg
(lines 203–218; SHA-256
`f568831b7d83dfa251a59c1bf9716fea2c891277c831abdcfa2bb8541a69a5db`).
These declarations do not establish the threshold's units.

The active `module_mp_kdm6.F` has SHA-256
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`.
Its commented scalar `ncmin=1.e1` says “changed for th Autoconversion”; the
land/sea block around lines 875–881 is preceded by `Feb5_2025` and uses the
values directly in number gates/budgets. Neither supplies a calibration source.
August 2025 Registry snapshots already have 100/10 and blank units. Private
host trees are gitignored and have no independent Git history; the historical
archive differs from runnable source and is not treated as current authority.

Public commit `eedb6c2` adopted 100/10 as host-parity values; `f467967` later
made number/m³ an explicit opt-in interpretation. Neither recovers original
calibration. The upstream WRF WDM6 `ncmin=10` comment identifies a minimum
value without calibration units. A paper's initial CCN concentration is a
separate quantity and cannot justify a cloud-number threshold.

**Result:** the bounded provenance search is complete without recovering the
original units or empirical rationale. S2 remains OPEN. Retain the explicit
volume-number convention for the optional path; do not relabel it as original
physical calibration. Closure needs the originator's documented units and
calibration domain, or an explicitly approved new physical policy and evidence.

This audit does not acquire external atmospheric inputs, infer a threshold by
BT fitting, change the numbers, or relax the strict moment-pair gate.
