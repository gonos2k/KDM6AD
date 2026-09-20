# Native number boundary and applied sedimentation follow-up

Keep PR230's offline arithmetic result. Use existing 5 km inputs and native
39-layer grid; no density conversion, physics correction, QC or tolerance change.

- [x] Record canonical source, compiler/linker, rebuilt module, inherited host
  objects, executable and original input identities in an isolated build.
- [x] Read-only capture at actual mp37 host entry, process invocation, limited
  rates, state application and host return; distinguish this from mp137 ABI.
- [x] Capture rain/ice sedimentation departure, arrival, state and surface exit
  at matching interfaces/substeps, retaining source density, qv and thickness.
- [x] Compare noninstrumented and instrumented histories at raw-bit precision.
- [x] Replay measured native ledgers with explicit conditional measures and
  reject missing or mismatched records; keep physical unit contract open.
- [x] Green/Red review, focused Python 3.12 checks and Graphify refresh.
- [ ] Resolve physical number basis, all species transport and density-coupled
  dynamics. A local measurement does not resolve those wider contracts.

Measured nonzero internal transport is not a conservation pass: ice departure/arrival
mismatch is retained as an open production-contract finding. Surface export was zero.
