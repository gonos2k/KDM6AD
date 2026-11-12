# Saved output-wise analysis of the selected host column

This packet reuses the #586 [screening archive](../native_host_batch3_shared_2026-11-12/README.md), the #584 f32/f64 output comparison, and a SHA-pinned copy of the declared numerical field scales. It executes **no KDM, WRF or RTTOV call**.

Run `python3 -m unittest discover -s . -p 'test_*.py'` here; repeat with `PYTHONOPTIMIZE=1 python3 -O` to check the optimized mode. `analysis.py` verifies parent digests and recomputes the deterministic `results.json.gz`. The test compares every saved raw/discrete field and floating diagnostic by f64 bit pattern. The packet is not a substitute for the parent archive's own 52-suite replay.

## Stored calculations

- **61 × 468 = 28,548 output rows:** each has the selected field and native level, both endpoint f64 words, saved JVP word, represented-component input direction, FD, absolute and field-scaled residual, relative-to-JVP diagnostic when defined, output ULP separation, and a captured-branch category.
- **9 × 468 = 4,212 second-forward NC rows:** center, `+h`, and `+2h` outputs are kept separately for three centers and three steps. Each `+2h` endpoint's own complete-capture, output-parity, Boolean-mask and schedule receipt is checked before branch classification. The comparison JVP is the saved first-forward JVP scaled by the ratio of actual represented NC directions. This is a linear rescaling, **not a separately executed second-forward JVP**.
- The native 16-level upper PII center and its `±10⁻⁴`, `±10⁻⁵` endpoints retain the selected activation operands, output words and all recorded mask/schedule differences. The negative `10⁻⁴` endpoint changes four captured masks; both `10⁻⁵` endpoints have no captured-mask change. There is no upper PII `10⁻⁶` call in the parent archive.
- All 101 rounded f32/f64 final-output mismatches from #584 remain linked to the #586 stage observations. The first **recorded** selected number difference is NC12 `fd_satadj_inner.ncact_raw` and NR16 `d1_melt_consumer.nr_after`. Baseline NC16 has no rounded f32/f64 final-output mismatch. Stage records do not establish the first causal operation.

Of the 28,548 output rows, **27,201** have equal numeric endpoint words and are unresolved, **411** have distinct output words with captured masks stable, and **936** belong to the two crossing PII diagnostics. The 411 distinct rows are concentrated in TH/QV/QC/QR/QS/NC/NR; no field-level derivative acceptance follows from a distinct output word. The second-forward NC rows are 4,170 unresolved and 42 distinct under the same recorded-mask classification.

## Interpretation and next gate

This packet records absolute, relative, numerical field-scale and output-ULP metrics without assigning a general output-wise pass threshold after looking at the data. The earlier #583 contract established a relative FD threshold for **one NC16 branch-interior output**, not a common contract for all 468 outputs. Accordingly, all rows are exploratory or unresolved; `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`. Equal numeric endpoints, including signed zero, are unresolved even if their raw words differ. Captured-mask stability does not prove stability of uninstrumented branches.

For the next common execution, [the proposed output-wise gate](../../../docs/NATIVE_HOST_OUTPUT_FD_GATE_V1_20261112.md) must be fixed before collecting new endpoints. [The capture plan](../../../docs/NATIVE_HOST_BATCH4_COMMON_CAPTURE_20261112.md) includes the NC=0 operands, upper PII's missing stable step, actual rate-cap operand tangents, applied process/transport ledgers and same-call precipitation. It separates numerical consistency from physical units and host/RTTOV composition.
