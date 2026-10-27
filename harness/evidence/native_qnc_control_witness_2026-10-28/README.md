# Same-level control witnesses for 54 QNC/QI failures — 2026-10-28

This versioned companion reads the **existing** variant-control final checkpoint at the same native cells and levels where the historical alpha0.25 candidate failed. It preserves the [PR #466 READY/final packet](../native_qnc_host_backoff_review_2026-10-28/README.md) and [PR #465 support packet](../native_qnc_host_backoff_2026-10-27/README.md) unchanged. The [value-only producer](../../native_qnc_control_witness_producer.py) pins both prior public assets and the private control checkpoint SHA before recording raw f32 moment words. No host, KDM6, RTTOV or optimizer call was made.

## What the same-level comparison shows

| Final alpha failure | Native levels | Same levels in variant control |
| --- | ---: | --- |
| QC>0, NC=0 | **54 levels in 53 profiles** | **QC>0, NC>0 at all 54** |
| Tiny QI>0, NI=0 | **1 level in 1 profile** | **QI=0, NI=0** |

Control therefore resolves every selected profile's hard moment inconsistency. For the liquid failures, it does so through **positive NC at the same QC-positive level**, rather than by making QC zero. The ice witness at native `(i,j,k)=(1,168,33)` instead has a subnormal QI residue in alpha (`00000002`) and zero QI in control. Raw NC/NI physical units remain uncertified.

Among the 29 profiles that were valid at **pre-command READY40** and invalid at the candidate endpoint, 27 changed from QC>0/NC>0 to QC>0/NC=0 at their final failed layer. The other two changed from QC=NC=0 to QC>0/NC=0. Each of these 29 has exactly one final failed liquid level. The two zero-to-cloud witnesses are `(155,120,15)` and `(152,268,11)` in native one-based coordinates.

READY and final failed-layer locations also differ within some of the 25 profiles already invalid at READY: **20 layers fail at both boundaries, eight READY failure layers resolve, and 35 final failure layers newly fail**; five profiles have no overlap at all between their READY and final failed layers. These are layer incidences, while 25/29 are profile counts. The final liquid failures cluster at native `k=4` (21 of 54 layers, including 15 of the 29 newly invalid profiles).

## Replay

```sh
python3 -m harness.evidence.native_qnc_control_witness_2026-10-28.replay
```

The replay verifies the immutable PR #465/#466 packet manifests and assets, current source pins, and the per-level raw f32 words in [control_witness_rows.json](control_witness_rows.json). It recomputes the category, overlap and vertical counts and reproduces [analysis.json](analysis.json) byte for byte. The public packet retains the control values at selected levels, not the full private NetCDF checkpoint. The producer's full-profile validity check and control checkpoint SHA are source/input attributed; the public replay cannot independently reconstruct unexported control levels.

This evidence narrows where to instrument next. It **does not** prove whether each NC loss or QC appearance occurred in transport, scalar boundary processing, KDM, or a later host operation. It does not establish a general one-ULP rule, whole-domain physical number conservation, a valid fixed-M0 candidate objective, or a second assimilation.
