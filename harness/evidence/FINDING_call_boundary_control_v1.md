# The call-boundary control: legacy is clean, conservative is not

Owner review §3 of the PR #100 review. The Fortran N=1 vs N=3 contrast was offered
as a coefficient-only control and is not one — re-entering the kernel three times
also re-runs entry normalisation three times, and the four external auxiliaries
being stateless is not evidence that they are the complete set of call-local state.

The review names the control that separates those, and it is now run.

## Why the C++ leg is the control

The port recomputes `cpm`/`xl` every **sub-cycle**, and both backends pick the same
sub-cycle count (`compute_loops_max`, coordinator.cpp:1297, is the Fortran's
`max(nint(delt/dtcldcr),1)` at F:930). So in C++:

| | calls | loops/call | **dtcld** | **coefficient refreshes** |
|---|---|---|---|---|
| N=1 | 1 | 3 | 100 s | **3** |
| N=3 | 3 | 1 | 100 s | **3** |

Identical step, identical total, **identical refresh count**. Any difference is
therefore a call-boundary artifact with the thermodynamic policy held constant.
Both members report their own `loops` and `dtcld` in the stream, so this is
checkable from the output rather than asserted here.

## Result

`arithmetic_multisubcycle_v1`, 300 s, max absolute difference over cells.

| arm | `th` | mass | number | precip | **state** |
|---|---|---|---|---|---|
| **C++ legacy** | 0/12 · 0 | 0/72 · 0 | 0/48 · 0 | 2/9 · 3.886e-03 | **bitwise identical** |
| **C++ conservative** | 3/12 · 2.670e-03 | 12/72 · 1.844e-05 | 3/48 · 3.942e+06 | 2/9 · 3.870e-04 | **18 records differ** |
| Fortran legacy | 4/12 · 2.899e-04 | 19/72 · 1.336e-08 | 8/48 · 5.120e+02 | 2/9 · 3.522e-03 | 31 records differ |

Three separate readings, and they do not agree with each other.

## 1. For legacy, the confound is measured to be zero

The C++ legacy state is **bitwise identical across all 132 state records**. With the
refresh count held constant, splitting 300 s into three calls changes nothing in the
state — so repeated entry normalisation and any call-local state reset contribute
**zero** on this fixture, in that leg.

That is the direction that supports the coefficient attribution for the Fortran
legacy N=1/N=3 state difference, and it is the specific confound the review said was
open.

**It is evidence, not proof.** The two backends do not share an entry path — that is
the whole subject of the port — so "the C++ entry clamp contributes zero here" does
not establish that the Fortran one does. What it removes is the generic argument
that *any* re-entry must perturb the state: on this fixture, re-entry demonstrably
need not. Closing it fully needs a per-call entry-clamp digest on the Fortran side,
which is not built.

## 2. For conservative, the control fails, and that is the new finding

The C++ **conservative** state is not identical: 18 records, `th` up to
**2.670e-03 K** — an order of magnitude larger than the Fortran legacy difference
this experiment set out to explain, and with the coefficient policy held constant.

So **the conservative interface is sensitive to how the same 300 s is divided into
kernel calls**, independently of the thermodynamic-coefficient question. For the
conservative variant the N=1/N=3 contrast cannot be read as a coefficient control at
all: there is a second mechanism of comparable or larger size.

The number moment moves most (3.942e+06). That is `ni`, not `nr`: the localisation
below shows the interface never touches `nr` or `qr` on this fixture, so this is
**not** the channel the conservative-`nr` transport blocker concerns.

This is a **conservative-specific** sensitivity, so it is in C4's subject area, and
it was not visible in any single-call comparison. It is a synthetic 300 s
microphysics-only integration and no operational claim follows from it.

## 3. Precipitation moves in all three arms

`precip` differs at 2 of 9 columns in **every** arm, including the one whose state is
bitwise identical. So the precipitation channel is sensitive to call segmentation
independently of both the coefficient policy and the variant.

That is a cross-check on the refinement chain, where precipitation was the one group
that did not converge (p = +0.028 from 100 s to 50 s, non-monotone successive
differences). Two independent experiments point at the same accumulation path. The
mechanism is still undiagnosed — onset time, bottom cap or threshold firing at
different steps, and `mstep` topology all remain live.

## Localisation, and a mechanism hypothesis that failed

The conservative sensitivity is not diffuse. Every differing state record is in
**column 3 at k = 0, 1, 2** — the cold column, 242–244 K — and the interface is
active in eight cells across three columns, so the sensitive set is a strict
subset of where it acts.

Per field, comparing where the interface acts (legacy vs conservative at N=1)
against where segmentation matters (conservative N=1 vs N=3):

