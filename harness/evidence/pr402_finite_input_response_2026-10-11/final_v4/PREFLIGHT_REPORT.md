# PR402 finite-input response preflight

This packet is phase-1 only. It prepared four isolated input cases from the saved PR398 center and made **zero wrapper/RTTOV calls**. It did not run a new baseline, model, M, optimizer, preprocessing, or acquisition.

Frozen plan ID: `finiteplan402final4`. The root/Red preflight gate must approve the exact `K_RESPONSE_PLAN.json` SHA-256 before the separate one-shot execute stage. That stage is limited to four wrapper launches, one per trial, with no automatic retry.

| Trial | Only changed input | Actual delta | Unchanged inputs | Wrapper planned | Saved K/radiance copied? |
|---|---|---:|---:|---:|:---:|
| skin_minus_0p5K | `profiles/001/sfc/01/skin.txt` | `-0.5` | 21 | 1 | No |
| skin_plus_0p5K | `profiles/001/sfc/01/skin.txt` | `0.5` | 21 | 1 | No |
| o3_source_minus_1pct | `profiles/001/atm/o3.txt` | `[-0.09784089999999956, -0.00030117840000000104]` | 21 | 1 | No |
| o3_source_plus_1pct | `profiles/001/atm/o3.txt` | `[0.00030117840000000104, 0.09784089999999956]` | 21 | 1 | No |

Skin values are serialized with the source's six-decimal scalar format. O3 trials perturb the saved 69-level fixture reference by ±1%, map the signed source beta through the hash-bound PR401 66×69 matrix P, and serialize the resulting active 66-layer O3 with `.17E`. `INPUT_DIFFS.csv` and the per-trial inventories show that only the declared input file changed; pressure, T/Q, O3/CO2 except for the designated O3 trials, surface, geometry, channels, namelist and launch files remain bound.

Each case's `out/` contains only the unchanged `run.sh`, `env.sh`, `rttov_test.txt` and empty `k/`/`direct/` output directories. The production runner target is `<trial>/out/run.sh`; the saved center `out/k` results were not copied. The resolved executable, coefficient, hydrotable and linked library paths/hashes are frozen in `K_RESPONSE_PLAN.json`; preflight rechecks them and confirms the original center outputs are unchanged.

This does not authorize or record an execution. The future execution stage requires the exact plan hash and a unique execution ID, takes an exclusive lock, creates a one-shot guard before the first call, stops after any wrapper failure, and preserves a failure record without retry. A quality failure retains all seven rows and withholds any accepted cost/result; it never fabricates a value or silently drops a channel.
The predeclared unit directions are d=+1 K for skin with h=0.5, and d=+1% of the saved 69-level reference O3 mapped through P with h=1. The executor will report raw B±−B0 separately, E±=[B±−B0]∓h(K0d), D_FD=(B+−B−)/(2h), ideal K0d, and K applied to the actually serialized input deltas. Relative errors use max(|D_FD|,|K0d|) as the denominator; they are null when that value is below 1e−6 K per unit d, while the signed absolute error remains reportable.
