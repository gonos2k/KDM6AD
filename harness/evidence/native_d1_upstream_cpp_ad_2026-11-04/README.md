# Same-call entry work2 and ProgB producers through actual C++ D1 AD

This packet extends the [conditional C++ D1→postmelt ProgB graph](../native_d1_progb_cpp_ad_2026-11-04/README.md)
on the same 5 km native column `(203,149)`, level 16, 20 s mp137 call
(`runtime_call=one_step_call=2`, `b_zero=27945`). The prior graph held
`work2`, `precg2`, and persistent D1-entry `rhox` fixed. Here the actual
C++ `compute_work2_venfac(p,T,DEN)` and **the same entry ProgB call's**
`precg2`, `rhox`, and BRS reclamp feed the D1 melt graph. A separate
postmelt ProgB call receives D1's updated QG/BRS. Snow/graupel slopes,
intercepts, dry-density forcing, other state, and the substep schedule
remain fixed.

```bash
python harness/evidence/native_d1_upstream_cpp_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_d1_upstream_cpp_ad_2026-11-04 -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_d1_upstream_cpp_ad_2026-11-04 -v
```

## Native source and same-call inputs

An isolated DSO adds value-only selected-column captures immediately
before and after the **entry** `preamble`. It records the pre-reclamp
QG/BRS, QV/T/P/DEN/DEND and the actual `work2`, `precg2`, `rhox`,
reclamped BRS, `cpm`, `xl`, `avtg/bvtg`, and active gate at all 39 levels.
The **9,516-row** capture preserves all **8,892** parent rows in order,
dtype, and raw word; 16 new fields × 39 levels add 624 rows. Stripping
the two capture blocks restores the prior `coordinator.cpp` byte for byte.
The same copied host executable and input checkpoint were used. Capture
off/on full endpoint SHA-256 both equal the parent variant's
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`.

The public verifier first replays the native packet. Independent Python
thermo/ProgB functions reproduce `work2`, `cpm`, `xl`, `precg2`, BRS,
`avtg`, and `bvtg` in raw f64 bits at **39/39 levels**. Entry `rhox` is
replayed where its gate is active: native levels 15–23. Inactive merged
`rhox` values can retain earlier ProgB history, which this packet does
not reconstruct. The inactive `precg2`/other coefficient words match the
fresh oracle outputs here, but that numerical equality alone does not
certify the earlier persistent-PR history. Every captured upstream value is joined in raw bits to
the value actually consumed at D1. The selected entry BRS before and
after reclamp happens to be bit-identical; the stages are kept separate.

| Native 16 entry value | Captured f64 value |
| --- | ---: |
| Pre-reclamp QG / BRS | `5.4038067779247255e−5` / `6.004757288472314e−8` |
| `work2` | `200.29441022254784` |
| Entry `precg2` | `24.35783384950257` |
| Entry `rhox` | `899.9209324078313` |
| Post-D1/postmelt `rhox` | `899.9209324078314` |

The fresh entry ProgB branch is active at this cell, so it replaces
the persistent prior diagnostic. The C++ program recomputes `precg2`
and `rhox` **together** from that same entry QG/BRS pair. It does not
recompute one while holding the other independently fixed.

## Direct C++ stage graph and derivatives

The archived [C++ program](cpp/main.cpp) links the **exact `libkdm6.a`
archive** recorded for this native DSO. It calls the actual C++
`compute_work2_venfac` and entry `progb_param_torch`, passes their
outputs to `melting_torch` and `apply_melt_freeze_inline`, then calls
postmelt `progb_param_torch`. The C++ JVP uses the same double-reverse
identity as `Handle::jvp`; the VJP uses `torch::autograd::grad`. Baseline
outputs **16/16 match native f64 raw bits**, including both new producers,
the earlier D1 state stores, and the postmelt outputs.

| D1-entry direction | Entry `work2` JVP | Entry `precg2` JVP | Postmelt `rhox` JVP |
| --- | ---: | ---: | ---: |
| Relative QV16 | `0` | `0` | cancellation-scale `+1.3877787807814457e−17` |
| Absolute T16, 1 K | `−0.5376620814389188` | `0` | cancellation-scale `+2.842170943040401e−14` |
| Relative QG16 | `0` | `+5.684666630498753` | `+899.9209324078313` |
| Relative pre-reclamp BRS16 | `0` | `−5.684666630498753` | `−899.9209324078315` |
| Relative P16 | `+66.76479673103562` | `0` | cancellation-scale `+1.4210854715202004e−14` |

The pressure direction exposes the work2 path: source-derived
`δwork2 = 0.3333333 × work2` for a unit relative P seed. For a 1 K
T seed, the independent derivative of the recorded work2 formula is
`−0.5376620814389188`. Entry `rhox` responds with `±rhox` to the
relative QG/BRS directions in the selected interior branch. The
entry `precg2` response is independently compared with the Python
ProgB oracle and finite differences.

Connecting these producers changes downstream conditional tangents.
For example, the T→D1 NR JVP is now `+386.8132657262213` instead of
`+388.06856471664145` with work2 fixed. A relative P seed, previously
absent from the fixed-input map, gives D1 NR `+155.8781711140534`.
These are numerical state-coordinate sensitivities at the selected
branch, not a physical particle-number budget.

All five directions compare actual C++ JVP with the separate Python
producer-chain JVP, C++ VJP weighted contractions, and central differences
using represented input gaps. Both C++ finite-difference endpoints are
independently evaluated by Python producer and source-order D1/ProgB
functions; **all 16 endpoint words agree in raw f64 bits**. Each local
endpoint retains the warm D1 melt/cap gates and both entry/postmelt
active interior `800–900` ProgB segments. The largest C++–Python JVP
absolute difference is `1.1368683772161603e−13`; the largest FD–JVP
residual normalized by `max(1,|JVP|)` is `1.8718900719759824e−5`.
Near-zero postmelt density/table responses in QV/T/P directions are
treated as cancellation/roundoff scale, not resolved physics signals.
The QV-to-postmelt-density comparison uses a `2e−17` absolute
cancellation allowance; T/P use `0.25` baseline output ULP for `rhox`,
`0.1` ULP for `avtg`, and `0.01` ULP for `bvtg`. A test output that adds
`1e−13` to the QV density JVP, recomputes
both weighted dots, and supplies a new SHA-256 is rejected by the full
replay. This keeps the near-zero validation threshold tied to the
observed numerical resolution rather than treating any small response
as a measured physical effect.
The pressure-direction postmelt `rhox`/`avtg`/`bvtg` values can be set
to zero within those bounds; a rehashed test records that their tiny
signs are not uniquely resolved.

The QG relative `h=1e−4` is **not** a local-JVP acceptance step:
its positive endpoint selects `rhox=900` in both entry and postmelt
ProgB calls, while the negative endpoint remains interior. The
conditional entry threshold is `8.786059899409143e−5`. Both crossing
endpoints are separately replayed in all 16 raw output words.

## Provenance and limits

The [native receipt](raw/native_build_receipt.json) links source/object,
DSO, runner, input and off/on execution hashes. The
[C++ receipt](raw/cpp_build_receipt.json) binds the same native static
archive to the isolated C++ object/executable, Torch 2.13.0 libraries,
captured input and [archived C++ output](raw/cpp_result.json).
`-ffp-contract=off` and assertions enabled in the test executable are
recorded. Private executable, archive, DSO and full checkpoint bytes
remain local; public CI replays the pinned evidence but does not rebuild
them. Stored C++ weighted JVP/VJP dots are each checked against an
`math.fsum` contraction of the validated JVP under a fixed-packet
roundoff-scaled gate. This is not a componentwise VJP oracle.
The JVP-dot gate uses a 16-term summation rounding argument. Using the
same numerical threshold on the archived VJP dot is a fixed-packet
consistency check, not a general bound on rounding through the whole
reverse-mode graph.
The inherited per-run record lists four selected C++ translation-unit
objects; the full native build receipt separately records `progb.cpp.o`
and the linked archive/DSO hashes. The public packet does not independently
recompile the private object bytes.

This is a conditional f64 **entry-preamble-to-postmelt stage** graph,
not the full subcycle, operational f32 map, perturbed host trajectory,
or the end-of-step C ABI JVP/VJP. The retained ProgB bundle matters in
inactive cells; this selected active cell uses fresh entry outputs.
Snow/graupel slopes and intercepts, density and dry-density forcing,
QI/NI, other state and the substep schedule remain frozen. QNICE's
historical physical unit and GK2A–RTTOV/whole-host sensitivity remain
unresolved. `scientific_status: INCONCLUSIVE` and
`physical_unit_status: INCONCLUSIVE`.

The C++ stage graph recomputes `cpm` from its QV input. In the selected
first microphysics substep, the outer entry QV and D1 QV agree and the
captured overwritten `pre.cpm` matches that recomputation in raw bits.
The QV direction is still a D1-entry stage direction: a full outer-step
QV derivative would need the explicit `entry_cpm` handoff and upstream
state/forcing path.
