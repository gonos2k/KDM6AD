# ProgB volume at the sedimentation handoff (2026-09-29)

`oracle/kdm6/runtime.py` used to zero pre-sedimentation `brs` whenever
`qg<=qcrmin`, even if `brs>BRS_MIN` made `ProgB_param` active. The actual
ProgB output in that case is the density-capped `qg/rhox`; the Fortran gate
and current C++ runtime both keep it. The Python runtime now passes that
ProgB output directly to sedimentation.

The focused float64 regression uses `qg=5e-10`, `brs=1e-13`: it checks the
sedimentation input is `qg/900` and its local `qg` derivative is `1/900`.
This fixes that oracle handoff, not the unresolved S10 density policy, native
parity, or whole-host moment budget. Tiny float64 residue states can still
take a different gate from the operational float32 calculation.

Related: [[KDM6AD]] and [[KDM6AD Mathematical Microphysics Operators]].
