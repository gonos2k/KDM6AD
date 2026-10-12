# Red preflight: opt-in nine-channel single-column analysis support

## Disposition

**GO for the bounded helper change.** The default channel tuple remains AMI 10–16. The only new opt-in set is AMI 8–16 in ascending physical-ID order; arbitrary subsets, permutations, non-integer IDs, and unordered containers are rejected before the model/observation path. No real H/M/optimizer call was made by Red.

## Helper review

`run_single_column_analysis(..., channels=None)` resolves to the original `_CHANNELS=(10,...,16)`; the new keyword is appended at the end of the signature. Explicit support accepts only the exact seven-channel default or nine-channel 8–16 tuple after sequence validation. The current helper requires an ordered `collections.abc.Sequence`, rejects strings/bytes, booleans and non-integer IDs, and rejects sets/frozensets/generators. Thus an unordered set cannot accidentally pass merely because this interpreter iterates small integer IDs in ascending order.

The selected physical-ID tuple controls observation shapes, exact `rttov_cfg.channels` equality, optional clear-config channel equality when present, `channel_gate` shape, frozen background support, and `channels_ami_physical_ids` metadata. The background must support every selected channel; any channel loss at a trial still raises under frozen support, with no channel dropping or support shrink. The all-sky position/routing, T/Q control projection, full-window adjoint, CVT, parameter prior, and optimizer remain the existing paths.

The prior PR394/default-seven caller explicitly configures both H and clear input channels as 10–16; it remains compatible with the unchanged default. If a clear configuration carries a channel list, it must match the selected set; the clear operator remains unused in this one-column all-sky route.

## Test review and bounds

The unchanged seven-channel synthetic tests still exercise default support, frozen trial quality, native 39-level shape, and the existing 51-control T/Q CVT. New synthetic tests cover nine-channel success, incomplete background quality, trial quality loss, source-quality support loss, mismatched clear channels, unsupported/permuted channel declarations, and acceptance of ordered lists/ranges. These tests use a synthetic H callback; they do not establish real nine-channel RTTOV quality or an analysis result. Root owns the separate actual nine-channel H calls and, only if all nine pass, the later nine-channel analysis.

The public API deliberately supports only the two established ordered spectral sets (10–16 and 8–16); it does not provide a general arbitrary-spectrum interface. This review does not change the frozen historical seven-channel records or establish any new scientific claim.
