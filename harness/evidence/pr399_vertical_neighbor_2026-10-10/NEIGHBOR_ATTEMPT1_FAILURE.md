# PR399 vertical-neighbor direct-H attempt 1

The source-pinned one-shot batch stopped before the first RTTOV call. The first neighbor fixture preparation called the existing `run_analysis._prepare_fixture_copy` without its required `o3_rttov_topdown_ppmv` input. The failure receipt records an empty completed-row list and zero M, optimizer, and H calls. The one-shot marker is preserved; there was no retry.

The archived PR398 center H remains available and was not modified. Its inputs were bound to the native center during preflight, but this attempt produced no new neighbor BT values or costs. The attempt does not support a physical or scientific conclusion.

Plan SHA256: `b9c9553b4c8201fdf3a6f92f549d3f393ab38555311667355433deba06ac2e92`

Executed source SHA256: `5133d050186d2093d14f130bb99932bcf616f75e7e6200635d31bbd8e8230c5a`

Private failure archive: `/Users/yhlee/KDM6AD-k/host/research_evidence/pr399_native_neighbor_h_20261010/attempt1_no_h`
