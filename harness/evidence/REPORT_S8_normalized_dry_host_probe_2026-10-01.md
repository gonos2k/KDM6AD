# S8 normalized dry-number probe inside mp337

The selected host fp64 probe now uses **selector 2 / dry-number 1**, matching
the physical options of its normal f32 value-only forecast. The
[standalone patch](../s8_normalized_dry_host_probe.patch) adds the AD-number ISO
binding and probes one staged column before the value-only call. It requires
both `KDM6_S1_NORMALIZED_ICE=1` and `KDM6_S2_DRY_NUMBER=1`; its own gate is
`KDM6_S8_FP64_PROBE`, strictly unset, 0 or 1. No forecast copyback uses AD output.

Apply to an isolated S1/S2 native source snapshot identified by the
[receipt](native_selector2_dry1_ad_probe_2026-10-01.json), using `patch -p1` from
the snapshot root. This standalone patch targets the semantic call boundary.
Stacking the old position-based S8/S2 patches against this changed wrapper
produced a rejected composition; that attempt was preserved and never compiled
or run. The final patch applies and reverses to the pinned base exactly.

Fresh ISO/wrapper objects retain `-ffp-contract=off` and precede the unchanged
host archive in the link map. The library is the same freshly built fp64 ABI
artifact used by the external-path column command. The corrected probe reads
JV/JTU only after successful calls, with nested status guards; its earlier
version and runs are preserved separately. The corrected source was rebuilt
and both native runs repeated. Canonical host sources and installs were not
modified. This is not a complete host rebuild or historical-source reapproval.

| Corrected-source execution | Evidence |
| --- | --- |
| Same executable OFF/ON | Both complete 40 s, dt=20 s, one rank/thread, actual 1x1 |
| Forecast noninterference | 254 common variables including Times match raw-bit at 0/20/40 s; whole forecast hashes equal |
| Energy output | Five variables match at both saved frames (0/20 s) |
| Probe event | OFF: zero; ON: one at global (200,152), dimensions (1,39,1), ABI 2, value_only 0 |
| Probe map | physics_variant 2, dry_number 1; entry qi plus 1% qv/nc direction |
| JVP/VJP | Finite/nonzero norms; u=Jv relative duality 4.3721970729e-16 |

MPI remained local: en0 was inactive, so both one-rank runs pinned TCP and OOB
TCP to loopback lo0. There is no multi-rank or active-en0 claim. Precipitation
and ocean streams had zero saved frames and supply no numeric comparison.

The reviewed selector-1-AD/selector-2-forward availability gap is closed for
this one staged native column. f32 and fp64 remain distinct numerical maps;
duality is self-consistency, not independent derivative accuracy. The separate
[offline column FD failure](REPORT_S8_same_candidate_column_2026-10-01.md) remains
open, as do general DA routing, physical units/thresholds, initialization
derivatives, whole-host nonnegativity and observation approval. S8 stays OPEN.
