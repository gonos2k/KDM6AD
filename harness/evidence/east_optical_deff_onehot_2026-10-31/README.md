# Diameter one-hot optical direction, v1

This packet captures 16 private direct-only RTTOV calls and zero K calls. Offline replay makes no model calls and reuses the prior [K capture](../east_optical_derivative_2026-10-31/README.md) and [content one-hot packet](../east_optical_onehot_2026-10-31/README.md). For each of ten profiles at GG and PP, only HYDRO_DEFF slot 7 at zero-based layer 39 is perturbed, with content and cloud fraction fixed. The four h values are 0.0001, 0.0002, 0.0004 and 0.0008. Serialized endpoints define the actual direction. The prior hydro, deff and mixed directions plus the content and diameter one-hot directions have rank four per profile.

The preflight and inventories attest fixed content and fraction, positive content, and bounded diameter. The baseline preflight checks the known liquid-plus-ice content threshold of 1e-6; unchanged content preserves that predicate. Serialized endpoints stay on the same side of the 20 µm knot and inside 10–120 µm. Full atmospheric inputs are not redistributed: slot-level changes and threshold preservation remain preflight-attested, and no claim is made for other lookup branches. Layer 39 is not necessarily the lowest physical level.

The packet includes the locked runner, launcher, prepared pins, attempt, independent audit, 16 receipts, value arrays and raw radiances collected after execution. Receipts bind consumed input hashes, value archives and raw direct output hashes. The verifier checks each archived radiance against its receipt and requires the expected direct output inventory and an empty K output inventory; the other direct outputs are hash-listed but not redistributed. The public packet manifest also binds the archived files. The manifest is self-contained and requires authentication via a trusted revision. Paths in pins are historical provenance labels. Receipts cannot prove execution, linked library identity or authenticity.

Run with NumPy from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 harness/evidence/east_optical_deff_onehot_2026-10-31/verify.py
python3 -m unittest discover -s harness/evidence/east_optical_deff_onehot_2026-10-31 -p 'test_*.py'
```

The verifier checks raw TOTAL/BT/quality blocks and independently converts TOTAL to KMA BT using pinned public calibration. The bound is 64 binary64 eps × 300 K, allowing practical conversion rounding; FD replay uses the archived value arrays and requires bit equality. Each K·v is checked against an exact rational product with a gamma(2) binary64 roundoff bound, not a scientific residual tolerance. All 70 profile/channel differences are nonzero at each step. Relative L2 errors for GG are 9.259e-10, 4.754e-10, 9.592e-10, 3.592e-9; PP gives 7.403e-10, 4.018e-10, 1.043e-9, 3.961e-9, in increasing h order. These are measurements, not an acceptance threshold or plateau. They do not establish host-boundary, QNICE, process, cost, or higher-order derivatives.

The original summary SHA-256 is `f68a83e82c8e78f9aa593f29da8f0f2613680a781bf7ee5baab808306b55f57b`; the independent audit SHA-256 is `a53c4b92a847cd1519070fa09cc17b8a08aa1c862b1c623d4bf54f8f521f26c9`. The source manifest pins the verifier, tests and this README; authenticate it through a trusted revision.
