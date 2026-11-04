# Actual C++/libtorch AD for the selected native D1-to-ProgB stage

This packet starts from the frozen D1-entry operands of the
[same-call postmelt ProgB record](../native_d1_progb_ad_2026-11-04/README.md)
at native `(203,149,16)`, `runtime_call=one_step_call=2`. An isolated C++
executable links the **exact static `libkdm6.a` archive** recorded in that
native DSO build. It calls the executed C++ `melting_torch`,
`apply_melt_freeze_inline`, and `progb_param_torch` functions on captured
f64 operands. The same graph is differentiated with C++ autograd: JVP uses
the double-reverse method of `Handle::jvp`, and VJP uses
`torch::autograd::grad`. This is an offline **conditional stage map**,
beginning at the captured D1 input; it does not replay the preceding
sedimentation or persistent ProgB producer history.

```bash
python harness/evidence/native_d1_progb_cpp_ad_2026-11-04/replay.py
python -m unittest discover -s harness/evidence/native_d1_progb_cpp_ad_2026-11-04 -v
PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_d1_progb_cpp_ad_2026-11-04 -v
```

The archived [C++ source](cpp/main.cpp), [build recipe](cpp/CMakeLists.txt),
[build receipt](raw/build_receipt.json), and
[raw C++ output](raw/cpp_result.json) are SHA-pinned. The receipt binds the
parent native build's static archive hash, captured CSV hash, C++ source,
object and executable hashes, compiler flags, Torch 2.13.0 libraries, and
the successful run command. The private static archive and executable
are retained locally and are not redistributed. The public replay checks
the receipt and archived output against the pinned native packet; it does
not itself compile or execute C++ in CI. A fresh build requires the
retained parent archive named by `KDM6_CAPTURE_ROOT`.

## Actual C++ forward and graph derivatives

The C++ program constructs the selected D1 state from raw f64 words in
the parent CSV. QV, T, QG, and the D1-entry persistent `rhox` are graph
inputs. Density, pressure, QI/NI, snow/graupel slopes and intercepts,
`work2`, `precg2`, entry QR/NR/BRS, geometry, and the 20 s schedule are
held at captured values. `cpm` and `supcol` are recomputed from graph
QV/T. D1-only freeze amounts are zero. At the selected active cell,
postmelt ProgB uses its fresh QG/BRS outputs; inactive persistent-
diagnostic history is outside the map.

The C++ baseline has **10/10 raw f64 words identical** to the selected
native capture:

| Direct C++ output | Selected native value |
| --- | ---: |
| Applied snow melt | `−1.3202611149878743e−4` |
| Applied graupel melt | `−1.2225833390863422e−5` |
| D1 QG | `4.1812234388383836e−5` |
| D1 BRS / postmelt returned BRS | `4.646212004038053e−8` |
| D1 NR | `1499.7893838072516` |
| Postmelt `rhox` | `899.9209324078314` |
| `avtg`, `bvtg` | raw words match the native record |
| D1 temperature | `274.6303629975879 K` |

Four D1-entry directions are differentiated: relative QV16, absolute
T16 in kelvins, relative QG16, and relative persistent-`rhox`16. The
actual C++ JVP is compared componentwise with the independent analytic
tangents from the parent D1/ProgB source equations. A mixed ten-output
VJP seed gives the expected transpose contraction. Each finite-difference
endpoint is evaluated by the C++ stage functions and independently
replayed by the scalar D1→ProgB formulas in **all ten raw f64 output words**.
The public verifier now recomputes `math.fsum(weight × validated_JVP)`
from the ten checked JVP components and separately compares each archived
`jvp_dot` and `vjp_dot` with that reference under a bound scaled by the
sum of absolute weighted terms. It retains the C++ VJP/JVP transpose
comparison. A rehashed test output with **both stored dot products set to
zero** is rejected. This checks the archived contractions' consistency;
it is not an independent oracle for every VJP component.
The JVP-dot allowance follows the ten-term reduction of rounded products.
Applying that same numerical gate to the archived VJP dot is a consistency
check for this fixed fixture; it is not a general bound on rounding through
the entire reverse-mode graph.
The largest absolute C++–analytic JVP difference among the ten outputs
and four directions is `5.684341886080802e−14`; the largest FD–JVP
residual normalized by `max(1,|JVP|)` is `2.539004969644758e−8`.

| D1-entry direction | Actual C++ postmelt `rhox` JVP | Returned BRS JVP |
| --- | ---: | ---: |
| Relative QG16 | `+1163.0564367765057` | approximately `0` |
| Relative persistent `rhox`16 | `−263.13550436867445` | `+1.3585452844342611e−8` |
| Relative QV16 | `+1.3877787807814457e−17` | `−2.5627159771234574e−12` |
| Absolute T16, 1 K | `+5.684341886080802e−14` | `−8.914889997487064e−9` |

The QV/T density signals are at the cancellation/rounding scale, and are
not resolved physical contributions. Their analytic zero or near-zero
expectations are checked with direction-specific cancellation allowances:
for QV, `2e−17` on density, `2e−18` on `avtg`, and `2e−22` on `bvtg`;
for T, bounds are tied to the respective baseline output ULPs. A
rehashed `+5e−13` change to the QV density JVP is rejected by the full
replay. These limits describe numerical resolution, not a resolved
physical signal. The
QG/`rhox` directions have clear interior signals.

## Upper-cap transition and numerical boundary

For local JVP–FD agreement, relative QG and `rhox` use half-steps
`1e−5, 1e−6, 1e−7`; both endpoints stay in the active `800–900` density
segment. The previously used relative-QG `h=1e−4` is recorded as a
**different-branch finite perturbation**. The direct C++ positive endpoint
selects `rhox=900`, while the negative endpoint selects approximately
`899.8046267641537`. The independently calculated positive threshold is
`6.798259282050436e−5`. Its centered secant is not used as a local JVP
acceptance test. The public replay checks both C++ crossing endpoints
against independent scalar output words and verifies the cap selection.

## Limits

This is direct C++ AD of the conditional D1-entry-to-postmelt-stage graph,
not a perturbed private host call, a full-subcycle derivative, or the
public C ABI's end-of-step `Handle` JVP/VJP. The archived native build used
the experimental f64 `norm_actual` path. This packet does not establish
operational f32 behavior, upstream parameter production derivatives,
inactive persistent-ProgB history, later BRS limits, QNICE's physical
unit, or whole-host/GK2A–RTTOV sensitivity. The executable source uses
the capture variant's extra value-only checkpoint argument at the inline
store; no captured value is detached into the AD graph. Test-target
assertions are enabled, and `-ffp-contract=off` is recorded.

`scientific_status: INCONCLUSIVE`; `physical_unit_status: INCONCLUSIVE`.
