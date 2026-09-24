# Applied phase-transfer pilot (X1)

Base: public `main` after PR #236, `63fb4d3a`. This is a verification-only
cross-phenomenon pilot. No production physics, ABI, QC, native executable or
operational selection changed.

The audit accepts an explicitly isolated same-basis mass-mixing-ratio boundary.
For each process it receives a nonnegative *requested* amount and a
nonnegative *applied* amount. It checks that all processes drawing on one
reservoir fit that reservoir, that each source and destination uses the applied
amount, and that the fixed-`cpm` local temperature equation uses that same
amount with a signed latent-heat coefficient. It rejects nonfinite operands,
computed overflow and empty grids. It never chooses how competing requests
are allocated.

The real KDM freeze-control cap and inline state applier were exercised using
**seeded** D2/D3 phase amounts. Two requests of 0.0008 each compete for
`qc=0.001`; the cap produces 0.0005 each, and the resulting `qc`, `qi` and
`T` satisfy the local transfer and latent-work contract. A separately seeded
D1 melt rate is converted by `dt=20 s` into its applied amount and checked
against `qs`, `qr` and the `xlf0` cooling term. The phase-rate producers and
an actual native meteorological column were **not** executed by these tests.

The synthetic cases distinguish a valid shared allocation from two separate
0.7 draws against a reservoir of 1, reject heat calculated from an inconsistent
amount, reject state/request mismatches, and reject two validator false-accepts
found in Red review: `inf-inf→NaN` and zero-length grids.

Local verification: `PYTHONPATH=oracle:. python -m pytest` on the new pilot,
existing melt/freezing and process-control tests: **54 passed** with Python
3.10.11. Python 3.12 exists locally but has no `pytest` installation, so a
Python 3.12 run was not claimed. Existing torch.jit deprecation warnings are
unrelated to the pilot. Graphify code update completed and a semantic query
result records this report's bounded conclusion; the itemized status is in
`CHECKLIST_cross_phenomena_2026-09-24.md`.

The fixed-`cpm` relation is a **local temperature-update check**, not a full
enthalpy law. It omits other simultaneous processes, changing heat capacity,
pressure work, reclassification, cleanup, native f32 operation order and
host coupling. X2 in the checklist is the next live mixed-phase boundary.
Existing operational ice-transfer P1, physical number-basis question, MPI and
restart failures, independent radiance accuracy, and liquid observation gate
remain open.
