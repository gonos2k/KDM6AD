# S5: actual second-call inputs to `calc_ww_cp`

**S5 remains OPEN.** The [one-object local MPI experiment](REPORT_S5_novec_native_oneobject_2026-09-29.md)
made the selected first `calc_ww_cp` call agree across 1×1 and 2×1, but the
20 s host histories still differed in 28/254 variables. This follow-up reads
the actual inputs at the selected second call to identify which producer
values have already diverged before `calc_ww_cp` executes.

The existing source-pinned, opt-in `calc_ww_cp` overlay now writes a separate
small input file for four fixed witness points: i=117/j=119 and
i=118/j=193 (`MUU`), i=117/j=158 (`MUV`), and i=234/j=1/k=1 (`DIVV`). Its original output-capture
format remains unchanged. A parser derives the required file and record sets
from the declared 1×1/2×1 tile schedule; it accepted six serial and twelve
2×1 input files with **120 records per layout**. The overlay strips back to
the pinned private source SHA-256
`27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c`.
The isolated instrumented executable SHA-256 is
`26494c17bb40438ea7665fec4bdeae301346cc100f59f696dbf565c4ab7d2741`.

Both layouts completed mp237 for 20 s with the same retained 5 km input,
one thread and local en0 networking. Logging OFF/ON within each layout
matched **254/254 saved variables raw-bit-wise**. The prior selected-output
parser also accepted its original six/twelve files, with 140,448 output
words per layout. The logging-OFF histories also match the unprobed
no-vectorization executable 254/254 in each layout. No Tailscale or new model
input was used.

| Selected input group | Call 1 | Call 2 | Call 3 |
| --- | ---: | ---: | ---: |
| i=117, 26 words | 0 different | **8 different** | 8 different |
| i=234, 14 words | 0 different | **1 different** | 1 different |

At call 2, the i=117 witness differs in `mu_2` at `(i,j)=(117,119),
(117,157), (117,158), (117,193), (118,193)`, in `u_2` at
`(i,j,k)=(117,2,1), (118,2,1)`, and in `v_2`
at `(i,j,k)=(117,3,1)`.
The `mub` and captured map/grid factors agree. Replaying the Fortran f32
source order from those `mu_2/mub` words exactly reproduces the measured
`MUU(117,119)` bits **`0x47b9ea68`/`0x47b9ea69`** and
`MUU(118,193)` bits **`0x47ae23e3`/`0x47ae23e4`**, and
`MUV(117,158)` bits **`0x47b755c4`/`0x47b755c3`** (serial/2×1).
These are all three differing `MUU/MUV` words in the selected i=117 output
capture at this call; they do not cover other columns or processes.

At i=234/j=1/k=1, the captured direct `DIVV` inputs and precomputed
`MUU/MUV` agree except for `v_2` at `(i,j,k)=(234,1,1)`, whose serial/2×1 bits are
**`0xc00f309d`/`0xc00f309e`**. The resulting `DIVV` words are
`0xbca270c7`/`0xbca270d1`. Thus the selected call-2 discrepancy has an
upstream **state-input difference**, not merely the call-1 `calc_ww_cp`
vectorization effect. This does not prove where the earlier `mu_2` or `v_2`
differences were first produced across the whole domain.

The [compact raw-word evidence](data/S5_call2_input_witness_2026-09-29.json)
contains all 120 selected input words from each layout, output witness bits,
source-order replays and local capture-file SHA-256 values. Its SHA-256 is
`8c496a6fa102612812d4a62332e502a4fa3d423c7b09f146505c7439840d6eb1`.
The complete private capture text and history remain local.

The next causal check is at the actual RK producers: `small_step_finish`
updates `mu_2`, while `advance_uv` and subsequent small-step/boundary updates
can alter `u_2/v_2` before the next `rk_step_prep` call. These are source-path
candidates, not identified causes. Capture their selected source-order inputs
and stores across both layouts, then isolate the first different applied
operation. No default build, physics, QC, tolerance or
number-unit policy was changed here.
