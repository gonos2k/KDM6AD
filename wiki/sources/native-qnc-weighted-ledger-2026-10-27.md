---
title: Native QNC seven-cell weighted ledger — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC seven-cell weighted ledger

Two post-PR459 tool gaps are closed: the opt-in Fortran writer clears stale
owner state before a nonselected call and gates all writes on current QNC/RK3
selection; the analyzer joins target MSFTY to the already recorded same-run
PR457 value. The old 19-file packet remains immutable, and a new companion
replay verifies the old case fields before calculating anything new.

From the saved seven-cell binary32 operands, exact rational arithmetic with
\(w_i=-1/(\mathrm{MSFTX}_i\mathrm{RDZW}_i)\) shows all six internal shared
faces cancel separately in correction and low-order components. The total
equals the 30 already recorded outer face incidences. Recorded weighted
tendency minus exact saved-face algebra is about −1,211.7242 (control) and
+1,238.8193 (alpha0.25) in raw numerical coordinates. This is not an
old/new QNC state budget, an executed FMA determination, or physical/domain
particle-number conservation. No new host/RTTOV/assimilation call occurred.

See [the derivation](../../docs/NATIVE_QNC_WEIGHTED_LEDGER_20261027.md) and
[versioned replay](../../harness/evidence/native_qnc_weighted_2026-10-27/README.md).
