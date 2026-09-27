# S8: one in-host fp64 conservative AD call

The opt-in [host patch](../s8_fp64_host_probe.patch) leaves mp337's normal
`value_only=1` f32 forward call and host copyback unchanged. When
`KDM6_S8_FP64_PROBE` is exactly `1`, its first matching call copies one staged
column into a separate `(1,39,1)` fp64 state, invokes the PR #302
conservative-interface selector with a live handle, applies a `qi` direction,
then a VJP seeded by that JVP. It checks finite, nonzero results and closes the
handle to null. No derivative result is copied into the forecast state.

The patch applies with zero fuzz to the private source hashes
`0aef23e61cd0e1a31eda0d9213f48c838a119f0c8e0de6dcf1e8da76af6b55b3`
(`phys/kdm6_iso_c.F`) and
`940adce388dff58495710349a62a79dcc66506f3017cc089756d8f3992b7e9bb`
(`phys/module_mp_kdm6ad_cons.F`). Fresh application reproduced the two
executed source hashes `7b6c2b66038c2b0e3bca124df587a30698300bdc72b2d6b84640338cc33ea18e`
and `57fa9ea84a48f3e14dfc337dfd2dd6c48e8827a9cece89438570a8b80244e77c`.
Only these two Fortran objects were freshly compiled; the link map (SHA-256
`7f83487330a9fc370983572481d897ed9389f5f398a5d16a1c16fb4d8ea0f516`)
selects them directly ahead of the unchanged host archive. The linked PR #302 dylib
SHA-256 is `e644effe5c109988755502597c0b35a28dd42e74a6219882f70bb839d195a028`.

The retained 5 km mp337 case ran for 20 seconds with one rank and thread,
first with the probe off and then with it on, using the **same** executable
(SHA-256 `8bc3fc2e256e8a533f9c738c37aecc21904294cb1ea16a89ec2d37faa0d832ea`).
Both runs exited successfully and saved 0/20-second frames. All 254 common
variables, including `Times`, matched raw-bit in both frames; both forecast
files have SHA-256
`14dbf6067f552c2e1fbda3d8317f1492eb61639657e5f304bde0457a7d6837d2`.
The off run emitted no probe row. The on run emitted exactly one `S8HAD_v1`
row (private RSL SHA-256
`6eace50f7cdfacfdca8b41c5f633ccadbd815cb77191be7a8c75caf7c687ca09`).

That row identifies ABI 2, selector 1, `value_only=0`, the tile-2 global
column `(i,j)=(200,152)` and local `(199,10)`. It matches the earlier
captured ABI column's zero-based local `(198,9)`. The `qi` seed norm was
`2.3900326413e-3`; JVP and VJP norms were `5.7970017634e4` and
`1.1100355496e17`. The two dual products were `3360522944.4907460` and
`3360522944.4907455`, with relative difference `1.4189373680e-16`
against the declared `1e-10` limit.

An initial capture completed the model but emitted no AD row because it
mistook the capture-local indices for global `(199,10)` and required the
second tile's `JM=139`; that global cell was on the first `JM=141` tile.
A separate diagnostic call established the tile bounds before the corrected
control/capture pair. These failed or diagnostic attempts are not included
in the pass result.

This is a selected **in-host ABI call**, not host-wide derivative routing.
The probe uses fixed captured forcing and the existing discrete `mstep`
selection; it does not test finite differences inside the host, density
directions, physical number units, or observation cost. The production caller
still requests `value_only=1`. **S8 remains OPEN.**
