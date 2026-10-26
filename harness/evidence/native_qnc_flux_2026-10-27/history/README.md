# Earlier PR457 instrumentation and failed attempts

This packet contains only the valid V5 control-on and V6 alpha025-on 77-row V2
traces and their same-run auxiliary traces. Earlier artifacts remain in the
canonical private research tree; they are not merged into the current analysis.

- The PR457 V1 source overlay remains at
  `host/research_evidence/native_qnc_flux_trace_20261026/source_overlays/pr457_v1/`.
  Its overlay receipts have SHA-256 `89332a9a5a3b68792ea66ec214d604ac71b04806837e699e79c8cf16cb1825d1`
  (module_advect_em) and `aece0a4e5072ccd6aa0a134dd663f1463003195353b108cfc2120e0b2d538824`
  (module_em). V1 is historical instrumentation context, not part of the current
  successful V5/V6 packet accounting.
- `runs/pr457_v5/alpha025_pr457_v5_off/run_result.json` is a preserved pre-step
  failure (`KeyError: 'alpha025_plan'`; zero completed host steps). It is not a
  successful run and is not counted in the current evidence.
- `runs/pr457_v3/control_pr457_v3_off/run_result.json` records one completed
  trace-off control step with a valid endpoint comparison; it is retained as an
  earlier noninterference arm, not one of the selected V5/V6 pairs.
- `runs/pr457_v3/control_pr457_v3_on/run_result.json` records one completed host
  step followed by rejection of its 154-row V1 capture (`line 3: expected pinned
  step 3, got 20`). This is a post-step reader failure, not a valid V2 trace.
  V3 therefore contributes two completed host steps/four KDM wrapper entries
  to broader campaign history, but not to the corrected V5/V6 pair accounting.
- Prepared plan receipts and earlier revisions remain separate from executed
  runs. The current pair receipts alone establish the successful V5/V6 trace
  noninterference reported in this packet.
