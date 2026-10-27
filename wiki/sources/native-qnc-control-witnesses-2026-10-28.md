---
title: Native QNC same-level control witnesses — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC same-level control witnesses

The source-pinned control checkpoint was matched to all 54 fixed-support candidate failures at the **same native cells and levels** as [[native-qnc-host-backoff-review-2026-10-28]]. The 53 liquid failed profiles contain 54 layers with QC>0/NC=0 in candidate; every corresponding control layer has QC>0/NC>0. The single ice subnormal QI/NI mismatch is absent in control because QI=NI=0.

Among 29 candidate profiles newly invalid after pre-command READY40, 27 lose positive NC while retaining QC, and two acquire QC from QC=NC=0 without positive NC. Of the 25 profiles already invalid at READY, five have entirely different failed layers at final. These endpoint facts narrow representative traces but do not name the process that caused each transition. M0 still loses 54 profiles/378 cells and the full candidate cost remains undefined.

See [report](../../docs/NATIVE_QNC_CONTROL_WITNESSES_20261028.md) and [hash-bound packet](../../harness/evidence/native_qnc_control_witness_2026-10-28/README.md).
