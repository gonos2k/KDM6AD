# S5: selected `calc_ww_cp` call-bound counterfactual

**S5 remains OPEN.** This local experiment identifies a cause of the selected
1×1/2×1 `ww` difference, but it does not change or recertify the full host.

The runner `harness/s5_calcww_bounds.py` checks the SHA-256 of the current
private `module_big_step_utilities_em.F`
(`27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c`),
extracts only the unchanged `calc_ww_cp` subroutine, and reads the checked-in
exact2 S5 caller-word projection (SHA-256
`64488506cfb144a2383107ba250660deb2868b9d8fb7f0f7c7131528842ed1d7`).
The selected serial and 2×1 input words must agree before replay. Captured
columns i=116–118 and 233–235 and j=0–283 supply the target cells' full local
stencil; unrelated columns are initialized filler. The Fortran driver holds
the arrays, memory bounds, j tiles, compiler flags and executable fixed, and
changes only `its:ite` between the archived serial and 2×1 call bounds.
The fixed memory bounds are `i=-4:240`, `j=-4:288` in every arm; the actual
2×1 host ranks use smaller, different i memory extents. Changing `its:ite`
also changes this routine's local automatic-array shapes. Thus the isolated
factor is the complete call-bound/local-extent package with host memory
extent deliberately held fixed.

With `/opt/homebrew/bin/gfortran -O2 -ftree-vectorize -funroll-loops`, all
**45,120 selected output words** (two columns × two layouts × 40 levels × 282
j positions) match the archived stage-2 `ww` projection bit-for-bit. The
same-input, same-executable bounds-only difference is:

| Target i | Different words out of 11,280 | Serial versus 2×1 bounds |
| ---: | ---: | --- |
| 117 | 9,890 | `1:235` versus `1:117` |
| 234 | 9,970 | `1:235` versus `118:235` |

Two separate one-option builds further isolate the compiled arithmetic:

| Option appended to baseline | i=117 bound differences | i=234 bound differences | Relation to archived outputs |
| --- | ---: | ---: | --- |
| `-fno-tree-vectorize` | 0 | 0 | Both bounds reproduce the archived 2×1 words exactly |
| `-ffp-contract=off` | 0 | 0 | Both bounds agree with each other but differ from both archived layouts |

The retained [result JSON](data/S5_calcww_bounds_result_2026-09-29.json) SHA-256 is
`29f534e092f4925413a5cf20ac3e7441eaf55ab8f0964a6cfbf0b929df7813a3`.
It was produced with `SDKROOT` set to the local Xcode macOS SDK and:

```sh
python3 harness/s5_calcww_bounds.py \
  --source /Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/dyn_em/module_big_step_utilities_em.F \
  --out /private/tmp/kdm6ad_s5_bounds_replay_run2
```

The baseline compiler reports vectorized loops in this routine. Thus, for
these selected cells, **call extent interacting with compiled arithmetic is
sufficient to reproduce the archived MPI-layout difference**. The selected
input/halo equality from the earlier exact2 trace is consistent with this
counterfactual. This does not prove which instruction causes each last-bit
change, that every domain difference has this cause, or that either variant
has a more accurate physical solution.

This is an extracted routine compiled separately, not the original WRF object
or a complete local MPI host run. The old exact2 shadow worktree was removed
in workspace cleanup; the checked-in selected projection and its hashes remain.
The next S5 action is one isolated **one-object** host build with
`-fno-tree-vectorize` applied only to `module_big_step_utilities_em.o`, using
the WRF preprocessing path, followed by 20 s local 1×1/2×1 runs. Require
same-executable instrumentation noninterference, actual processor-grid
records, and full saved-field comparison before changing any host default.
No Tailscale, new external input, physics default, tolerance or QC was used.
