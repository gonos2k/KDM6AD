# NCCN zero-only candidate: native FD passes, moment admission fails

Baseline: PR #351 `65d76a7`. This is the N5 follow-up for the isolated
zero-only fp64 NCCN return selected in N4. Production runtime remains unchanged.

## Result and remaining condition

Two local mp337 40 s runs, OFF/ON, used the same candidate library/executable,
selector 2 / dry-number 1, dt=20 s and ncmin_land=ncmin_sea=10. All 12 separate
39-level max-norm FD checks pass at h=1e-4; the worst is NCCN at 6.74342e-8
against 1e-5. Native JVP/VJP duality is 4.37220e-16 against 1e-12. OFF/ON
forecast files have identical SHA-256 and 254 raw-identical variables at
0/20/40 s. Energy has five variables at 0/20 s; zero-frame precipitation/ocean
files supply no numerical comparison. Both model runs complete on a 1x1 grid.

The **native-staged state fails the existing user command's strict moment
admission**, both on input and after the fp64 kernel. Therefore the numerical
pass is not supported-state acceptance; N5 remains OPEN/FAIL and N6 is deferred.
The public [replayer](../replay_nccn_native_fd.py) returns
`NUMERICAL_PASS_UNADMITTED_STATE` and exits 1. It does not relax the gate,
replace the sampled input, populate missing counts or adopt the return patch.

| Strict one-sided moment pairs | Input levels | Base output levels |
| --- | ---: | ---: |
| qc/nc | 31 | 5 |
| qr/nr | 17 | 8 |
| qi/ni | 32 | 0 |
| qg/bg | 0 | 4 |

The replayer checks all six input/output states (base and both endpoints);
plus/minus pair counts match the corresponding base counts shown above.
Input NC/NR/NI are zero alongside positive paired masses. Output qg/bg failures
are qg=0 with positive bg. These counts apply the current command's exact-zero
support rule; they do not declare every trace hydrometeor physically active or
prove a new production defect. An independent [retained-input audit](nccn_native_input_number_audit_2026-10-02.json)
finds QNCLOUD, QNRAIN and QNICE are all exactly zero across the original
1x39x282x234 input arrays. The inspected first-call wrapper initializes NN, then
copies NC/NR/NI; it does not fill those missing counts. The captured gap therefore
exists before the return-arithmetic candidate or FD overlay. This observation
does not define a replacement initialization policy. The first native
input/initialization and physical moment policy need resolution before this
state is accepted as a supported diagnostic example. Selected historical numerical parity and the
operator's input-domain admission are distinct questions.

## Evidence and independent reconstruction

The [lossless staged trace](nccn_native_fd_trace_2026-10-02.tsv.gz) contains
10 full 12x39 arrays: STATE_IN/PLUS/MINUS, OUT_BASE/PLUS/MINUS, V, JV, JTU and FD;
also four forcing profiles, XLAND, exact shapes/order, dt/h/ncmins, cell and
per-field summaries. Decimal ES26.17E3 values round-trip to binary64. The
uncompressed SHA-256 is `82f5173f022d9bc4bb708224ed799d18c4d779b99c696769c4a872254cd5ce59`.
Records come from an actual native execution, not generated with the replay's
own update equation.

The [native receipt](native_nccn_zero_fd_result_2026-10-02.json) identifies
source, objects, library, executable, inputs, controls and actual run folders.
Root independently verified those source/library/executable hashes, forecast
and energy files, variable counts and saved Times. The trace replay independently
reconstructs both staged endpoint inputs, every FD value and all 12 reported
error triples; it compares SUM(JV*JV) with SUM(V*JTU). Six focused public tests
cover the actual result plus missing/duplicate/nonfinite/changed records and
inconsistent success flags. They do not execute a new model forecast.

Root additionally called the same candidate C ABI with the exact serialized
native inputs, forcing and direction. Base forward, JVP, VJP, plus and minus
outputs match all five native arrays **bit-for-bit**. The [ABI replay receipt](nccn_native_staged_abi_replay_2026-10-02.json)
uses low-level `step`, not the validated `run_column` entry: the latter rejects
the moment pairs before execution. The two access paths must not be described
as equivalent admission results.

The native coordinate is global (200,152), XLAND=2. The earlier offline command
uses zero-based (3,272), frame 1, XLAND=1. They share candidate/configuration,
not atmospheric input or an identical direction array. The native mixed rule
is unchanged (entry qi plus 1% qv and nc); current entry nc is zero. This is one
state-to-state direction, not full Jacobian, arbitrary DA routing or a literal
adjoint of rounded f32 forecast arithmetic.

## Build and scope

The [FD overlay](../s8_nccn_zero_native_fd.patch) adds two value-only calls to
the previous corrected native AD probe and writes a bounded, unique trace.
It does not overwrite forecast states. The new binary links the isolated
zero-only library `08bf94881a8fbcded44c8b070f6f5350b281bf3b20da9f0cc2b99ffa6abb757b`.
Fresh ISO/wrapper objects were compiled with `-ffp-contract=off`; existing host
archives were retained. This is not a complete host rebuild or historical
source-pin approval. Both runs use local MPI rank 1, threads 1; active `en0` is
pinned for OOB and TCP. No Tailscale transport or multi-rank equivalence is claimed.

NCCN entry volume is below its 1e8 minimum at zero-based levels 9–38. Levels
4–8 have an interior entry and negative NCCN changes, but downstream clamps
still matter. Thus nonzero output changes and a passing state Jacobian cannot
certify a particular unconstrained CCN producer or its physical number basis.
The baseline/hybrid/zero-only return artifacts remain preserved. No threshold,
h, input or direction was tuned after seeing the result. No RTTOV or deployment
was performed; operational and observation approval remain false.

```sh
python3 harness/replay_nccn_native_fd.py  # expected exit 1: unadmitted moments
python3 -m pytest -q harness/tests/test_nccn_native_fd.py
```

The [existing checklist](CHECKLIST_pr349_followup_2026-10-01.md) records the
numerical measurement completed and the supported-state acceptance still open.
Next work is the measured input/initialization and moment-policy boundary,
not more return formulas, new phenomena or a general schema framework.
