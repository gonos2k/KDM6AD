# Serialized one-layer optical direction

This packet captures a follow-up to the [pinned baseline and K packet](../east_optical_derivative_2026-10-31/README.md). A private run made 16 direct-only RTTOV calls and zero K calls; this offline replay makes zero model calls. It reuses the prior GG and PP K captures. The pinned runner and prepared manifest, attempt, summary, all 16 receipts, value archives and raw direct radiances are included. Raw radiances were collected after execution; receipts bind values and consumed inputs, not these raw files. The manifest SHA-256 is `f1b7e41e18b12a7151beb82d0782b0dd2a3c35897421863c437002aa9ec26384`. Authenticate this digest independently; a self-contained manifest cannot prove its origin. Absolute private paths in the pins are provenance labels, not dependencies of replay.

For each of ten profiles and two corners, slot 7 is perturbed only at zero-based layer 39; that layer is not necessarily physically lowest. The saved plus and minus decimal strings define the actual direction `(plus-minus)/(2h)`, for h = 0.0001, 0.0002, 0.0004, 0.0008. Diameter, cloud fraction and other atmospheric inputs are fixed. The preflight checked positivity, cloud threshold retention and diameter bounds. The three prior directions contain two independent directions; together with the one-hot direction they have rank 3 in each profile. The verifier reconstructs rank and uses the serialized direction with the pinned K. Fixed input inventories and positivity are checked; the slot-level edit and threshold preservation are attributed to the captured runner and preflight because full input contents are not redistributed. The direct output configuration differs from the K case. No assertion is made that all RTTOV lookup branches remain unchanged.

Run from the repository root with NumPy and the prior packet available:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 harness/evidence/east_optical_onehot_2026-10-31/verify.py
```

All 70 profile/channel BT differences were nonzero at every step. Replay checks only the shape and quality of the raw radiance blocks; BT values used for FD come from the receipt-pinned value archives. Raw quality codes were zero. Maximum absolute FD–K differences and relative L2 differences are:

| h | GG max | GG relative L2 | PP max | PP relative L2 |
|---|---:|---:|---:|---:|
| 0.0001 | 6.1603e-9 | 6.4062e-10 | 4.2079e-9 | 4.9995e-10 |
| 0.0002 | 1.6040e-9 | 2.4118e-10 | 1.7941e-9 | 2.1077e-10 |
| 0.0004 | 1.1626e-9 | 1.4165e-10 | 1.1779e-9 | 1.2864e-10 |
| 0.0008 | 6.5411e-10 | 1.0174e-10 | 7.1469e-10 | 1.0621e-10 |

The comparison is in K per unit dimensionless direction. These results do not establish a plateau, a scientific acceptance threshold, a KDM process derivative, or an end-to-end cost derivative. KMA BT conversion and linked external assets remain attributed to the source-pinned execution, as described in the prior packet. Receipts cannot independently prove execution or dynamic-library identity. The independent private audit is separate from this public replay. The product replay compares both saved and recalculated K·v against the exact rational product of their binary64 operands using gamma(2) times the product magnitude plus one minimum subnormal. This arithmetic bound does not apply to the scientific FD–K residual. The source manifest pins the verifier, tests and README; authenticate it using the trusted Git revision.
