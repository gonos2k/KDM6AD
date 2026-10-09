# Bounded MPI finalize controls

## Result

The standalone one-rank Fortran control completed through `MPI_Init`, `MPI_Finalize`, and the host-style C `_Exit(0)` call in four bounded arms. Each was built as `wrf.exe`, launched by `/opt/homebrew/bin/mpirun -np 1`, and returned launcher status 0:

| Linked runtime | Observer | Rank and launcher evidence |
| --- | --- | --- |
| MPI only | absent | rank 0; init/finalize returned ierr 0; launcher rc 0 |
| MPI only | present | observer saw finalize enter/return and `_Exit(0)`; rank 0; launcher rc 0 |
| Historical `libkdm6_c` plus its PyTorch runtime | absent | all four runtime dylibs loaded; rank 0; finalize ierr 0; launcher rc 0 |
| Historical `libkdm6_c` plus its PyTorch runtime | present | same dylibs loaded; observer saw finalize enter/return and `_Exit(0)`; rank 0; launcher rc 0 |

The full event lines, compile and launch commands, per-arm logs, executable hashes, and before/after pins are in [result.json](result.json). The reusable control is [mpi_finalize_control.f90](mpi_finalize_control.f90), with [run_controls.py](run_controls.py) compiling the host-flag variants and enforcing a 20-second timeout for each command.

Two additional direct Open MPI singleton launches, with and without the observer, returned direct-child wait status 0. The observer arm emitted `_Exit value=0`. These direct launches are separate from the `mpirun -np 1` arms. For the MPI-launched arms, the recorded status is the launcher’s aggregate status; the observer itself does not report a rank exit code.

## Provenance

The runner uses the historical native target’s `configure.wrf`, `mpif90` and Open MPI launcher; host Fortran flags include `-O2 -ftree-vectorize -funroll-loops`, the configure compatibility flags, and the project’s `-ffp-contract=off` rule. The linked arm uses the exact `libkdm6_c.2.0.0.dylib` pinned by the earlier native probe and the Python 3.10 PyTorch directory recorded in that native executable’s `LC_RPATH`. `DYLD_PRINT_LIBRARIES=1` confirms that `libkdm6_c`, `libtorch`, `libtorch_cpu`, and `libc10` loaded in both linked arms.

Green review corrected the receipt’s `configure.wrf` hash from the canonical private host file to the isolated host file actually named by the runner. The compile commands already used the matching host flags and libraries; this was a metadata-only correction, and no control was rerun.

The observer source and dylib are the original files in the earlier exit-observer directory. Its `wrf.exe` name filter is satisfied by the temporary control executable name, so the child rank markers are emitted. The original observer source and dylib, historical native `wrf.exe`, and historical KDM6 dylib have identical before/after SHA-256 values, recorded in the receipt. The first default-SDK compile failure is retained at `runs/without_observer/compile.log`; the first linked attempt with the unrelated Python 3.9 runtime is retained at `runs/historical_python39_loader_failure/` and was not counted as a passing control. With the active Xcode SDK supplied as `SDKROOT` and the native Python 3.10 runtime path, all four final arms passed.

## Coverage limits

This is a standalone MPI/C-exit forwarding control. The linked arms load the historical KDM6AD and PyTorch libraries but call no KDM6AD entry point and perform no physics or numerical work. These results do not demonstrate numerical instrumentation noninterference, WRF shutdown behavior, a native WRF rank exit/signal, or successful WRF termination. The MPI-launched controls report only the launcher aggregate status, so it cannot establish whether any rank signal occurred. The separate direct singleton controls report a direct child wait status. MPI entry is logged before rank becomes available; the post-init/finalize records are rank 0 because each control uses one rank.

No host model was launched in this control task. The prior bounded native probe expired before a WRF-start marker; WRF startup and shutdown observation remain a separate bounded evidence step.

## Graph coverage

The initial worktree query and canonical graph query did not cover the private MPI-finalize/host-launch path. The public worktree graph has since been refreshed; this report’s measured path and limits are represented in the bounded semantic JSON. The private host and licensed RTTOV source/build paths remain evidenced by source and build receipts rather than structural graph edges.
