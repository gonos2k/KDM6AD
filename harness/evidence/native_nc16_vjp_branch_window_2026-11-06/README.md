# Native NC16 output-seed C ABI VJP (2026-11-06)

This packet uses the **same captured `(203,149)` column, 39 levels and 20-second f64 call** as [the selected full-state AD packet](../skipped_substep_ad_2026-11-05/README.md). It reuses the isolated DSO identified by [the branch-trace build receipt](../native_fd_outlier_branches_2026-11-05/raw/build_receipt.json), with capture environment variables disabled. The run performs a new C++ C ABI graph-forward, JVP and VJP; it is **not** an AD call inside the historical host executable. The state forcing, xland, timestep, physics variant and one-thread environment are fixed to the retained call. Operational f32 AD, physical QNICE units and GK2A–RTTOV cost sensitivity remain outside this evidence.

## Seed, output and independent directions

The packed state order is `(th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg)`. Reversing the native capture's K rows `38..0` puts native level 16 at array index 15. The one-hot **output** cotangent is `u[NC=8,K=15]=1`, packed offset **327** in the 468-element one-column state layout; every other seed word is raw `+0`. The C++ graph and value-only forwards both match the captured native 12×39 exit state in raw f64 bits. The new QV16, QS16 and QG16 JVP arrays and input directions match the earlier saved C ABI arrays in raw bits.

The resulting VJP is finite in all **468 input coordinates**. Three selected relative input projections are:

| Relative input direction | NC16 C++ JVP | `VJP·direction` | Branch-aware independent FD |
| --- | ---: | ---: | ---: |
| QV16 | `-112.9934654754613` | `-112.99346547546132` | `h=10^-4`: `-112.9935681819453` |
| QS16 | `-50323449.70132754` | `-50323449.701327555` | `h=10^-4`: `-50323449.81667616` |
| QG16 | `+363038.5297350049` | `+363038.52973500476` | `h=10^-6`: `+363038.5249984018` |

For wider **same-graph transpose coverage**, the producer also called the C ABI JVP for each of the 468 unit input directions and retained its NC16 scalar output. Comparing that 468-element coordinate JVP map to the one-hot-seeded VJP gives a maximum `|JVP−VJP|/max(1,|VJP|)` of **`9.270351824068155e-16`**; 13 cells differ in their final raw f64 word. This checks every saved VJP component against a separate JVP call on the same graph. Independent finite differences cover only the selected QV16, QS16 and QG16 directions, not all 468 input coordinates.

## Finite-step branch windows

The prior [branch trace](../native_fd_outlier_branches_2026-11-05/README.md) establishes that QV relative `h=10^-3` crosses the cloud activation-fraction cap at the negative endpoint, and QG `h=10^-5` crosses the entry ProgB graupel density cap at its negative endpoint. The replay retains their central secants as **branch-crossing finite changes** and excludes them from local derivative acceptance. QV `h=10^-4`, QS `h=10^-3,10^-4`, and QG `h=10^-6,10^-7` pass the selected NC16 FD–JVP normalized bound `5e-6` using the represented input gap. For QS, only the parent packet's recorded masks/schedule are checked, so this is not a proof that every internal branch remained fixed. QV `h=10^-5` stays on the captured activation cap but has a normalized NC16 FD–JVP residual `2.151e-5`; it corresponds to **1.631 output f64 ULP** at the represented gap and is reported separately.

## Provenance and limits

`manifest.json` pins the producer source, result arrays, run receipt/logs, the exact private C ABI bridge source/header and `State::fields()` header, and the bridge compile flags. The [post-run bridge attestation](raw/bridge_attestation.json) records its private object, archive and DSO hashes. Public replay matches the bridge snapshots and flags to that attestation and the parent DSO receipt; the bridge object and DSO bytes remain private and are **not independently rebuilt or hashed by public CI**. The saved receipt records C ABI return codes, handle close and one-thread variant controls. Rehashed mutation tests exercise the one-hot seed and an otherwise untested VJP component against the full coordinate JVP map.

The result is an **NC16 output-seed state VJP on one conditional f64 call**. A 468-coordinate JVP transpose sweep is an internal same-graph check; the selected FD comparisons provide the independent directional evidence. This does not establish arbitrary output seeds, forcing or parameter adjoints, a full host Jacobian, operational f32 differentiability, physical number conservation or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_nc16_vjp_branch_window_2026-11-06 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