| field | interface-active | segmentation-sensitive |
|---|---|---|
| `ni` | col 3, k 0–2 | **same set** |
| `qi` | col 3, k 0–2 | **same set** |
| `qs` | col 3, k 0–2 | **same set** |
| `qc` | col 3, k 0–2 | **same set** |
| `qv`, `th` | cols 1–3, 8 cells | col 3 only |
| `nc`, `bg` | col 3, k 0–2 | **none** |
| `nccn` | cols 1–2, 4 cells | none |
| `qg` | col 3, k 0 | none |
| **`nr`, `qr`** | **never** | none |

Two things follow immediately. **This is not the rain-number channel**: the
conservative interface never touches `nr` or `qr` on this fixture, so the
conservative-`nr` transport blocker's channel is simply not exercised here.
And `nc`/`bg` are interface-active in the same three cells yet insensitive, so
"the interface touched it" is not sufficient either.

`ni` leads in relative terms at every level — 35%, 43%, 50% — ahead of `qs`
(38% at k=2), `qi` (24%) and everything else. The interface transports **mass
with ρΔz and number with the legacy Δz-only measure**
(`sedimentation_conservative.cpp:91-92` against `:109`, and the comment at `:172`),
the same mismatch flagged in-source as the release gate for `nr`.

That suggested a mechanism: the Δz-only measure creates ice number, `ni` grows past
the `[0, 1e6]` entry cap (`runtime.cpp:435`, F:836), and because that cap is applied
**once per kernel call, outside the sub-cycle loop** (line 435 against the loop at
441), how often it fires depends on how the 300 s is divided. The direction fits —
every N=3 `ni` is *lower* than its N=1 counterpart, which is what repeated capping
would do.

**It is refuted by its own control.** Measuring `ni` at the intermediate call
boundaries:

| | t = 100 s | t = 200 s |
|---|---|---|
| legacy | 6.5e4, 7.5e4, 8.8e4 — under cap | **1.61e6, 2.32e6, 3.35e6 — over cap** |
| conservative | 6.0e4, 7.3e4, 8.7e4 — under cap | **1.63e6, 2.35e6, 3.40e6 — over cap** |

Legacy breaches the same cap at the same boundary by nearly the same amount, and
legacy is bitwise identical across the two segmentations. So the cap firing at a
call boundary is **not sufficient** to produce a difference, and the hypothesis as
stated is wrong. Recorded rather than dropped, because the numbers above are the
reason to stop believing it.

What remains is that the two variants differ in one place — the interface — and
only the conservative one is segmentation-sensitive, in exactly the cells where the
interface touches the ice species. Which step inside the interface carries it is
not established, and separating the candidates needs per-sub-cycle instrumentation
of the conservative transfer, which is inside frozen C++.

## What this changes

| claim | before | now |
|---|---|---|
| Fortran legacy N=1/N=3 state difference is coefficient policy | plausible, confound open | **confound measured at zero in the C++ leg**; entry-path asymmetry remains |
| The same holds for conservative | assumed | **false** — a second mechanism of larger size exists |
| Precipitation anomaly is a refinement artifact | one experiment | **two independent experiments**, same channel |

The supported statement for legacy becomes:

> Over a synthetic 300 s microphysics-only integration, coefficient refresh
> frequency accounts for the observed Fortran legacy call-segmentation sensitivity
> in the state, to the extent the C++ leg's zero call-boundary effect transfers.
> For the conservative variant it does not: call segmentation there is its own
> operator difference.

## Method

`harness/g33_overlay/g33_refine_driver.cpp`, a separate translation unit from
`abc_driver.cpp` — the bundle manifest anchors that driver's **binary** digest
(`canonical_driver_sha256`), so adding a mode to it would mean the source no longer
reproduces the anchored artifact. Linked against the canonical archive only, never
the diagnostic overlay: the refinement measures the operator, and instrumentation
would be a second difference between members.

The C++ returns per-step increments while the Fortran accumulates internally, so the
driver sums them — the two legs then report the same quantity, the 300 s total
rather than the last sub-call's share.

Emits the same `G33R` grammar as the Fortran driver so one analyzer reads both, but
tags its algorithm `legacy-cpp`/`conservative-cpp`, so a mixed C++/Fortran set is
**rejected** by the analyzer's algorithm check rather than silently compared. The `k`
index is host-K (bottom-first) as the C++ tensors carry it, not the Fortran driver's
top-first convention; a cross-backend read needs the normalizer's flip.

## Not established

- No per-call entry-clamp digest on either side, so the Fortran entry path is
  argued about rather than measured.
- The mechanism behind the conservative call-boundary sensitivity is unidentified.
  The entry-cap hypothesis above was tested and refuted; no replacement is offered.
- Whether the `ni` mass/number measure mismatch is causal here is NOT established.
  It is the leading field and it uses the mismatched measure, but `nc` also carries
  a number measure, is interface-active in the same three cells, and is insensitive.
- The precipitation mechanism is unidentified in both experiments.
- The counterfactual operators still do not exist and still need a scoped
  freeze-lift.
- Synthetic fixture; no operational claim.
