# Host-column TH16 f32 activation transition (2026-11-12)

This packet follows the exact 624-word input published in the [host-column packet](../native_host_column_f32_2026-11-11/README.md). The input came from the selected native `(203,149)` column of the second `mp_physics=137` f32 C ABI tile at the 2025-07-19 00:00:00→00:00:20 host step. Every probe below is a **separate B=1, value-only `kdm6_step_c` call** in which only initial potential temperature TH16 is changed. It is not an instrumented perturbed WRF tile or an f32 AD experiment.

## Coupled search and observed transition

The earlier TH search stopped when the activation rate changed from equal to its NCCN cap to below it. In the selected stage, `NC=0`, `NCCN=100,000,000`, and `dt=20 s`; a fraction below one can therefore lower both the raw rate and the activated fraction. This run explicitly allows the two recorded comparison groups (`pow` versus one, raw rate versus cap) to change together, while requiring the other four recorded Boolean masks to remain at their baseline values. It independently checks the saved operands and f32 rounding at every probe; this acceptance rule does not assert that the two minima have the same derivative rule.

The [compressed sweep](raw/sweep.json.gz) retains the original private JSON bytes after decompression and contains **23 distinct TH16 input words**. Separate searches for `sw_percent >= 0.48` and saved `activated_fraction >= 1` both ended at the same adjacent positive-f32 input words:

| Native TH16 input | Lower `43a00285` | Upper `43a00286` |
| --- | ---: | ---: |
| Potential temperature | 320.0196838378906 K | 320.01971435546875 K |
| `sw_percent` | 0.4800319672% | 0.4797935486% |
| Captured pre-minimum pow | 1.0000399351 | 0.9997419119 |
| Selected fraction | 1 | 0.9997419119 |
| Raw rate / NCCN cap | 5,000,000 / 5,000,000 | 4,998,709.5 / 5,000,000 |
| Final NC16 | 100,000,000 | 99,974,192 |

The represented input gap is **3.0517578125e-5 K**. Final NC16 changes by **-25,808**, or **3,226 f32 output ULP**. Across the two complete 510-word output arrays, six state words change; precipitation increments and RHOG words do not. Both endpoints have strict pow comparisons, so neither is an observed pow tie. The rate/cap operands are tied only on the lower side; that value tie does not identify the operator's tie derivative.

The pair is a **local discrete f32 transition** for this B=1 input. It does not establish global uniqueness, a continuous root, continuity, a derivative at the boundary, or a JVP/VJP. No QV search was performed on this host-call input. The earlier #578 f32 boundary used a different 00:00:40 input, and its location is not transferred here.

## Executed evidence and public replay

The [manifest](manifest.json) pins the full 23-event sweep, six terminal call records (installed DSO plus capture DSO off/on at each endpoint), two compressed endpoint scalar captures, the executed private sweep script snapshot and its run receipt. Every event retains the 33 target-layer activation fields and all **468 state + 3 precipitation + 39 RHOG output words**. Terminal records retain the full **624 input words and 510 outputs** per call. Public replay checks the single-word TH16 perturbation against the parent input, call controls, all output words, source-order f32 relations, comparison masks, the four fixed non-target masks, both adjacent predicates and endpoint capture rows. The independent Python pow comparison allows up to four f32 ULP; recorded C++ operands and their minimum handoff are checked as raw words.

The private runner used the same executable and installed/capture DSO hashes as the earlier [f32 boundary packet](../native_f32_activation_boundary_2026-11-11/README.md), whose build receipt pins the source and compiler flags. At the baseline and two terminal words, installed, capture-off and capture-on outputs matched in all 510 words. The first coupled-search attempt reached the bracket but failed while formatting a diagnostic gap; the final executed script corrected that helper and reran all probes. Both attempts and the correction are identified in the run receipt. These hashes and archived records are provenance **claims** in public CI: absent private binaries and loader logs cannot be independently authenticated there. Optional private endpoint replay, when supplied the exact binaries and input, provides a separate local execution check.

The observed `cloud_complete_evap` mask enters the checked downstream NC/NCCN arithmetic; its upstream generation is not reconstructed here. The output equality at B=1 endpoints does not establish the original full tile's internal substep schedule. Physical mass/number/volume budgets, operating f32 AD, f64 host DA, native observation-profile pressure interfaces and GK2A–RTTOV cost sensitivity remain separate. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_host_column_f32_boundary_2026-11-12 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`. The private endpoint check skips when the pinned private runner, input and DSOs are unavailable.
