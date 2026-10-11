# Final Green review — PR404 follow-up

## Result

The additive v3 and evidence fixes resolve the prior Green review's actionable command/environment omission and the future-writer gaps recorded in `TEAM_AUDIT_RESOLUTION.md`. I found no new Green consistency blocker in the reviewed packet. This is a source/evidence review only; I did not rerun tests, acquire data, inspect model arrays, or run a native/model, RTTOV/H/K, KDM M, or optimizer path.

The v3 implementation requires a successful download receipt, exact planned key/count/byte coverage, one-to-one progress rows, expected local path/size/ETag, and unchanged local SHA-256 before calling the production reader. Its publication order checks conflicts before intake and writes `RESULT.json` only after both CSVs. Empty-scene outputs retain the declared CSV headers and report zero decoded scenes; external plan paths are represented without forcing a repository-relative conversion. The v3 raw-word/source-mask and canvas functions have the same normalized AST as v2, so these workflow changes do not alter the frozen mask implementation.

The 11 new integration cases use temporary NetCDF objects and a synthetic reader payload. Together with nine actual-netCDF4 source-mask cases and 16 unchanged LA-reader cases, the recorded local command reports 36 passed. `AUDIT_VALIDATION.json` records the exact prior 25-test command, the root's current 36-test command, Python/package versions, and thread settings; `LOCAL_TESTS.log` records the 36-pass result. The Flow Red report separately identifies its independent 36-pass invocation as `/opt/local/bin/python3` (Python 3.10.11). These are two executions of the same 36-case coverage, not 72 distinct tests; the command records are now clearly distinguished. The nonempty synthetic case checks writer dataflow, not the real LA scene reader or full-scene decode. The tests do not exercise a network acquisition or prove native/model integration.

`SIDECAR_AXIS_CONTRACT.json` binds the existing private NPZ hash, states the `(5, 5, 9)` axes and center, and lists the channel order. The channel IDs and order agree with `CLEAN_IR_CHANNELS` in the production reader; the sidecar hash still matches the private 0600 file. The original PR404 ten-entry manifest and PR403 21-entry manifest still match every listed byte count and SHA-256. V2, the executed repair helper, receipts, and existing private capture remain preserved.

The old-head CI results remain correctly separated. `AUDIT_VALIDATION.json` identifies harness `38105648779`, oracle `38105648764`, and port `38105648778` as checks for head `4b65577f7c2062ab99dffe50ced233a092457184`; they are not evidence for the changed v3 head. Current-head CI must be recorded separately after the follow-up changes are pushed. The publication tests also establish successful write order, not crash durability; the team resolution records that limit.

The completion matrix, PR404 checklist, and wiki source now identify v3 as the future writer and state that only synthetic integration ran. Same-date July 20/21 native analyses remain pending matching original inputs and lineage within the bounded availability search; the packet does not claim global archive absence. GK2A AMI L1B remains the only admitted satellite observation, other sensors/L2 remain deferred extensions, and the user-assigned 78/100 baseline is unchanged.

## Evidence and limits

- Verified both frozen public manifests again: PR404 10/10 entries and PR403 21/21 entries.
- Parsed `AUDIT_VALIDATION.json` and `SIDECAR_AXIS_CONTRACT.json`; recomputed normalized AST identity for v2/v3 raw-mask and canvas functions; checked channel-axis IDs/order against the production channel declaration and bound sidecar hash.
- Two independent 36-pass invocations are recorded: the root-pinned command/environment in `AUDIT_VALIDATION.json` and Flow Red's `/opt/local/bin/python3` invocation. They cover the same 36 cases and must not be summed as distinct coverage.
- Did not independently reproduce the 36-test run or query GitHub. The recorded command/log are accepted as packet evidence. Prior CI is old-head evidence only; no current v3-head CI result is certified here.
- Did not repeat private source reads or any model/native analysis. The earlier bounded availability finding and private sidecar checks remain scoped as previously recorded.

**Disposition:** Green on v3 code-path consistency and the stated synthetic coverage. The local command/environment gap is closed by the additive receipt, and the two 36-pass invocations are distinguished without double-counting. The original mask/sidecar and PR403 results remain preserved. Keep current-head CI and real v3 acquisition/full decode/model analyses explicitly pending until their own evidence exists.
