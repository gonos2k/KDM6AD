# Serialized east optical directional evidence

This packet contains the finalized locked 50-process GG/PP experiment captures. Its verifier never calls RTTOV. Export again only from completed results using the **same pinned Python runtime**:

```sh
python export.py /path/to/east_optical_derivative_20261031 /new/path/packet
python verify.py /new/path/packet > /new/path/diagnostics.json
```

`export.py` requires the locked runner, launcher and prepared-manifest hashes, rechecks every recorded source/asset and runtime pin, all 50 captured case input inventories, baseline pins and receipts, then copies the captures into a new directory. It checks that copied bytes still match. The printed packet-manifest hash must be retained independently: a manifest distributed without an authenticated external digest cannot prove its own provenance. The packet contains 50 value archives and receipts, all 50 raw direct radiances, two raw K radiances and compressed K profiles, baseline archives, attempt and summary, preflight, runner, launcher and prepared manifest. The 528 external source/asset hashes are retained in the prepared manifest; assets are not redistributed. A partial export may remain on failure and must not be treated as evidence.

`verify.py` checks the inventory, SHA-256 hashes and lock constants; binds preflight and baseline captures to the prepared source manifest; checks the planned 48 direct-only plus two combined direct/K paths and per-case input receipt hashes; requires bitwise KMA BT agreement among the v7 preserved direct baseline, K-case direct and K radiance; then recomputes per-cell FD and K contractions for all three directions and four steps. It checks saved FD values bitwise. Saved and recomputed JVP and transpose-dot reductions are checked against an exact rational contraction of their fixed binary64 operands under explicit rounding bounds, and their replay differences are reported separately from the FD–K residual. Replay parses all raw radiances and checks zero quality in each of the 50 direct outputs and two K outputs. It also checks that native type-major slot-7 K multiplied by the saved same-run coordinate factor reproduces the saved K, and that raw K total radiance matches the saved total. It does not independently reconstruct KMA BT or phi-prime/psi-prime: those transformations and their use on the direct outputs remain attributed to the source-pinned runner and external calibration assets. Positive-cloud rows and fixed cloud fraction are established in the pinned preflight and input inventories; the verifier checks the selected rows, not an independent replay of all input edits. A receipt is evidence of what the pinned runner recorded, not cryptographic proof of process execution or the loaded external library.

### Portable arithmetic replay

The exact reference treats each saved K, perturbation direction and cotangent as
its binary64 rational value. For each JVP element the verifier checks the saved
and newly reduced values separately against `gamma(8) × sum(abs(products))`,
where `gamma(n) = n·2^-53/(1−n·2^-53)`. Each field has at most six nonzero
direction layers, giving at most one product, five additions and the final
cross-field addition on a term's path; eight is a conservative bound. It
rejects nonnormal nonzero products and RHS `cotangent × K` intermediates,
channel contractions and subsequent direction products. The two algebraic transpose sums use
separate `gamma(80)` and `gamma(670)` bounds on the exact cotangent-weighted
product sum, including their longer reduction paths. Tiny absolute allowances,
scaled by the direction where needed, cover gradual subnormal results. These bounds concern **replaying derived
binary64 sums**, not RTTOV K accuracy or the FD–K scientific comparison.
They assume nearest binary64 arithmetic and gradual underflow; a different
floating-point environment requires separate validation. Raw hashes, baseline
BT and saved finite-difference cells retain their strict checks.

The output is always `INCONCLUSIVE`: any acceptance threshold and a plateau require scientific review, and a zero/zero comparison is not evidence of agreement. The runner's transpose dot is an algebraic identity using the same K array, not an independent VJP. It does not establish a host-boundary, QNICE, KDM process or BT-cost derivative; ice units, actual external linked-library identity and upstream branch/budget interpretation remain limited. Native model fields and cloud fraction are held fixed except for the specified serialized active-cloud slot-7 perturbations. A pinned executable or Python extension does not by itself attest all dynamically linked libraries.

## Captured results

The exported `packet/packet.json` SHA-256 is `02b4d7efb574154480bc8b5e213d21f66905d7fb501880eb9b17de013eff230a`. Offline replay finds bitwise equality for both preserved v7 direct KMA BTs against each K-case direct and K radiance. All 70 profile/channel elements have nonzero plus-minus BT differences for every corner, direction and step. At h=1e-4, the maximum absolute FD–JVP residual across these cases is 6.995e-9 K per unit dimensionless direction. At h=1e-6 it ranges up to 5.548e-7; at h=1e-3 the diameter and mixed residuals reach 6.758e-4. These values show step-size dependence; they do not establish a strong plateau or physical branch smoothness. The source summary records algebraic transpose dot residuals, not an independent VJP.

An independent private audit was reported with SHA-256 `f6a74a72896837fb021bf653d0f30b6018d9e405a6ea25e7de7ab340409284cd`; it is not part of this replay or independently verified by it. The externally loaded RTTOV libraries, parameter units and upstream branch behavior retain the limitations above.

The pinned RTTOV hydrotable `rttov_hydrotable_gkompsat2_1_ami.dat` has SHA-256 `fdbe99ea68fd750e146fb78a798ab72b8568e4a3d545a2d847263cb374746890`. Its Baum ice diameter grid includes 20 µm. The archived preflight records all 42 GG active base diameters and 41 PP diameters as 20.020000000000003 µm; the remaining PP row is 20.020000000000007 µm. At h=1e-3, the deff and mixed directions cross that knot for all 42 rows per corner: their lower values are respectively 19.999980000000004 and 19.999980000000008 µm. At h≤1e-4 there is no 20 µm crossing. This provides a plausible explanation for the larger h=1e-3 discrepancy, not proof of its cause. The runner checked an input threshold and diameter bounds, not all RTTOV lookup branches. The h=1e-4 comparison likewise does not certify all branch behavior.

Raw output captures were hashed and collected **after** execution; the runner receipts pin the value archives and consumed input files, not these raw outputs at execution time. Their packet hashes detect later changes only relative to an authenticated packet-manifest digest, and do not independently prove execution-time identity. The shipped pins, runner and preflight contain absolute private local filesystem paths; review these paths before public distribution.

The sibling `source_manifest.json` pins the exact verifier, exporter, tests and this README. Both entry points check that fixed inventory before processing captures. The source manifest itself must be authenticated against the trusted Git revision; modified code can remove its own checks, so a self-check alone is not a trust anchor.
