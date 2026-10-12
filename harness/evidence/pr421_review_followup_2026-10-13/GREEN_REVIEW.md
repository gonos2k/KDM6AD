# Green review: PR421 follow-up evidence

Reviewed 2026-10-13 KST. The new packet contains only additive review artifacts;
the PR420 analysis plan, captures, numerical outputs and executed scripts were
not changed. No H, M, optimizer, native-model, or finite-difference calls were
made.

`DOM_EFFECTIVE_SETTINGS.json` reads all twelve retained DOM7/DOM9 call
directories and records `rttov_test.txt` and `channels.txt` hashes. All six
DOM7 cases write channels 10–16; all six DOM9 cases write 8–16. Every namelist
has `thermal_solver=1`, eight streams, zero DOM accuracy and optical-depth
threshold, with solar, `plane_parallel`, and `lambertian` options false and
`lambertian_fixed_angle` true. These are the configured values, not claims
about internal effective flags. I verified the distinction against the local
RTTOV v14 User Guide v1.1.1 and its official [NWP SAF PDF](https://nwp-saf.eumetsat.int/site/download/documentation/rtm/docs_rttov14/users_guide_rttov14_v1.1.pdf),
§8.4.2, Table 8.11, p.73: DOM1 is solver 1; RTTOV automatically applies strict
plane-parallel geometry for DOM even with the option false; DOM treats surface
reflection as Lambertian independently of that flag and ignores specularity.

`NUMERIC_REVIEW.json` uses only the public captures, channel table, and
direction result/plan. Per-channel Huber costs recompute to the captured
initial/final Jo values. On common channels 10–16, final Jo plus state prior is
6.3318615336 for DOM7 and 6.3335859423 for DOM9, a delta of +0.0017244087.
The added WV063/WV069 costs fall from 5.1948370201 to 5.1350736129; the
0.0597634072 reduction is 3.1859% of DOM9's total observation-cost reduction.
The two channels still make up 45.2477% of final DOM9 Jo. These figures do
not compare unnormalized whole-vector costs across channel counts.

The direction check's lower minus endpoint has Jtotal 11.4681507087; the plus
endpoint has Jtotal 11.4691694160. Recomputed central FD is 0.5093536529727771
against AD 0.5093536523613577; FD over the saved full-gradient L2 norm is
1.000000001200383. Both perturbation quality vectors are zero.

The graph update completed and contains a `recompute_pr421_review.py` node in
`graphify-out/graph.json`; the default HTML visualization was skipped because
the graph exceeds its 5,000-node limit. Ruff, JSON assertions, and
`git diff --check` pass. Numeric conclusions remain those of the diagnostic,
nonconverged PR420 returns; configured DOM flags are not misreported as
instrumented internal effective flags.

The saved full/prior gradient-norm ratio uses the CVT prior definition
`Jb = 1/2 ||v||²` in `oracle/kdm6/da_minimizer.py`; with `Jtheta=0`,
`sqrt(2 Jb)=0.4895737281`, versus full-gradient L2 `0.5093536524`. The
negative direction endpoint is lower than the saved return by `0.0005088465`
Jtotal, but it is a value-only diagnostic and does not replace or continue the
optimizer. The validation receipt records 55 related oracle tests plus one
legacy seven-channel synthetic-capture test. Public CI remains reported
separately.
