# Independent Red review: native valid-time linkage

## Disposition

No logical omission found in the reviewed time-coverage flags or their scope. The result separates boundary interval coverage from native-input selection and analysis admission. Both target dates remain `PENDING_NATIVE_INPUT`; selected run/state/forcing/pressure/surface are null and `analysis_executed` is false.

## Independent checks

- Read the canonical IC `Times` and BC `Times`, encoded `THISBDYTIME`, and encoded `NEXTBDYTIME` fields only. The current `native_time_linkage.py` SHA-256 matches the value in `NATIVE_TIME_LINKAGE.json`; the preserved PR403 L1B result SHA-256 also matches.
- Re-ran the focused suite: `python3 -m pytest -q harness/evidence/pr405_native_valid_time_2026-10-11/test_native_time_linkage.py` — **8 passed**.
- For July 20 05:56, the nominal-as-model-UTC assumption yields a 29 h 56 min lead from July 19 00:00 and places the target 17 h 56 min after the final BC interval endpoint. July 21 05:56 yields a 53 h 56 min lead and lies 41 h 56 min after that endpoint. Both `boundary_supports_run_to_target` and `boundary_supports_existing_8frame_intake` are false for the inspected file.
- The three required times remain distinct: nominal slot 05:56, local background valid time 05:55:40, and existing 8-frame output end 05:58. The last is represented as a two-minute output/coverage extension; it does not redefine the observation time.
- `same_initialization_date_required` is false as policy. A synthetic earlier-initialization case passes only when a continuous boundary interval spans the full target/intake time. The actual July 19 interval does not cover either current target.
- The final BC interval is `[09:00, 12:00)`. The script allows a final state at the endpoint but separately rejects advancing from it. The ordinary host guard and WRFPLUS/dynamical-adjoint equality condition are documented as source-level branches; no compiled configuration is inferred.

## Evidence limits

These flags establish only whether the recorded boundary intervals span the declared model-time assumption. They do not admit a native run, certify an earlier IC's lineage or physical state, validate pressure/surface fields, or establish forecast quality. GK2A filename time remains an explicitly declared assumption, not measured pixel UTC. No boundary meteorological arrays, forecast files, additional boundary paths, archives, data sources, or model execution were used.
