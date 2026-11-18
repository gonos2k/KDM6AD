# Conditional native QV → heat capacity → D1 temperature derivative

This packet extends the [conditional ice-speed/sedimentation/D1 chain](../native_qnice_d1_chain_ad_2026-11-04/README.md)
using the **same recorded native call**. It makes no new host, C++, Fortran,
or RTTOV run. The parent replay/result, executed thermo source snapshot, and
current Python oracle thermo source are checked by SHA-256 before analysis.

```bash
python harness/evidence/native_qnice_d1_cpm_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_qnice_d1_cpm_ad_2026-11-04 -v
python -O -m unittest discover -s harness/evidence/native_qnice_d1_cpm_ad_2026-11-04 -v
```

The CLI ends with `NATIVE_QNICE_D1_CPM_AD_REPLAY_PASSED`. The result JSON is
hash-pinned. Fresh tangents are checked against independent source algebra,
VJP transpose contraction, represented-gap differences and branch/ULP
diagnostics; saved reductions need not have identical bits across Torch/CPU
implementations.

## Same-call baseline

The original 39-level D1 trace records QV, `pre_cpm`, `cpm_safe`, applied
ice melt and D1 temperature. Runtime-entry QV and D1-entry QV are **raw-bit
equal at all 39 levels**. The public `compute_cpm()` producer, with its
executed f64 constants and two-rounding operation order, reproduces all 39
`pre_cpm` words; the subsequent `max(pre_cpm,1e-9)` reproduces all 39
`cpm_safe` words. Feeding this recomputed coefficient into the parent
fixed-speed chain preserves its 13 stage fields × 39 raw-bit baseline and
the dynamic-speed selected baseline outputs.

This packet adds a direct QV handoff check that the parent D1 packet did
not make. In that parent packet's **test-only rehashed override**, changing
native-15 QV by one f64 word can leave rounded `pre_cpm` unchanged and
pass. Here the same mutation conflicts with captured runtime-entry QV and
is rejected by the handoff check. The parent packet and its documented
override semantics are unchanged.

## Local derivative and resolution

At native 15, the captured values are QV `0.005104054231196642`,
`cpm_safe=1008.7971032572444`, and applied ice melt
`6.109135817357022e-11`. Snow and graupel capped melt amounts are zero.
For a **unit relative perturbation of D1-entry QV**, with the other
operands held fixed,

```text
δcpm = (1846.4 − 1004.5) × QV = +4.297103257244453
δT15 = 350000 × pimlt_qi × δcpm / cpm² = +9.028507464652678e−11 K
```

The D1 `(QC,QI,NC,NI,T)` and selected C3 NI output vector has a nonzero
JVP only in D1 T15. The oracle's `compute_cpm()` is inside the Torch JVP/VJP
map. The weighted VJP contraction and independent formula agree. Central
differences use the represented QV endpoints and report output f64 spacing:

| Relative half-step | T endpoint signal | Signal in T f64 spacings |
| ---: | ---: | ---: |
| `0.25` | `4.5133674575481564e−11 K` | 794 |
| `0.1` | `1.801936377887614e−11 K` | 317 |
| `0.05` | `9.038103598868474e−12 K` | 159 |
| `0.01` | `1.7621459846850485e−12 K` | 31 |

The difference acceptance includes both finite-difference curvature and
the recorded T output spacing. A relative `1e−3` half-step would produce
only about three T spacings and is not used as a precision gate.
[Saved output and gaps](results.json)

## Scope

QV is varied at the **D1 input**. Density, pressure, temperature, QI melt
amount, snow/graupel melt amounts, D2–D4 applied amounts, other preamble
outputs, transport state, ice speeds, and substep schedule are fixed. In
particular, this test does not recompute the other melt-rate producers when
QV changes. The full host QV path can also alter density, saturation,
other process rates and downstream states. This packet checks the partial
QV→cpm→D1 thermal path on one f64 native numerical state; it does not
certify operational f32 or a host-to-RTTOV QV derivative.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.

A later [active native D1 and QI interface packet](../native_qi_applied_d1_active_2026-11-04/README.md)
records nonzero snow/graupel melt and actual QI applied transfer in a
different column of the same model call. Their producer derivatives remain
to be tested.
