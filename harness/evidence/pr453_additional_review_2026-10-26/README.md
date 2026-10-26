# PR453 additional review

The review began at PR head `a0e4c622`, after main advanced to `59d7926c`
through PR451 and PR452. The sole merge conflict was an add/add of the checklist;
the PR's dated H1 version and current-progress link were retained. The native
runtime, value bridge, observation code and numeric case products did not
change during this integration.

Public baseline arithmetic and source/history checks passed again. The result
remains 65,988 columns, 377,342 support cells and J=11.007963317242059. All three
trials remain inadmissible. This review does not add a model/RTTOV run or a
derivative/forecast certificate.

One low-priority documentation scope issue was reproduced on the executed
isolated value library. Its dt scalar check runs before FpEnvGuard construction.
An invalid-ncmin refusal adds FE_INEXACT while retaining the seeded exception,
rounding mode, null handle and untouched outputs. There is no tensor or kernel
work in this probe: one ABI refusal, zero KDM/host/RTTOV calls.

The FP64 bridge note now explicitly limits the claim to FP-control coverage and
the environment captured after scalar validation. It does not promise original
caller exception-status preservation. The operational entry and experimental
executable were not changed. Exact H1 note bytes remain archived for its original
manifest. Probe source and result/source/library hashes are included here.
