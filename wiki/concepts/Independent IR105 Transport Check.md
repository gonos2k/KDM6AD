# Independent IR105 Transport Check

The C5 actual liquid sea case is a fixed input experiment, not a representative
weather sample. [[KDM6AD Differentiability Audit]] distinguishes numerical
self-consistency from physical accuracy; this check adds a separately implemented
transport solution while retaining the same optical tables and boundary sources.

C-DISORT 2.1.3 reproduces the mapped pure-absorption boundary equations and
converges over 8/16/32 streams. Its IR105 BT differs from RTTOV DOM32 by about
0.000287 K and its NC directional signal by about 0.00073%. C-DISORT freezes
thermal source slopes in very thin layers; RTTOV uses linear sources there.
Formal clear-column integration reproduces both rules and explains their gap.

The comparison does not certify optical tables, particle-size calibration,
observational error covariance or overall S11 accuracy. Original land/sea
100/10 threshold units and empirical rationale remain unrecovered. No threshold,
operational default, NCCN return or physical approval was changed.

- [Executed comparison and replay](../../harness/evidence/REPORT_independent_DISORT_2026-10-03.md)
- [Bounded threshold provenance search](../../harness/evidence/REPORT_S2_calibration_provenance_2026-10-03.md)
- [Active checklist](../../harness/evidence/CHECKLIST_pr361_followup_2026-10-03.md)
