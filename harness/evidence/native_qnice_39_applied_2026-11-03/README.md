# Same-call native 39-level QNICE applied ledger

This packet records one 20 s mp137 call on the native 5 km column `(164,242)`.
The executed research configuration selects `KDM6_ICE_FACTORIAL_MODE=norm_actual`
and `KDM6_QR_TRANSPORT=actual_departure`. It uses the native fp64 value bridge:
REAL4 host inputs are widened to binary64 before the selected C++ calculation.
The call identity is model step 3, rank 0, tile 2 (`i=2..233`, `j=143..281`),
`runtime_call=2`, `one_step_call=2`, `B=32248`, selected `b_zero=22617`,
and 39 native full levels. The ice sedimentation substep number is 1.

Run the offline verifier from the repository root:

```bash
python harness/evidence/native_qnice_39_applied_2026-11-03/replay.py
python -m unittest discover -s harness/evidence/native_qnice_39_applied_2026-11-03 -v
python -O -m unittest discover -s harness/evidence/native_qnice_39_applied_2026-11-03 -v
```

The CLI ends with `NATIVE_QNICE_39_APPLIED_REPLAY_PASSED`. It makes no host or
RTTOV call. The exact raw host and native CSV bytes, source snapshots, build and
run receipts, and saved numerical result are in this directory. The 32 MiB
legacy scalar capture is retained privately; its SHA-256 is
`fd2a239a480a728aebdbde2d2a3a982a949f4349eec2df4f094081f2211a58a5`,
exactly the hash of the earlier [verified two-level C5 packet](../native_c5_limiter_call_2026-11-01/README.md).
The verifier replays that packet and joins its two C3 NI words and ABI NI input
words to this call's selected levels. Private executable, DSO, full checkpoints,
input assets, and full scalar capture are attested by frozen hashes and private
run records; their bytes are not redistributed.

## What the numerical replay establishes

The host trace has 39 ordered f32 rows after `moist_physics_prep_em` and before
`microphysics_driver`. At every level, source-order f32 `1/f32(AL+ALB)` equals
recorded RHO. Host RHO/DEN, QV, and QNICE widen exactly to the C++ runtime
ingress words after reversing native bottom-first to sedimentation top-first
level order. The full-column ABI handoff itself was not separately recorded;
the prior C5 packet has ABI words for levels 21 and 23.

For the executed conservative ice substep, 25 fields are present at each of 39
levels. The replay checks the stored fall rate, actual departure cap, arrival
from the preceding level's **actual** departure, source-order NI state store,
and `fall_ni` accumulator store using raw f64 bits. All 39 selected gates are
active, no departure cap or depth floor is active, and bottom actual departure
is zero in this call. The capped branch is separately exercised by the private
39-level C++ build smoke recorded in `raw/cpp_build_receipt.json`.

| Native level | NI before sedimentation | Actual out | Actual in | NI after |
| ---: | ---: | ---: | ---: | ---: |
| 21 | 0.1376752108335495 | 0.0017857102530552098 | 40.591479729160824 | 40.72736922974132 |
| 23 | 116719.8203125 | 172.77053588541446 | 1.10466000736014 | 116548.15443662195 |

The numerical coordinate `Σ NI·DELZ` changes by approximately
`−2.3794033831152292e−11`. The maximum absolute adjacent-interface
departure/arrival difference is `3.0448629728674348e−12`; the exact-sum
arithmetic closure residual is `+2.6382586313862565e−11`. These are reported
separately from raw-bit state replay. `fall_ni` is a rate accumulator, so its
stored increment is not used in place of actual departure.

The C3-pre stage boundaries join at all 39 levels. D1, homogeneous freeze,
D2–D4, and snap B show no NI word change in this call. Snap A changes native
levels 25, 20, 19, 18, 17, and 16; its recorded `Σ NI·DELZ` difference is
`+49027.35812796282` in the numerical coordinate. This is a measured
before/after stage delta. The packet does not independently replay the snap A
coefficient formula or treat the delta as physical particle creation. Final
DSD number rewrite has no NI change in the recorded 39 levels.

A later [snap-A local replay and derivative packet](../native_qnice_snap_a_ad_2026-11-03/README.md)
independently checks the 39-level snap-A output formula and the selected
branch's conditional JVP/VJP. The stage delta above remains a numerical
coordinate quantity.

## Build and interpretation limits

The same attempt5 `wrf.exe` and DSO were used for capture-off and capture-on.
Their complete saved endpoint files both hash to
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`.
The private runner rehashed both files and checked the actual dyld-loaded DSO.
The public verifier checks the pinned run/session attestations and all
redistributed bytes. The historical C5 endpoint has a different file hash:
an [independent, pinned raw-bit scan](raw/historical_c5_compare.txt) found 650
of 652 variables equal, with 15 QNCLOUD cells and one RE_CLOUD cell different.
Its [receipt](raw/historical_c5_compare_receipt.json) binds the archived
[scan tool source](producer/strict_bitwise_nc.py.txt) and
both private endpoint hashes; the endpoint bytes are not redistributed. The selected C5 scalar stream
has the same SHA-256 in the two runs; full-domain historical parity is not
claimed. The origin-to-ready comparison also records one differing serialized
`WE_JUST_D01_LBC` element.

The first isolated build called the operational f32 ABI and failed the
actual-QR candidate's binary64 admission check. A later attempt captured
only stage snapshots because its hooks were on the inactive legacy ice path.
A third attempt recorded the executed conservative path but mislabeled the
global one-step call. Those failed/intermediate runs and their receipts remain
private and separate. The final attempt5 build uses the receipt-pinned
historical fp64 host wrapper and a separately pinned C++ DSO with corrected
call identity; the old source/archive, new host trace object, and new DSO
lineage are recorded in the receipts. The executable and DSO bytes are not
published here, so public replay verifies their attestation, not their binary
contents.

`scientific_status: INCONCLUSIVE` and `physical_unit_status: INCONCLUSIVE`.
Raw QNICE's producer/restart basis is still unverified. `Σ NI·DELZ` is a
numerical-coordinate diagnostic until that basis is established. This packet
does not validate physical particle conservation, an operational f32 run,
host JVP/VJP, or RTTOV sensitivity. The fixed-branch conservative calculation
and its captured f64 words are the scope of the arithmetic replay.
