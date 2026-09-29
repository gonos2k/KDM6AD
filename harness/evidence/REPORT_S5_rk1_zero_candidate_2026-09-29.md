# S5: opt-in RK1 zero-store candidate

**S5 remains OPEN.** The [first-RK boundary trace](REPORT_S5_rk_boundary_contraction_2026-09-29.md)
found nonzero, layout-dependent `u_2/v_2` perturbations immediately after
`small_step_prep`. In RK1 the source copies `u_1=u_2`, `MUUS=MUU` and their V
counterparts over the same cells it then updates. The two perturbation
formulas therefore cancel to zero in exact arithmetic there. This experiment
tests an explicit zero store for **only those two RK1 updates** in an
isolated private-host build; the operational source and default build stay
unchanged.

The generator pins `module_small_step_em.F` SHA-256
`cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634`.
Its guarded overlay SHA-256 is
`54db8ea6b0ac66cc0b52e04ce66ca97bcf86df1dfe1c21e7896c91c34a0c185a`,
and removing the guards restores the original source byte-for-byte. With the
normal host `-O2 -ftree-vectorize -funroll-loops` options, the isolated
candidate object SHA-256 is
`4560f30d1eef108cc96eb269a93642a4ad0d63bc687a44c038bce7eb4a7f1baf`;
the linked executable SHA-256 is
`463c60cc5b3dd63523456f63813a49d69001167174aad5048574fba5fecffdb8`.
No whole-module `-ffp-contract=off` flag was used in this candidate.

The retained 5 km mp237 input ran for 20 s at fixed dt with one thread and
local en0 MPI in 1×1 and 2×1 layouts. Requested and actual grids agree;
each run completed with stable executable/input hashes. Logging OFF/ON
histories match **254/254 variables** within each layout. The existing
eight-stage RK probe accepts 16 serial and 32 2×1 files, 80 selected words
per layout. At the `small_step_prep` exit, the three sampled **owned** U/V
words are `0x00000000` in both layouts. Halo reads outside rank 0's updated
i range remain separate.

| 20 s 1×1 vs 2×1 comparison | Different saved variables / 254 | Different U words | Different V words | Different W words |
| --- | ---: | ---: | ---: | ---: |
| Previous baseline, no-vectorized `calc_ww_cp` object | **28** | 122,708 | 105,672 | 202,079 |
| RK1 two-store zero candidate | **28** | 122,539 | 105,470 | 202,034 |

The candidate fixes the sampled cancellation residual, but **does not fix
the MPI trajectory**. At the selected `advance_uv` exit,
`V2(i,j,k)=(117,3,1)` already differs again (`0x4438aa81`/`0x4438a862`),
and a selected owned `mu_2` word differs after `advance_mu_t`. The smaller
U/V/W word counts are layout-difference counts, not physical error or forecast
skill. Between the baseline and this intentionally changed candidate,
bitwise trajectory identity is not required or claimed.

The [compact evidence](data/S5_rk1_zero_candidate_2026-09-29.json) records
source/build/run hashes, the four completed run identities, same-executable
comparisons and the selected RK words. Its SHA-256 is
`583ce046ab132dc82754da168c085fdc0d9d6f80ee9795570e3219994520862f`.
Private raw histories/captures remain local. No Tailscale, external model
input, QC or tolerance change was used.

**Disposition:** retain this as a negative, bounded opt-in experiment; do not
add RK1 zero stores to the default host to claim S5 closure. Trace the actual
`advance_uv` operands and neighboring/halo inputs at the remaining selected
difference before deciding whether any narrower algorithm change is sound.
