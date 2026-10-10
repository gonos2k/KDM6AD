# PR398 fixed-candidate spatial review checklist

Base reviewed revision: `bf00721b` on open PR398; merged main remains PR397
`26ff5a1f`. The earlier budget/gradient/time/viewing-center diagnostics stay
closed in their demonstrated scopes. No repeated optimization or host run.

| Work | Status | Completion criterion |
| --- | --- | --- |
| Freeze candidate/regions before inspecting neighboring values | Done | `pr398_spatial_representativeness_2026-10-10/PREDECLARED.json`: native3×3 at frames1/4/6, AMI5×5, nominal VIIRS centers inside native-center bounds |
| Native geometry-only region | Done | `NATIVE_PATCH_GEOGRAPHY.json`; cell-center bounds are descriptive, not exact cell union or footprint |
| Native27 column/time diagnostics | Done, bounded scope | `NATIVE_PATCH_RESULT_v3.json`: valid39levels/40interfaces, center exactly matches intake; all27QC/NC0, max liquid ratio95.1460–95.9879%; no M/H |
| AMI seven-channel patch | Done | `OBSERVATION_PATCH.json` / CSV: 175BT, DQF0, exact center replay; IR105288.9325–293.7085K; paired calibration/SRF limits retained |
| VIIRS spatial categories and QA | Done, QA discrepancy open | 103phase1/type2 raw categories; flag0×94,5×9. `OBSERVATION_PATCH_QA_AUDIT.json`:9raw5 outside declared[0,1], no bit inference or area cloud fraction |
| Existing unused native-event inventory | Done, additional cases unavailable | `NATIVE_5KM_AVAILABILITY_v3.json`:84 path variants share July19 initialization; inspected stock lacks two other IC dates; not all84 physical runs newly validated |
| Spatial interpretation and source-specific limits | Done | `REPORT.md`: separate regions, phase homogeneity vs BT variability, conditional QA/time/calibration/geolocation; no unique process attribution |
| Canonical private preservation | Done | `LOCAL_PRESERVATION.json`:24 files,537339bytes, exact executed sources/selected arrays; canonical host directory0700/files0600, originals preserved |
| Final Green/Red coverage and counterexamples | Done | `SPATIAL_GREEN_REVIEW.md` / `SPATIAL_RED_REVIEW.md`: no remaining actionable blocker in bounded scope; actual QA metadata mismatch remains explicit |
| Pixel UTC, height datum, parallax, physical footprint | Open | Patch diagnostic alone does not establish these |
| Two unused warm-liquid event analyses | Open | Availability/QA/geometry-based selection; no BT residual selection or external-model substitution |
| Full flux budgets / calibrated B,R | Open | Existing state decomposition or pixel scatter cannot close these |

Score remains56/75 (74.7%). Spatial diagnostics may explain applicability;
files, repeated tests and another PR revision do not automatically add points.
