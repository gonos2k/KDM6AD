# PR #362 review follow-up: fixed-density forward AD

Change baseline: `4702099b7e0e8661890e57fe5f391f9b26c727a1` (PR #363).
This resolves the first-order P2 input-contract finding; it does not reopen the
successful PR #362 live-density calculations or approve physical policies.

- [x] Reproduce the forward/reverse discrepancy on the actual public helper.
  Python 3.13.7 / Torch 2.10.0, qv=0.02, rho_m=1.2, qc=1e-4 and dqv=0.0002:
  fixed-mode JVP leaked -2.306805074971165e-5 g/m³ per direction, while reverse
  AD rejected the live density. The profile-level zero-dual regression also
  failed before the guard change.
- [x] Reject both reverse gradients and forward duals in `live=False` using
  public `forward_ad.unpack_dual`. A zero tangent is still a carried dependency.
  Reject the input; do not silently detach it. Return the original tensor for
  valid fixed inputs and explicit `live=True`.
- [x] Verify rejected zero/nonzero forward tangents, preserved live-density
  content JVP, and a frozen constant with state JVP. Reuse the existing reverse
  rejection test and existing entry-density/optical regression tests.
- [x] Preserve entry-qv selection, all six optical fields, 17-digit RTTOV output
  and existing finite-difference criteria. No physical arithmetic or ABI change.
- [x] Green/Red review of consistency, false positives and derivative coverage.

## Focused execution

Python 3.10.11 / Torch 2.13.0: **29 passed**, 18 existing TorchScript warnings:

```sh
python3 -m pytest oracle/tests/test_cloud_density_contract.py \
  oracle/tests/test_entry_density_optics.py oracle/tests/test_dry_number_optics.py \
  oracle/tests/test_rttov_bridge.py -q
```

Python 3.13.7 / Torch 2.10.0: **34 passed**, 18 existing TorchScript warnings,
using density, entry-density, RTTOV bridge and model-profile-cloud test files.
These overlapping suites are not summed. They use public fixtures/synthetic
AD inputs, not new native/RTTOV runs or new meteorological cases.

The fixed-measure guard applies to supported first-order AD. Under nested
`torch.func.jvp`, an inner transform may hide an outer density tangent from
`unpack_dual` at the current level. Nested/higher-order transforms remain outside
the RTTOV-K/DA contract; this change does not certify or silently expand them.

The implemented check follows the public [unpack_dual API](https://docs.pytorch.org/docs/2.14/generated/torch.autograd.forward_ad.unpack_dual.html).
[no_grad](https://docs.pytorch.org/docs/2.14/generated/torch.no_grad.html) does not disable forward AD.

Original 100/10 calibration and AMI physical/error-policy approval stay OPEN in
[the scientific checklist](CHECKLIST_pr361_followup_2026-10-03.md). No deployment,
new atmospheric data, native re-certification or full DA-window claim is made.
