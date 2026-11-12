# Selected native column: bounded capture preflight

This packet prepares the **next** isolated f64 B=1 capture for the same native `(203,149)` column, 39 levels and 20 seconds. It is `SPEC_ONLY`: constructing and checking the plan executes **no KDM, WRF or RTTOV call**. The new instrumented DSO has not been built or identified, `execution_receipt` is null, and `execution_preflight()` rejects execution. A future run must cite a committed plan revision and its SHA before treating the directions and thresholds as predeclared; the JSON file alone cannot prove its registration time.

## Fixed input and call inventory

`plan.py` checks SHA-pinned #580/#586 inputs and current public source bytes, then exactly widens the 624 f32 input words. It changes only native level 16 as follows:

These live source pins are a **freshness check for this planned build**, not an immutable-source archive. A later source edit invalidates this preflight and requires a new plan and build attribution; it does not rewrite the meaning of previously executed evidence.

| Input family | Centers and steps | Distinct endpoint inputs |
| --- | --- | ---: |
| NC positive | baseline, lower, upper; `h=10⁻⁴,10⁻⁵,10⁻⁶`; `+h,+2h` | 18 |
| PII central | lower, upper; same three steps; `−h,+h` | 12 |
| TH and QV central | all three centers; `h=10⁻⁵`; `−h,+h` | 12 |
| Centers | baseline, lower, upper | 3 |

There are **45 distinct 624-word inputs**. Each matches a #586 **declared input** record, including the unexecuted upper PII `10⁻⁶` pair. Matching an archived input does not establish an archived output. The plan lists 90 new capture off/on value calls, three center graph calls and seven optional installed-value comparisons. The complete list is capped at **100 calls and 900 seconds**; optional calls must be reported as executed or skipped rather than silently assumed. The planned DSO hash remains null, so none of these calls is reported as having happened.

`field_inventory.json` starts from the #586 51-stage, 505 stage/field, 19,656-row inventory. Seven groups identify the additional value, live tangent and mask records needed for NC=0, PII, the rate–cap tie, applied sedimentation, named processes, same-call water, and heat/BG. Existing field labels and source locations are starting points, not a complete causal graph. Future instrumentation must preserve AD tensor connectivity; value-only snapshots cannot certify live operand derivatives.

## Prospective numerical gate

`fd_gate.py` implements the proposed [output-wise FD gate](../../../docs/NATIVE_HOST_OUTPUT_FD_GATE_V1_20261112.md) for **future** endpoint data. Normal operation binds a requested center, direction, output index and steps to the SHA-pinned canonical `plan.json.gz`; synthetic tests use an explicit test-only mode. Each step checks all 624 input words, the actual componentwise represented direction, 468-word forward parity supplied by the caller, finite outputs, captured-mask and schedule inventories, the 16-output-ULP resolution floor and relative FD–JVP residual. The overall result distinguishes branch crossing, direction degeneration, numeric mismatch, unresolved or rounding-limited signals, and a locally consistent numeric pattern. One stable step is insufficient for a final local consistency tag.

The gate compares **caller-supplied** execution arrays and receipts. Until future independent asset hashes and executed-path provenance are checked, its result remains `UNVERIFIED_EXECUTION_RECEIPTS` and `NOT_ELIGIBLE` even when synthetic numbers satisfy the local formula. It does not assign a new pass to #586/#587 saved rows and does not prove hidden-branch stability, installed joint AD, physical budgets or RTTOV cost derivatives. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

## Replay

From this directory, run:

```sh
python3 -m unittest discover -s . -p 'test_*.py'
PYTHONOPTIMIZE=1 python3 -O -m unittest discover -s . -p 'test_*.py'
```

The tests verify plan hashes, exact input inventory and budget, the missing-DSO execution block, field requirements, and the prospective gate's synthetic branch/rounding/mutation cases. They do not rebuild a private binary or execute the 45 planned inputs.
