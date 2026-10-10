# PR399 fixed native 3x3 direct-H comparison

This is a single direct RTTOV H batch on the nine already-saved native columns at frame index 1 (2025-07-19 05:56:00), with the same fixed AMI candidate geometry, seven channels, baseline quality mask, and observation cost for every row. The center result is reused from the hash-bound PR398 V2 execution because its complete saved input/profile/asset bindings match; only the eight neighboring columns required new H calls.

Result status: `ALL_NINE_ROWS_RETURNED`; result SHA256 `2bf488dca1a39f5c8d6fc19fd299a5a4de2560cfa083b98dc0bafd133f150422`; private NPZ SHA256 `4e2c36075e69d000bff48db8b2586ff1378adda3297508c58caa72b092e1c793`.
Center `(j=86,i=48)` reused with `Jo=26.5976847821` and all-seven rad_quality zero.

| j | i | latitude | longitude | all 7 quality zero | Jo (Huber K units) | max |ΔBT| from center (K) |
|---:|---:|---:|---:|:---:|---:|---:|
| 85 | 47 | 35.3676338 | 122.0898438 | True | 26.8011012031 | 0.1024257 |
| 85 | 48 | 35.3698502 | 122.1460266 | True | 26.5314165214 | 0.05135971 |
| 85 | 49 | 35.3720398 | 122.2022095 | True | 26.1407416552 | 0.1174473 |
| 86 | 47 | 35.4134407 | 122.0870972 | True | 26.7036937938 | 0.107046 |
| 86 | 48 | 35.4156609 | 122.1433105 | True | 26.5976847821 | 0 |
| 86 | 49 | 35.4178581 | 122.1995239 | True | 26.3582751199 | 0.1101141 |
| 87 | 47 | 35.4592476 | 122.0843506 | True | 26.1833334785 | 0.151865 |
| 87 | 48 | 35.4614792 | 122.1405945 | True | 26.254993623 | 0.1052263 |
| 87 | 49 | 35.4636765 | 122.1968689 | True | 26.1759997226 | 0.09199293 |

The full seven-channel BT vectors, per-channel `rad_quality`, state/forcing/density/pressure/surface/profile hashes, fixture asset hashes, and exact input arrays are preserved in the result JSON and private NPZ. If any row fails the fixed all-seven quality gate, its cost is withheld while the row and support remain present.

This comparison isolates each native column only under the fixed AMI geometry; BT and cost differences can reflect native State, pressure, density, and surface differences. It is not H(M(xb)), a footprint or parallax calculation, pixel-time validation, or science acceptance. The experiment made no M, optimizer, or native-model calls and had no retry path.

Attempt 1 failed in fixture preparation before any H call because the helper did not receive its O3/CO2 reference arrays; that immutable record is in [NEIGHBOR_ATTEMPT1_FAILURE.md](NEIGHBOR_ATTEMPT1_FAILURE.md). Attempt 2 preflight prepared all eight neighbor fixtures with pressure, interface pressure, temperature, humidity, O3, and CO2 vectors; the preflight receipt records zero H/M/optimizer calls. After independent Red clearance, the eight neighbor H calls completed once in serial order.

Postrun verification confirmed that all nine actual active profile files match the saved native+reference profile arrays, every surface file and geometry file matches the pinned writer inputs, and all nine costs recompute from saved BT, target, frozen mask, sigma=1 K, bias=0 K, and Huber delta=1 K. See [NEIGHBOR_POSTRUN_AUDIT_attempt2.json](NEIGHBOR_POSTRUN_AUDIT_attempt2.json), SHA256 `f8e3c941f57dc39faa72dc7b7c10bec2c4dfe5cdc2a458bfbf65d61da4c0636b`.
