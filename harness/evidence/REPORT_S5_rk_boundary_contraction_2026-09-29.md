# S5: first selected RK state difference and one-object contraction test

**S5 remains OPEN.** The [second `calc_ww_cp` caller witness](REPORT_S5_call2_input_witness_2026-09-29.md)
established that selected `mu_2` and `u_2/v_2` words differed before that
routine ran. This follow-up brackets the preceding first RK stage in the
private `solve_em.F` path. It identifies the first difference among **ten
preselected state words** at eight executed boundaries; it does not find the
earliest difference over the whole domain or every operand of those calls.

The opt-in overlay is pinned to private `solve_em.F` SHA-256
`d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f`.
Removing its guarded blocks restores that source byte-for-byte. It records
`mu_2` at six selected horizontal locations and `u_2/v_2` at four selected
staggered locations around `small_step_prep`, `advance_uv`, `advance_mu_t`
and `small_step_finish`. A fixed parser accepts the declared 16 serial and
32 local 2×1 tile/stage files: **80 records per layout**. The 20 s mp237
control/capture runs use the retained 5 km input, one thread and local en0;
each layout has **254/254 raw-bit-equal saved variables** with logging OFF/ON.
The baseline probe-off histories also match the preceding unprobed trajectory;
the no-contract candidate has its own OFF/ON comparison, not a claim of
equality to that earlier executable.
`SMALL_AFTER` is immediately after `small_step_finish` and before the following
physical-boundary calls. Each file stores the final recorded `rk_step=1`
occurrence in this fixed-20 s run; it has no independent time/occurrence
ordinal and is not a multi-timestep event ledger.

| First RK boundary | Baseline different / 10 | `-ffp-contract=off` different / 10 |
| --- | ---: | ---: |
| Before `small_step_prep` | **0** | **0** |
| After `small_step_prep` | **5** | **2** |
| Before `advance_uv` | 4 | 1 |
| After `advance_uv` | 4 | 2 |
| Before `advance_mu_t` | 4 | 1 |
| After `advance_mu_t` | 10 | 3 |
| Before `small_step_finish` | 10 | 2 |
| After `small_step_finish` | 9 | 2 |

At the baseline `small_step_prep` exit, three **owned** sampled velocity words
already differ: `U2(117,j=2,k=1)` has `0xb9a4b2b8`/`0x39a4b2b8`,
`V2(117,j=3,k=1)` has `0x3c31112b`/`0xbc31112b`, and
`V2(234,j=1,k=1)` has `0x3be59d77`/`0xbbe59d77` (serial/2×1).
These sampled words agreed before the call. The other two exit differences
are rank-0 x2 reads at i=118, outside that tile's updated i range; they are
**halo observations**, not evidence that the rank-0 call wrote different
owned results. Selected owned `mu_2` words remain equal through
`advance_mu_t` entry and first differ at its exit. The call's other inputs
are not fully captured, so this does not independently identify the producer
of its arithmetic mismatch.

In RK1, `small_step_prep` copies `u_1=u_2` and `MUUS=MUU` over the same U
update range, and `v_1=v_2` and `MUVS=MUV` over the same V update range.
Its subsequent perturbation formulas therefore cancel to zero in exact
arithmetic on those updated cells. The nonzero stored baseline residuals
show that this mathematical identity is not bitwise realized by the current
compiled expression at the sampled points. They do **not** by themselves
identify a unique machine instruction or validate a replacement model.

For a controlled arithmetic check, `module_small_step_em.F` has SHA-256
`cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634`.
Compiling the same saved WRF-preprocessed `.f90` (SHA-256
`a6f4b9243e83e40dd356920d5d92b89fb72233541613eaab197ff3c45b4028d9`)
with the baseline options reproduces the existing object SHA-256
`923c7be0501a15da720b009035631be0c6493970f059f5039b1858cf5b5d558a`.
Appending only `-ffp-contract=off` gives object SHA-256
`6828d84841d7b2d15e8f8de69ebcd57466390bcbbb89590b6f16935de2331c4c`.
This one-object candidate makes the three sampled owned RK1 U/V exit words
**`0x00000000` in both layouts**. It strongly supports floating-point
contraction as a mechanism for the sampled baseline residuals, without
proving a unique instruction-level cause.

The complete 20 s host trajectory **still fails 1×1/2×1 raw-bit equality**:
28 of 254 saved variables differ in both builds. The selected U/V/W
different-word counts decrease from 122,708/105,672/202,079 in the baseline
to 29,687/23,946/81,442 in the one-object candidate. This is a layout
comparison, not a forecast-error or physical-accuracy metric. In the candidate,
the first remaining **owned sampled** difference appears after `advance_uv`
at `V2(117,j=3,k=1)`; a selected owned `mu_2` difference remains after
`advance_mu_t`. Halo differences are kept separate.
The compiler flag changes all routines in `module_small_step_em.o`, so the
history-count reduction cannot be assigned solely to `small_step_prep`.

The [compact stage and build evidence](data/S5_rk_stage_witness_2026-09-29.json)
contains the 80 raw words per layout for both builds, executable/input and
capture hashes, exact compile arguments, and saved-field comparisons.
Its SHA-256 is `4c507c470d1ccf8b96343470780dbd7dc18fae945d61560459a63730b99bf6a9`.
Full private host outputs and capture text remain local. No Tailscale was used.

**Next:** compare the actual `advance_uv` inputs at the first remaining
selected owned `V2` difference and the coupled `advance_mu_t` operands before
testing another change. Neither `-ffp-contract=off` nor an explicit RK1 zero
store is approved as a default host change by these selected witnesses.
