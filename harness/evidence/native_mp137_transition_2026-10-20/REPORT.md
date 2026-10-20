# Native MP137 forward boundary evidence, 2026-10-20

This campaign uses the existing native 5 km case, 234 × 282 columns, 39 mass
levels, fixed 20 s, one MPI rank and one thread. It advances the saved 120 s
checkpoint to 160 s. No observations were assimilated and no external model
input was acquired. Raw inputs, NetCDF outputs, complete build logs and trace
streams remain private under `host/research_evidence/mp137_native_transition_20261020/`.
The public JSON files contain bounded metrics, exact hashes and execution receipts.

## Results

- Three independent controls each match all 652 restart variables at 160 s:
  rebuild of the two boundary objects, trace-enabled compilation with tracing
  off, and trace runtime on versus off. See `comparisons.json`.
- Direct intermediate restart still fails: 120→140 s matches all 652 variables,
  but restarting 140→160 s differs in 1,385 of 322,426,586 numeric values across
  13 variables. A load-only dump at 140 s preserves all 652 variables; it executes
  zero integration steps and returns the known post-finalize code 14.
  Neither this failure nor its unproven boundary/halo lead is hidden by a tolerance.
- The final `NativeHostTransition` uses explicit origin-bound prefix replay,
  rather than direct intermediate restart. Both baseline and H-memory probe
  completed a `HostForwardWindow` with logical steps 120→140→160 s. The second
  call reintegrates the origin continuously for 40 s and checks the supplied
  140 s checkpoint before accepting 160 s. Baseline 140 and 160 s both match
  all 652 variables of the independent contiguous execution. See
  `native_forward_summary.json`; it pins the adapter source actually executed.
- Prefix comparison includes all variable/global attributes. Exactly two
  recorded integer-Boolean output-alarm ringing bits are normalized: stream 1
  (history) and 7 (auxhist6). The active host skips restoring output alarms with
  `override_restart_timers=true`; all other metadata remains strict.
- A single saved `H_DIABATIC` element is changed by binary32 approximately
  0.001 K/s at 120 s. At the actual next MP137 call, all four packed forcing
  inputs change at selected column (156,21): DEN on 24 levels, PII on 24,
  pressure on 24 and DELZ on 22. At call 8, the counts are 30/30/30/21.
  `trace_metrics.json` gives units-compatible absolute changes and trace hashes.
- Each two-step trace contains 78 level-step samples per kind, 312 records.
  Baseline, probe and independent contiguous traces each have zero mismatches
  against the exact sampled arm64/GFortran finish arithmetic replay and zero
  mismatches across the packed-state→finish boundary. The baseline trace also
  matches the independent contiguous trace exactly at this selected column.

## Arithmetic and build attribution

The experimental trace executable replaces two boundary objects and adds one
trace helper to the previous archive (377 members versus 376). Other objects,
including the fixed initializer objects, are reused. This is not a full clean
host source build. `boundary_*_BUILD.json` pins source/executable/library hashes;
complete exact build arguments stay in the hash-bound private receipts.
`loader_receipt.json` records the actual library mapped by the trace executable
in the zero-step load-only probe. Other calls pin that same candidate but do not
claim a separate loader attestation per execution.

KDM/wrapper `-ffp-contract=off` is preserved. The host finish object retains its
existing O2/FMA arithmetic. A source-order, non-fused binary32 replay differs by
one ULP in two sampled heating rates; it is not the emitted host calculation.
The diagnostic `native_finish_replay.py` instead uses exact rational FMAs with
binary32 nearest/even rounding, following the archived object disassembly
SHA-256 `74ace0eddba7a480e26d1bc9b0f2426561086b66f18448b0a6d66c400aab79d7`.
No numerical tolerance or operational arithmetic change was introduced.
The sampled ideal coordinate cross term reaches 1.6121332717763466e-8 K;
the sampled limiter contribution is zero. These are arithmetic diagnostics,
not mass/energy/number conservation or derivative evidence.

## Verification and limits

```sh
python3 -m pytest -q harness/tests
# 2329 passed, 59 skipped, 309 deselected, 153.83 s
python3 -m pytest -q oracle/tests/test_da_host_window.py
# 10 passed (included in the focused 64-test verification command)
```

The 309 `local` tests are excluded by the default harness selector; they include
private-host/bundle/toolchain work. Dependency/platform-dependent tests can also
skip. The separate native experiments above provide their own evidence; the
public unit tests do not substitute for them. Focused transition tests include
forged clocks/contexts, changed inputs, prefix mismatch, strict metadata,
incomplete trace rejection and process-group timeout cleanup.

The two review reproductions are fixed: numeric `Times` cannot satisfy expected
UTC time, and commented source fragments cannot report a patch success. Prior
native Times and the intended initializer patch bytes were rechecked separately.

This backend is **value-only**, origin-bound, fixed-input, and O(N²) across N
logical calls. It cannot accept an analysis increment at an intermediate time.
It therefore does not yet implement the requested tendency-balanced, updated-
initial-state assimilation loop. Native full-host JVP/VJP, forcing derivatives,
pressure-aware observation derivatives and optimization remain open. The seven
restart-entry history diagnostics remain a separate limitation, documented in
`docs/NATIVE_ENTRY_DIAGNOSTIC_CONSUMERS.md`. The old KO DA stays paused.

To regenerate the selected-column metrics from the private streams:

```sh
PYTHONPATH=. python3 harness/evidence/native_mp137_transition_2026-10-20/trace_report.py \
  --baseline BASELINE_PREFIX_40S_TRACE --probe H_PROBE_PREFIX_40S_TRACE \
  --reference INDEPENDENT_CONTIGUOUS_TRACE --output trace_metrics.json \
  --i 156 --j 21 --levels 39 --steps 7 8 --dt 20
```

The baseline and probe trace paths are in the final-step transition receipts.
The reference is `TRACE_ON_CONTIGUOUS/case/native_trace.hex`. This recipe is
specific to the attributed compiler profile, not portable arithmetic certification.
