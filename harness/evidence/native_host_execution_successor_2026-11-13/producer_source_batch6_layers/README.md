# Blocked batch6 source layers

`replay.py` applies four pinned source patches after the existing A5 packet:
77 files → 82 files for the separate condition-v2 record ABI → 83 files for
39 guarded named-tensor observation calls → 83 files with 45 more operand,
diagnostic-comparison and scalar-control record sites → 84 files with one
macro-ON synthetic parity CTest. Each step validates its input
inventory, patch paths and modes, and every output file SHA-256. The A5 packet
and the #593 parent remain unchanged.

`test_named_hooks.py` checks that removing the named observations restores the
v2 source byte for byte. `test_diagnostics.py` similarly recovers the named-hook
source and verifies the added diagnostic roles. The named hooks preserve existing
consumed Boolean tensors and named operands; the diagnostic comparisons do not
pretend to be source-consumed masks. Some comparisons repeat v1 hook work.
These sites are not a complete implementation of the 19 proposed mask groups.
Source reconstruction and synthetic CTests do not establish that
any hook ran on the native column or that a derivative or physical budget is
correct. The fifth CTest executes KDM on one synthetic B=1, K=39 f64 input and
compares capture-off/on raw state and same-call rain; it is a narrow value
noninterference check with no native host data.

The dedicated source CI builds separate macro OFF and ON configurations and
records exact exports, compiler flags and selected CTests. No registered
45-input batch or host/RTTOV run is authorized by this packet. The successor
remains `DRAFT_BLOCKED`; scientific and physical-unit statuses remain
`INCONCLUSIVE`.
