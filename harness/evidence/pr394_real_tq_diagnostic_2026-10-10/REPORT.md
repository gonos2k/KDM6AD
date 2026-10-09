# PR394 one-column T/Q RTTOV diagnostic

This is a bounded integration diagnostic built from the cached selected-column
checkpoint associated with a failed host run. It is not a new valid native
case, an observation matchup, or a science acceptance result.

The pure preflight reproduced all cached `State_out_baseline_*` arrays
bitwise with one 20 s normalized-dry KDM step. It verified the native center
and interface pressure suffixes, frozen optical density, paired-case gas and
surface/geometry inputs, and exact full-grid RTTOV profile arrays. The direct
one-profile all-sky H check then emitted the declared 10–16 channel file,
preserved the declared p/p-half/T/Q arrays exactly, returned seven zero model
quality flags, and matched the saved baseline BT and Huber cost exactly:
`Jo = 26.588575903055926` and maximum BT difference `0.0 K`. The frame DQF
values and RTTOV model `rad_quality` are separate inputs and are not equated.

The one-iteration call to the existing `run_single_column_analysis` returned
`Jb_state = 0.02141671856035715`, `Jtheta = 0`, and `Jo =
26.45074405369286`; their sum, `26.472160772253215`, matches the final dual
closure trace. The final callback retained all seven frozen channels with
zero model quality flags. The returned state has a nonzero potential-temperature
(`th`) increment norm of `0.1383784 K` and an absolute dry-air mixing-ratio
(`qv`) increment norm of `7.9360e-5 kg kg-1`; every other state field stayed
fixed. These are state-coordinate norms, not physical-temperature or relative
humidity changes. The physical-temperature increment range/norm, relative-qv
min/max, final-slot liquid QC/NC state, and native RH were not persisted and
cannot be recovered from the saved norms and state hashes. The temporary
per-callback profile directories were cleaned up, and no KDM/H replay was run
to reconstruct those values. The configured prior used 39 potential-temperature controls and 12
water-vapor controls, with all other state controls and all four parameter
controls fixed at zero. The cached physical background was classified clear,
while the adapter routed the observation through all-sky H (`allsky_pos=[0]`,
`clear_pos=[]`).

The final record reports three non-`None` observation-evaluator results, two
window evaluations, one audit evaluation, and four captured logical H
outputs including the initial background probe. The separately evaluated
baseline H and the failed probes are not included in these final-analysis
counts. RTTOV executable launches and internal KDM call totals are not
instrumented and are left unknown. Two
earlier attempts reached the background probe and then failed in the local
capture wrapper when it treated `adj=None` as an array; they returned no
analysis. Other failed setup attempts were also retained beside the final
receipt. The final analysis driver passed `params=None` to the adapter, which
pins the default inactive parameter prior internally, while the separate pure
preflight used the equivalent explicit default to reproduce the cached state.

Tracked production source and immutable paired-case hashes matched before and
after the diagnostic. The baseline H and analysis used different hashes of
the local diagnostic driver because the H readiness checks were tightened
and an adapter-configuration/capture-wrapper issue was corrected after the
baseline H phase. These changes did not change the baseline H inputs or
production sources; both driver hashes are recorded in `RESULT.json`.
The driver-generated receipt had `accepted_state_published=true`; after the
run, that ambiguous metadata was replaced with `minimizer_returned_state=true`
and `valid_native_analysis_published=false`. `RESULT.executed_raw_reconstructed.json`
preserves a deterministic reconstruction of the emitted receipt, and
`RESULT.json` records the reconstruction hash and the fact that the original
write stream was not separately saved before postprocessing.

No WRF host/native case was launched, no RTTOV or KDM source was changed, and
the large forecast was not opened or hashed. The input remains the small
checkpoint from a failed 358-minute host run. This result does not establish
physical observation agreement, forecast skill, or a valid native analysis.
The adapter reports that p-half was passed unchanged; the separate preflight
verified its native interface suffix, while the adapter itself does not claim
an independent interface-grid identity check.

See [`RESULT.json`](RESULT.json) for the machine-readable evidence and
[`run_diagnostic.py`](run_diagnostic.py) for the staged, non-reusing driver.
