# Actual native QC–NC boundary measurements

Base: main `a1c63630` / PR454. The full 234×282 native host is integrated from
the same original 00:00:40 restart to 00:01:00. Only telemetry is restricted to
three columns; neither the model domain nor its native physics batches are
reduced to those columns. No physics equation, moment floor, control vector,
observation mask or operational ABI default was changed.

## Executed campaign and noninterference

Eight independent 20 s host steps completed: two initial engineering control
runs, then corrected off/on pairs for control, historical alpha1 and alpha0.25.
There are **16 actual KDM wrapper entries, zero RTTOV calls and zero optimizer
calls**. The initial on stream included 18 extra top-storage values at K=40;
the strict reader rejected them. Its raw data and source are preserved in
`engineering_history/` and `execution_sources/`. The producer was fixed to use
the owning call's 39 native levels, and the corrected pairs were run again.
No rows were removed or assertions weakened to make the initial stream pass.

The corrected pairs and their historical endpoints are bit-identical across
**652 checkpoint variables / 322,426,586 numeric elements per comparison**:

| Pair | Applied T/Q points | Applied components | Endpoint SHA-256 prefix |
| --- | ---: | ---: | --- |
| Control | 0 | 0 | `225d2cabe8a4` |
| alpha1 | 561,407 | 855,443 | `ff3c101e3b35` |
| alpha0.25 | 117,172 | 170,749 | `77be4282ef36` |

Each off/on ACK is also byte-identical. All READY40 files have SHA-256
`0c4836a2…`; no 60 s result is relabeled or reused as a 40 s input. These are
independent reproductions, not eight consecutive forecast steps or a DA cycle.
See [noninterference](receipts/noninterference.json) and the
[actual execution ledger](receipts/execution_ledger.json).

Runtime readback in every run confirms MP137, `NO_MP_HEATING=0`,
`USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW=4/4, PBL11, CU37 and LSM2.
`MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0`, threshold approximately 1e-8 are retained.
The water-tendency correction switch does not disable physical water updates
or latent heating. One MPI rank and one thread are used.

The measured KDM calls have `(I,K,J)` dimensions `(232,39,141)` and
`(232,39,139)`: 32,712 + 32,248 = 64,960 interior columns. The remaining
1,028 outer-ring columns still participate in the full host/boundary evolution.
The second call owns none of the selected witnesses and is retained explicitly
in both trace streams. Observation B512/B452 chunks are unrelated to these tiles.

## What the selected states show

Coordinates are native one-based, mass levels counted from the ground. QC uses
kg/kg dry; **NC remains a legacy raw coordinate with uncertified physical units**.

| Witness and case | READY40 NC | MP_INPUT NC | FP64_OUTPUT NC | QC at final state |
| --- | ---: | ---: | ---: | ---: |
| `(155,25,19)`, control | 0 | 0 | 0 | 0 |
| `(155,25,19)`, alpha1 | 0 | 0 | 0 | 7.61499052e-7 |
| `(155,25,19)`, alpha0.25 | 0 | 0 | 0 | 0 |
| `(221,63,6)`, control | 13,605,366 | +3.44254065 | +3.44254065 | 6.38341007e-5 |
| `(221,63,6)`, alpha1 | 13,605,366 | +12.1508684 | +275,672.2769 | 6.10249626e-5 |
| `(221,63,6)`, alpha0.25 | 13,605,366 | **−3.81439924** | **0** | 6.38586134e-5 |
| `(91,94,4)`, control | 0 | +0.02228504 | +0.02228504 | 6.02195287e-5 |
| `(91,94,4)`, alpha1 | 0 | **−0.03163810** | **0** | 6.04965608e-5 |
| `(91,94,4)`, alpha0.25 | 0 | **−0.17183831** | **0** | 6.02189975e-5 |

- The first witness is already QC-positive/NC-zero at READY. The control and
  alpha0.25 KDM outputs remove QC; alpha1 retains positive QC with NC=0.
  This is not evidence of newly losing positive NC in the bridge.
- The second witness's alpha0.25 NC is negative **before KDM**, and its exact
  widened FP64 input remains negative. The KDM map returns NC=0 while QC stays
  positive. This is a newly observed invalid pair after an initially valid READY.
- The third witness is initially invalid. The control has positive NC by
  MP_INPUT; both candidates reach MP_INPUT with negative NC and return zero.
  The observation is an upstream change plus a KDM output boundary, not proof
  that an activation or advection process is responsible.

The f32→f64 input widening and f64→f32 writeback checks have **zero raw-bit
mismatches** across all three valid trace runs. Writeback, wrapper diagnostics,
zero-out and MOMENTS_PRE/POST retain the selected NC outputs. MOMENTS records
are actual `moist(P_QC)` / `scalar(P_QNC)`, not QC_RATE.

## Public replay

From the repository root, with NumPy installed:

```sh
python3 -m harness.evidence.native_qc_nc_trace_2026-10-26.replay
```

Alternatively use `PYTHONPATH=. python3 harness/evidence/native_qc_nc_trace_2026-10-26/replay.py`.
The module form provides the repository import root. The replay verifies
SHA-256/size pins, reads NPZ from those verified bytes, and parses temporary
copies of the verified traces without modifying the original files. It writes
JSON only to stdout. The output is byte-identical to [analysis.json](analysis.json)
with SHA-256 `681ef65d744e378c7cb0ea595aef53c4c05f939875f5d28374f1224ca2a5e639`.
Its zero `model_calls` field describes the arithmetic replay, separately from
the eight actual native runs in the execution ledger.

There are 6,318 raw trace values: 3 runs × 3 columns × 39 levels × QC/NC ×
9 stages. Each context NPZ contains only READY/final f32 QC/NC `[3,39]` arrays,
extracted from hash-pinned checkpoints by the recorded publication producer.
Full private checkpoints are not distributed in this packet.

## Limits and provenance

The READY40 source already contains an earlier unaccepted diagnostic T/Q history;
it is not a pristine forecast. The same nominal KO00:00 scene belongs to the
surrounding experiment, but no new observation evaluation occurs here.

These observations locate **READY→MP_INPUT** and **FP64 KDM output** boundaries.
They do not identify the upstream process, certify number units or conservation,
establish a derivative, compute candidate cost or accept a full-host analysis.
All three original full-host trials remain inadmissible; general representable
runner wiring, cumulative optimization and a second assimilation remain open.

Build receipts bind compiler commands, compiled source, objects, archives and
binaries. The build orchestration scripts were inventoried after the build;
their hashes were not captured inside those receipts at execution time. This
gap is explicitly described in [build producer provenance](receipts/build_producer_provenance.json).
The rejected stale generated solve source was replaced by authoritative `.F`
preprocessing; its uninstrumented instruction/relocation bodies match the old
object, with only source-path strings differing. Corrected native outputs were
then compared directly, rather than inferred from that build comparison.

Private-path prefixes in copied build receipts are redacted and original
unredacted receipt hashes are retained. Actual controller/publication source
snapshots are preserved without rewriting old H1 or PR454 manifests.
