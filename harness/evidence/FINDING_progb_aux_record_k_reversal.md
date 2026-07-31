# The ProgB auxiliary was recorded reversed in k, and read as a divergence

Self-review finding. Withdraws the first protocol-v9 four-leg result and states
what the corrected run measures instead.

## What the defective run reported

The v9 four-leg run at `de15b35` returned `INCONCLUSIVE` with the first
divergence at `micro_call_progb_aux` — 58 of 228 cells, 18 of the 19 fields,
in both algorithms:

```
micro_call_progb_aux L1 col2 k0 rhox
  legacy_fortran        0x43fa0097   500.004608
  conservative_fortran  0x43fa0097   500.004608
  legacy_cpp            0x43fa0203   500.015717
  conservative_cpp      0x43fa011c   500.008667
```

Read at face value this says the ProgB bundle entering the microphysics already
differs, i.e. the seed sits upstream of the microphysics arithmetic. It does not.

## What it actually was

`_stage_block` emits the Fortran side at `k = kte-k`, so the dump is canonically
TOP-FIRST, and `runtime.cpp.overlay` wraps every whole-K record in `flip_k`
because the C++ working tensors are host-K (WRF bottom-first). The
`micro_call_progb_aux` records added in PR #92 read `pre2.progb.*` raw. Inside
the coordinator those tensors are host-K — the same file's §53d comment says so
explicitly when it flips the sed-era bundle *into* that orientation. Every
column therefore landed reversed in k.

Measured across all 114 `(field, column, loop)` blocks — both loops, all 19
fields, all 3 columns — `cpp[k] == fortran[kmax-k]` holds with **zero
exceptions**. Corrected, the bundle is bit-identical between the backends.

The clearest single witness was `bg`, whose four values in column 3 appeared in
exact reverse:

```
fortran  k0=0x2f4b200a  k1=0x30de598d  k2=0x313da060  k3=0x317395c8
cpp      k0=0x317395c8  k1=0x313da060  k2=0x30de598d  k3=0x2f4b200a
```

## Why the existing tests could not see it

Orientation is a *relation* between two independently generated streams; no
single-sided check has anything to compare against. And on this fixture only 10
of the 114 blocks even carry four distinct values — column 1 holds no graupel
(all zero) and column 3's `rhox` is pinned at the `rho_max` clamp, so both are
constant in k and read identical under either order. The whole signal was
carried by a handful of blocks.

`harness/tests/test_g33_overlay_orientation.py` now scans both overlays
uniformly and fails any whole-K record that is not `flip_k(...)`, an
already-top-first `*_pyc` member, or a broadcast constant. The `_pyc` suffix is
not taken on trust: the aggregates are checked to be all-`flip_k`, and a member
reassigned after construction must be listed with its justification.

## What the corrected run measures

`f3ff97d`, same fixture (`arithmetic_multisubcycle_v1`, manifest
`290ddce1…` — unchanged), same Gate A report, all four legs regenerated.

Fortran vs C++ differing cells, per stage and outer loop:

| stage | loop | legacy | conservative |
|---|---|---|---|
| `kernel_call_input` | 0 | 0/180 | 0/180 |
| `kernel_after_entry_clamp` | 0 | 0/180 | 0/180 |
| `outer_pre_sed` | 1, 2 | 0/180 | 0/180 |
| `outer_post_sed` | 1, 2 | 0/144 | 0/144 |
| `micro_call_progb_aux` | 1, 2 | **0/228** | **0/228** |
| `outer_post_micro` | 1 | 0/144 | 0/144 |
| `outer_post_micro` | 2 | 24/144 | 20/144 |

First divergence, both algorithms, same identity —
`outer_post_micro` loop 2, column 3, k 0, `qr`:

```
legacy_fortran        0x31974466        conservative_fortran  0x31974466
legacy_cpp            0x31974463        conservative_cpp      0x31974463
```

Both pairs carry the identical −3 ULP delta at the divergent cell.

## Structure of the loop-2 snapshot

All 24 differing cells are in column 3. At **k = 0 (model top)** the
Fortran→C++ delta is bit-identical in both algorithms for every prognostic that
differs there:

| field | k | legacy Δ | conservative Δ |
|---|---|---|---|
| `qc` | 0 | −84 | −84 |
| `qr` | 0 | −3 | −3 |
| `qs` | 0 | −6 | −6 |
| `qv` | 0 | +169 | +169 |
| `t` | 0 | +4 | +4 |
| `t` | 1 | +5 | +5 |

Below the top the two algorithms part: of 20 shared cells, 6 agree on the delta
and 14 do not, and 4 cells differ in legacy only. The top level is where the
conservative interface has no inflow from above to redistribute, so it has
nothing to change there; the levels beneath it are exactly where it does act.

## What this does and does not establish

It establishes that at the first divergent cell, and at every k = 0 cell of the
first divergent snapshot, the Fortran↔C++ difference is *bit-identically the
same* with the conservative interface and without it — the difference at that
point does not depend on the variant.

It does not establish where the difference originated. `_STAGE_MAJOR` runs
`micro_call_progb_aux` (7) → `outer_post_micro` (8) with **no instrumentation
between them**: the loop-2 microphysics rate chain (warm, cold, D5,
state_update) is a black box in this protocol. The seed is confined to that
chain, and localising it further needs op-level records inside it.

The gate returns `INCONCLUSIVE` accordingly. Attribution is owner adjudication;
the tool does not make a C4 claim.

## Superseded

- `harness/evidence/g33m_dt300_kernel_result.json` — already marked superseded.
- The v9 bundle at `de15b35` (first divergence `micro_call_progb_aux`) is
  withdrawn: the stage was mis-oriented, not divergent.
