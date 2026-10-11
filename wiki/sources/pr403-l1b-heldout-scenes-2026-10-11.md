---
title: AMI L1B-only research edition and two held-out observation scenes
type: source
date: 2026-10-11
---

# AMI L1B-only edition and held-out scenes

The user fixed current satellite observation input to GK2A AMI Level-1B. External SST, MLS, VIIRS and Level-2 products are later extensions, not completion gates. Native model IC/BC and RTTOV fixed gas/surface/top assumptions remain necessary model inputs. [Current contract](../../harness/evidence/CURRENT_OBSERVATION_DATA_CONTRACT.md) and [completion matrix](../../harness/evidence/AMI_L1B_RESEARCH_EDITION_COMPLETION.md) supersede broader prerequisites without rewriting historical execution.

The predeclared July20/21 scenes were acquired from the exact nominal05:56 LA020GE slots:18 original files,8,555,216 bytes. The unchanged production reader/calibration decoded nine thermal channels; the same geometric target selected a pixel679.55m away and a fixed5×5 patch on each date. DQF0 denotes source quality, not cloud/phase/SST. Raw time/navigation fields preserve OBT and planned UTC, while actual pixel UTC remains unverified.

[Result](../../harness/evidence/pr403_l1b_heldout_2026-10-11/RESULT.json), [report](../../harness/evidence/pr403_l1b_heldout_2026-10-11/REPORT.md), [coordinator report](../../harness/evidence/pr403_l1b_heldout_2026-10-11/COORDINATOR_REPORT.md) and [coverage review](../../harness/evidence/pr403_l1b_heldout_2026-10-11/COVERAGE_REVIEW.md) distinguish observation intake from analysis. These are separated scene dates, not proof of independent weather events; matching original native inputs and same-configuration analyses remain pending. No model, RTTOV, KDM or optimizer call occurred.

[[pr402-finite-input-response-2026-10-11]] remains the bounded finite-input-response evidence. Its external-data collection suggestions are deferred under the current contract. Previously fixed July19 L1B/native numerical evidence can be reused as a declared test case without admitting historical VIIRS phase/selection rationale as current truth. New modeled cloud/number states are inferred results, not independent observations.

The broader historical56/75 reference is not transferred or increased automatically. The current matrix records executed, conditional and pending requirements; no new weights or denominator have been assigned.
