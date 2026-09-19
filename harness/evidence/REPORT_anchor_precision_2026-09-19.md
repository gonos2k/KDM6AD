# Scene-anchor sensitivity and retained-output precision

## Contract

This follows PR221 without reopening its pressure or derivative-checker findings.
The same local 5 km column 45577, 39 model layers, explicit P/P_HALF, model state,
observation values, sigma=1 K, Huber delta=1 and zero bias are retained. No external
model or reanalysis data are used. These are selected first-order results under
scene-anchor geometry, not exact pixel navigation or independent atmospheric cases.

## Retained centre-anchor finite differences

The public [summary JSON](scene_anchor_precision_2026-09-19.json) records spacecraft
ECEF anchors, ellipsoid, target location, angle serialization and the actual BT
endpoint strings for both controls, seven usable channels and both epsilon values.
Run `python3 harness/replay_scene_anchor_precision.py` from the repository root to
replay geometry and Decimal arithmetic without private inputs or RTTOV.

For nearest-rounded endpoint text with increments q+ and q-, the text contribution
to the central-difference error is `(q+ + q-)/(4 epsilon)`. We distinguish the
observed AD–FD agreement from the stronger, text-only sufficient condition
`abs(AD - FD) + B_text <= 0.05 abs(AD)`. Neither condition bounds upstream floating
point error, finite-difference truncation or unrecorded branch changes.

For riming/WV073, AD is -2.980737509575238e-7 K/control. At epsilon .03, endpoint
strings 250.756881162 and 250.756881180 yield Decimal FD -3e-7. The stronger
condition fails: 1.8592915709e-8 exceeds 1.4903687548e-8. At epsilon .1, endpoints
250.756881139 and 250.756881199 yield the same FD, but the smaller text contribution
makes 6.9262490425e-9 less than the same threshold. Thus the retained .1 comparison
supports the text-aware 5% condition; .03 retains observed agreement only. No
physics, output precision, tolerance or QC rule has been changed.

## Shared baseline and additional calls

Deposition-alpha0 and riming-alpha0 have identical bytes in all 44 retained files:
including 22 profile/auxiliary input files, five direct outputs and nine K outputs. Their full saved baseline profiles, BT, K, quality and
mask agree. This permits reusing both saved profile tangent directions with a
single baseline direct/K evaluation at each additional anchor.

The anchor comparison uses `g_c = K_c v_process` and recomputes the Huber seed at
each anchor's BT before forming `dJ/dalpha = seed dot g`. It does not reuse the
centre cost seed, rerun the ten centre experiments, or claim a new direct-FD check
at the first/last anchor. Changed usable sets must be reported explicitly.

## Remaining scope

First/last scene-anchor spread is descriptive, not a navigation uncertainty bound.
Exact target-pixel acquisition timing, model-top/background-gas and bottom-boundary
sensitivity, representative process/column coverage, particle-number units,
nonzero applied transport and timestep convergence remain open. Single-column
RTTOV geometry does not construct a slant path through neighbouring model columns.

## Measured first/last comparison

The [anchor summary](scene_anchor_comparison_2026-09-19.json) includes all 16 BTs,
quality/masks, recomputed Huber seeds, channel tangents, field contributions and
input/output hashes. Seven channels remain usable; WV063/WV069 retain quality
32768. The valid copied input files differ only in the two exact satellite-angle
keys. Direct and K-run BTs agree exactly. Centre raw K parsing/cloud-slot mapping
replays the retained cost tangents exactly (channel differences <=2.61e-18).

| Anchor | Cost J | Deposition dJ/dalpha | Riming dJ/dalpha |
| --- | ---: | ---: | ---: |
| first | 20.511033272784854 | -0.013383490642655121 | -1.3201029757266893e-5 |
| centre (retained) | 20.511083910530242 | -0.013383672296319402 | -1.3201112415040182e-5 |
| last | 20.511136548239776 | -0.013383861100795374 | -1.3201198327021636e-5 |

Maximum absolute relative changes from centre are 0.001411% / 0.000651% for
cost derivatives and 0.000702% / 0.000537% for usable-channel derivatives
(deposition / riming). These quantify this recorded anchor choice, not a bound
on pixel navigation error. The IR133 Huber seed changes with BT; it is recomputed
at each anchor rather than reused.

Four calls were attempted: the first two were **rejected** because a temporary
script's substring matching also overwrote solar-angle keys. Review caught this
before publication. The corrected script compares exact unique keys and checks
all other values before executing two fresh cases. Only those two corrected calls
support this table. Rejected artifacts remain separately labelled locally.

Python 3.12 replay verifies three anchor geometries and 28 retained channel/width
comparisons: 28 observed agreements, 27 text-aware sufficient conditions. An
endpoint-mutation negative control fails. This arithmetic replay is not a fresh
KDM integration or full RTTOV reproduction; the two new direct/K calls use the
existing local runtime. No native build or complete oracle suite was rerun for
this evidence-only change. Graphify structural update completed; documentation
relationships were recorded by manual KG synthesis, not automatic semantic extraction.
