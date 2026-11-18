# Source, build, and run scope

The source-bound overlay input was the private PR #481 `solve_em.f90` with
SHA-256 `73d4ac972e3576d151b4a04ee8a263da0e3a9d19734ba6e75a1d83c1a055a451`.
The public overlay SHA is recorded in `execution_summary.json`. It generated
the private solve source SHA `56809d2134bc8cc5ada8a0c3b678994009f44ba88e469c3f5d5560c810c2264f`.
The isolated build replaced only `solve_em.o` in the PR #481 archive. Its
executable SHA is `83082927c18fbb1c47ab67b34b0bf0b22e138365b0d4fa7a7f868fb81f17db29`;
the KDM DSO SHA remains `9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`.
The private build receipt SHA is `fbb46253edbd4f71e564563486e687e5bdc453ffaacec7e0f66b553ba2ee80bb`.

The first solve compile attempt was interrupted before any host call because
the overlay still referenced an OpenMP runtime routine absent from the
serial parent link. It is excluded. The revised source removes that call,
then compiled and linked in the isolated build above. Six completed runs
form the accepted set; case, pilot, trace mode, plan SHA, run-result SHA,
checkpoint SHA, ACK, and inherited trace hashes are listed in
`execution_summary.json`. The first two alpha runs used a controller with an
8 GiB disk preflight. The other four used a controller that differs only by
a 6 GiB disk preflight; each run result records its exact controller SHA.

The full private executable, build commands, checkpoint arrays, and run
receipts are not republished. The public replay checks the *published*
source/data pins, parent replay, raw sample and delta arithmetic, and
recorded hash relationships. The build and full-array claims come from the
private producer and were checked locally; public replay alone cannot
independently rebuild the private host.
