# F5: measure-aware dual work pairing on a synthetic complete overlap

The verification-only `dual_work_mapping_contract.py` composes X6's checked
`OverlapRemap` with a dual force-density relation. Source/target cell measures
are declared in `m²`; source and target velocity are in `m/s`, force density
in `N/m²`, extensive force in N, and their pairing in W. The full-coverage
pilot requires

```
v_t = P v_s,             P 1 = 1,
P^T w_t = w_s,           g_s = W_s^-1 P^T W_t g_t.
```

The last relation uses the **same target extensive force** `W_t g_t` to
construct the source extensive force `W_s g_s`. It implies both total-force
and power identity for this declared map:

```
sum(W_s g_s) = sum(W_t g_t),
v_s^T W_s g_s = v_t^T W_t g_t.
```

For the synthetic two-by-two map `P=[[1,0],[0.5,0.5]]`, measures
`w_s=[2.5,1.5] m²` and `w_t=[1,3] m²`, source velocity `[2,4] m/s`
maps to `[2,3] m/s`. Target force density `[5,2] N/m²` represents
`[5,6] N`. The dual source force is `[8,3] N`, so each total is **11 N**
and each power is **28 W**. A wrong source force `[10,1] N` keeps the
same 11 N total but gives **24 W** and fails the dual-map gate. Constant
velocity and constant force density also remain constant under the declared
measure identity; signed fields retain the pairing.

Six new test functions and the retained parameterized X6 overlap tests
produce 17 passing cases with warnings treated as errors; Ruff passes. The
pilot requires unmasked finite float64 arrays and fixes a `1e-12` relative,
zero absolute comparison for mapped values. It is limited to complete
overlap and one specified nonnegative linear P. It does not certify partial
coverage, nonmatching real model meshes, actual mechanical work, or a host
coupling trajectory. X6's separate partial-overlap integral check remains
in force; F5 adds the dual intensive/extensive pairing that X6 did not test.
