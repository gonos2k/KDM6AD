# Saved seven-cell QNC weighted ledger — 2026-10-27

Base: main `1c28c241` / PR459. This follow-up corrects two opt-in trace
validation gaps and calculates an exact-rational **numerical coordinate
ledger** from PR459's already saved binary32 operands. It changes no
microphysics, advection arithmetic, operational ABI, model input or
observation support. No new host or RTTOV call was made.

## Two trace-tool corrections

The Fortran writer now clears its saved `qnc_shared_owner` before a call that
may return for nonselected species/RK. Its value writer, seven-cell capture
and tendency writer also require the *current* QNC selection and RK3. A
compiled `gfortran -O0 -fcheck=all` regression performs an owner call followed
by an unselected call: only the first call's value is recorded. The published
PR459 run had an owner tile followed by a non-owner tile and does not show the
stale-state contamination; this fixes future reuse of the instrumentation.

The shared-face analyzer now includes `MSFTY` in the raw-bit join to the same
run's PR457 V2 target trace. Both published cases have matching
`MSFTY=3F7BEF54`; replacing only the new trace's target MSFTY with `40000000`
causes the join and overall captured-check flag to fail. **The source RK3 Y
tendency multiplies by `MSFTX`, not `MSFTY`**; the extra MSFTY check closes a
recorded-input consistency gap for the low-order limiter/coordinate context,
not a change to the executed Y tendency formula.

## Exact ledger from the existing 7-cell trace

Let (i) denote each of the target and six face-neighbor cells. The source
RK3 tendency applies Z, X and Y divergence in that order. With the saved
binary32 cell metrics interpreted as exact rationals, set

\[
w_i=-\frac{1}{\mathrm{MSFTX}_i\,\mathrm{RDZW}_i}.
\]

For a face value (F=F^c+F^\ell), where (c) is the limited correction and
\(\ell\) is the separate low-order flux, the *exact algebra of the saved
operands* gives

\[
w_i\Delta\mathcal T_i
=\frac{\mathrm{RDX}_i}{\mathrm{RDZW}_i}\Delta F_{x,i}
+\frac{\mathrm{RDY}_i}{\mathrm{RDZW}_i}\Delta F_{y,i}
+\frac{1}{\mathrm{MSFTX}_i}\Delta F_{z,i}.
\]

Each \(\Delta F\) is upper/east/north minus lower/west/south. The recorded
shared face values are already equal on both sides. The additional metrics
needed for cancellation also agree as raw bits: `RDX`/`RDZW` for the x pair,
`RDY`/`RDZW` for the y pair, and `MSFTX` for the z pair. The replay checks
both value and coefficient and finds **12/12 correction/low-order internal
face contributions cancel exactly**. The seven-cell face sum therefore equals
the explicitly recorded **30 external perimeter face incidences**. These
perimeter values existed in PR459; their outside consumers and state changes
were not measured.

The replay also forms
\(\sum_i w_i(\mathcal T_{i,\mathrm{afterY}}-
\mathcal T_{i,\mathrm{beforeZ}})\) from the *recorded, rounded* stage words.
Its difference from the exact saved-face formula is reported separately.

| Numerical ledger in legacy raw host coordinates | Control | Alpha0.25 |
| --- | ---: | ---: |
| Exact weighted face contribution, equal to 30-face perimeter | −27,767,629,636.3833 | −27,767,544,586.4499 |
| Weighted difference of recorded tendency stores | −27,767,630,848.1075 | −27,767,543,347.6306 |
| Recorded minus exact saved-face calculation | **−1,211.7242** | **+1,238.8193** |

Every input word is converted from its stored binary32 bit pattern to an
exact `Fraction` before the face algebra or stage subtraction. The replay
records exact rational strings as well as approximate decimal values, with
separate Z/X/Y and correction/low-order terms. It does **not** reconstruct
which floating-point contraction the compiler emitted. The ratio of the
aggregate arithmetic difference to the aggregate face sum is about
\(4.4\times10^{-8}\), but that does not make the target's near-zero NC
positivity problem negligible.

## Provenance and remaining gate

The [original PR459 19-file packet](../harness/evidence/native_qnc_shared_face_2026-10-27/README.md)
and its source hashes remain unchanged. Its original replay pins the old
analyzer/overlay source, so use the `1c28c241` tree for that exact historical
entry point. The [new versioned replay](../harness/evidence/native_qnc_weighted_2026-10-27/README.md)
verifies all historical packet files, checks that every old analysis field is
unchanged under the new analyzer, requires the new MSFTY join to pass, and
then computes this ledger without model calls.

This weight is derived from the recorded numerical operator. It is **not a
certified dry-air mass, grid volume or physical particle-number weight**.
The ledger does not close an old/new QNC state budget, a tile/halo-boundary
budget or whole-domain conservation. The next measurement can be narrowed to
the same seven cells' old/new QNC, RK mass coefficients, any scalar source,
and actual applied state. A limiter modification should follow that state
budget, then be tested on the complete fixed observation support before any
candidate RTTOV cost or further assimilation is claimed.
