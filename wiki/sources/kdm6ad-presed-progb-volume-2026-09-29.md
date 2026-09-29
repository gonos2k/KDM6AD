# ProgB volume at the sedimentation handoff (2026-09-29)

`oracle/kdm6/runtime.py` used to zero pre-sedimentation `brs` whenever
`qg<=qcrmin`, even if `brs>BRS_MIN` made `ProgB_param` active. The actual
ProgB output in that case is the density-capped `qg/rhox`; the Fortran gate
and current C++ runtime both keep it. The Python runtime now passes that
ProgB output directly to sedimentation.

The focused float64 regression uses `qg=5e-10`, `brs=1e-13`: it checks the
sedimentation input is `qg/900` and its local `qg` derivative is `1/900`.
On the pre-existing two-cell, three-subcycle cross-tree fixture, a fresh local
macOS C++ library (SHA-256 `fa16d746…266bef`) and the Python oracle now have
maximum relative VJP/JVP differences `1.82e-8`/`2.45e-7`. The old permitted
cell-0 divergence was removed from the regression gate; the `1e-6` criterion
was not relaxed.
This fixes that oracle handoff, not the unresolved S10 density policy, native
parity, or whole-host moment budget. Tiny float64 residue states can still
take a different gate from the operational float32 calculation.

Related: [[KDM6AD]] and [[KDM6AD Mathematical Microphysics Operators]].
