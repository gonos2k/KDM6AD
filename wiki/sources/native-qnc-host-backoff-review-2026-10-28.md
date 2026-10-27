---
title: Native QNC host-backoff current-source and baseline comparison — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC host-backoff current-source and baseline comparison

The versioned companion to [[native-qnc-target-host-backoff-2026-10-27]] pins the current saved-backoff and PD/RK-budget analyzers, which the prior packet called without direct source checks. The PR #465 packet and its output remain immutable. The current replay rejects both comment-only source drift and substitution of the pre-gate PR #462 budget analyzer.

On identical block-28 M0 observations/support, original control target IR105 BT is `285.822573426 K`, variant control `286.148468954 K`, and variant alpha0.25 `285.822483468 K`. Variant control→alpha changes −0.325985487 K; **original control→variant alpha changes only −0.000089958 K**. Block M0 RMSE is `24.475896309 → 24.476204946 → 24.474283624 K` in that order. The comparison uses existing arrays only and makes no new model/RTTOV call. Variant alpha still loses 54 full-domain fixed-support profiles / 378 channel cells: 53 liquid QC/NC and one ice QI/NI failures. A pinned **pre-command** READY40→final witness shows 25 already invalid before the T/Q command and 29 invalid only at the final checkpoint, without attributing a named process. No accepted analysis or full candidate cost follows.

See [report](../../docs/NATIVE_QNC_HOST_BACKOFF_REVIEW_20261028.md) and [current replay](../../harness/evidence/native_qnc_host_backoff_review_2026-10-28/README.md).
