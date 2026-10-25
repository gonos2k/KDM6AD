# Executed source and observability boundary

The native wrapper is the pinned `source_v2/harness/native_batch_microphysics.py`.
It performs native prep, one full-B C ABI call, outer cleanup, finish and EOS.
Parent baseline/three trial files came from source_v3; restricted source_v2
contains the parent-exact physics bytes with two orchestration/helper overlays.
The original B512 context is retained in every source receipt.

The isolated research DSO SHA-256 is
`5ef3b287cfff0a65e268f79d7f13f17540b5b477fcf647b3859ba61919ac0c99`.
Its build records archive-object reuse. The executed overlay coordinator is
`373e77cc9f81bd77603c6993a53cd8dfd5e9b3b401da6e102d90bc16028f280e`;
public d2ac976 coordinator is
`9253e1741cb8926f98fc088c56579a015472ea43b7ef0b365ef2c42bd2660152`.
They are not whole-file identical. A bounded source-text comparison of
`apply_satadj_step` through the next function matches, SHA
`44530a766de3617b26f503d60dbd162355d24af64a59bf0b2a571b803edde067`.
This text comparison supports a relevant code-path description; it does not
measure which activation branch executed. See [comparison receipt](cpp_source_comparison.json).

The bounded hash uses UTF-8 source bytes, starting at the first byte of
`CoordinatorState apply_satadj_step(` and ending immediately before the first
subsequent `CoordinatorState apply_threshold_cleanup(`, then applying byte
`strip()` to that bounded region (including its trailing section comment).
Internal whitespace and line endings are unchanged. For either pinned source file:

```python
source = path.read_bytes()
start = source.index(b"CoordinatorState apply_satadj_step(")
end = source.index(b"CoordinatorState apply_threshold_cleanup(", start)
assert hashlib.sha256(source[start:end].strip()).hexdigest() == (
    "44530a766de3617b26f503d60dbd162355d24af64a59bf0b2a571b803edde067"
)
```

The public side can be reproduced from `libtorch/src/coordinator.cpp` at
`d2ac976`; reproducing the executed-overlay side requires its pinned private
source. This public receipt does not bundle that private source.

Relevant source paths:

- `harness/native_observation_batch.py`: converts clean raw NC/NI using the
  same live dry density supplied to the optical bridge.
- `oracle/kdm6/obs/native_cloud_profile.py`: checks admissible QC/NC and
  QI/NI pairs; emits native layers in reversed RTTOV order.
- `oracle/kdm6/rttov_bridge.py`: uses the scheme's DSD preamble and radiation
  effective-radius factors; explicit dry-density content/number measures.
- `oracle/kdm6/cloud_dsd.py`: active cloud slope is exp(log(ratio) times the
  promoted f32 reciprocal of dmc); inactive qc/nc gates are separate.
- `oracle/kdm6/obs/model_profile_builder.py`: HYDRO6=QC content, HYDRO7=QI+QS;
  Deff and detached CFRAC limits. The target Deff endpoints are interior.
- Receipt-pinned overlay `coordinator.cpp::apply_satadj_step`: post-update
  CCN activation, pcact, saturation adjustment and NC/NCCN bounds.

For `s=100*(qv/qs1−1)`, the activation code uses a safe nonnegative power
and `f=min(1,(max(s/0.48,0))^ACTK)`, then a nonnegative activation amount
limited by available NCCN. It gates activation at s>0 and finally clamps NCCN
to its allowed range. Values here are the function's intermediate state,
not necessarily the saved kernel-entry T/Q. Entry or endpoint saturation is
not substituted for the unrecorded actual activation snapshot.

Candidate before/raw/clean arrays directly show QC/NC changes and QI removal.
Baseline raw NC/NI are retained in its applied-physics audit; baseline raw QC
is not. For positive above-threshold QC, raw=clean is source-inferred from
the outer cleanup identity. No baseline/trial raw intermediate snapshot is
invented. None of this identifies a unique microphysical rate or closes a
number, water or energy budget.
