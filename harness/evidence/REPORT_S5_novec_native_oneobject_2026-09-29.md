# S5: local one-object no-vectorization host counterfactual

**S5 remains OPEN.** The selected `calc_ww_cp` difference identified by the
[isolated bounds replay](REPORT_S5_calcww_bound_counterfactual_2026-09-29.md)
can be removed at its first measured call, but a 20 s mp237 full-host 1×1/2×1
comparison still fails.

An isolated host copy used the retained 5 km input (`input_canonical_sha256`
`12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf`),
the same non-grid namelist SHA-256
`0ea0f4d94860c6f2cb23c737bb0caab97f2cc7368a73d2aa15e323abc8c363d1`,
20 s fixed time step, mp237, one thread, and local en0 networking. Both
layouts report the requested and actual grids. Tailscale was not used.
The 0 s frames match 254/254 variables across layouts in each build, and each
run records a stable before/after executable hash.

The pinned private `module_big_step_utilities_em.F` has SHA-256
`27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c`.
The final controlled pair compiled **the same saved WRF-preprocessed `.f90`**
(SHA-256 `d8c11bd9b3dd0fd717c14899c53ffe7ca37c4d768128c4dac750429f7fb4bf3a`)
with the current compiler and identical options except for an appended
`-fno-tree-vectorize` on that one object. Other archive members and host input
were kept fixed. The rebuilt baseline object SHA-256 is
`ea8fc1e1d3b8c70c9f12af7b20dc3023fc85c401cbdd746d71c13b8b5f4f1276`;
the no-vectorization object is
`6efea1779d745371128bdb80d769d97b2f1a18a5f2fd014c062e522d6b4e5a6f`.
The resulting executable SHA-256 values are `14468d0f95b3e26cff81d345ff3631302ca834367bb89ea712f9e22b6ae1a477`
and `a809332081cd33a51518a4bb662436d9e295b944b09084a801e78c85847e2ea4`.
The rebuilt baseline reproduces the prior selected host executable's 254 saved
variables bit-for-bit in each layout, despite a different object/binary hash.
The [compile receipt](data/S5_novec_build_receipt_2026-09-29.json) records both
executed command arrays, exit codes and repeated object hashes from the same
`.f90`; its SHA-256 is
`953e2db5e40893d903ccaacb159d55e3b6aaf70d8d5123cce09499c2e3cd7dd1`.

| 20 s comparison | Common saved variables | Different variables | Different `W` words / 2,639,520 |
| --- | ---: | ---: | ---: |
| Rebuilt baseline 1×1 vs 2×1 | 254 | 28 | 203,301 |
| One-object no-vectorization 1×1 vs 2×1 | 254 | **28** | 202,079 |

An opt-in `calc_ww_cp` overlay was also compiled into an isolated
no-vectorization executable. In each layout its logging-OFF, logging-ON and
unprobed no-vectorization trajectories agree across **254/254 saved variables**.
The existing fail-closed parser accepts all declared six serial and twelve
2×1 tile/call files. At **call 1**, i=117 and i=234 each have zero serial–2×1
differences in `MUU`, `MUV`, `DIVV`, `DMDT`, and all 11,280 selected `WW` words.
At **call 2**, differences recur: i=117 has 2 `MUU`, 1 `MUV`, 10,603 `DIVV`
and 10,588 `WW` differing words; i=234 has equal selected `MUU/MUV` but 9,538
`DIVV` and 10,476 `WW` differences. These are selected probe fields, not a
full-domain first-divergence claim.

The compact [result JSON](data/S5_novec_native_oneobject_2026-09-29.json)
records run/executable/input hashes, all comparison counts, the complete
selected call table and per-file capture hashes; its SHA-256 is
`0e4884cc1dd9ea9d4e1f2a03e2df714da9f725c011edf5d96b167df9f2811e0b`.
Raw private host outputs and capture text remain local. A first attempt with
en8 stopped before model start because that interface was no longer available;
only completed en0 runs enter the comparison.

The preliminary shadow build regenerated a `.f90` with different whitespace
and diagnostic line numbering; it was **not** used for the strict one-factor
claim. The final pair instead used identical saved `.f90` bytes. The probed
overlay has a different compiled source, so its interpretation is bounded by
the demonstrated logging-OFF/ON and unprobed-output equality.

**Next:** trace the input producers read by the second `calc_ww_cp` call,
including `mup/mub` at i=117 and the `u/v` flux operands at i=234. The
one-object no-vectorization option is not a whole-host S5 fix and should not
be applied to the default build on this evidence. No operational physics,
number-unit policy, QC or tolerance was changed.
