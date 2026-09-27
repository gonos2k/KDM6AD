# S10 build-preparation capacity measurement

This report summarizes one path-redacted `build-preparation-measure` receipt created on 2026-09-27. The single preflight invocation exited 0. The public summary is bound to plan SHA `3cebf313…b50a958f7`, estimate SHA `82f2b43c…ec96c7d3`, snapshot SHA `c4cac9cb…21efd5d`, and private receipt SHA `c0ecfcdc…397c39b9`. The raw private receipt is not published.

At 2026-09-27 03:41:08 UTC, the proposal estimated 717,666,816 bytes, with a safety factor of 2, a 4,294,967,296-byte reserve, and a 2,147,483,648-byte minimum. The preflight observed 19,817,902,080 free bytes against a required 5,730,300,928 bytes. Its status is `MEASURED_BUILD_PREPARATION_CAPACITY_ONLY`; capacity remains `MEASURED_ONLY_INCOMPLETE_COMMAND_INPUTS` because required link inputs and executable build commands are not complete.

This phase ran no static, toolchain, or environment probes. Its receipt has an empty command allowlist, null toolchain and environment digests, and false build/model permissions. The output root remained absent. No preprocessing, object compilation, link, or model command ran. The aggregate build gate remains blocked, the model-run gate remains blocked, and S10 remains OPEN.

An earlier preflight under the preceding plan revision stopped with exit code 2 because the inherited sanitized environment differed from its historical pin; it created no measurement receipt, so there is no receipt hash for that failure. The successful run used the reviewed capacity-only path, which does not validate that environment. The attempt-three configure evidence remained preserved, and this report does not claim that the capacity phase revalidated it.

See the [S10 capacity and command-gap report](s10_resource_capacity_command_gap_2026-09-27.json) for the incomplete build-input and full-matrix resource findings, and the [attempt-three configure-only report](s10_attempt3_configure_only_result_2026-09-27.json) for separate configure evidence. Neither this measurement nor configure-only evidence authorizes a build or model run.
