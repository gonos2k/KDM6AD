# S10: native ProgB validity probe — P2 exposure confirmed; policy remains open

## Status

**S10 remains OPEN.** The canonical sources contain a source-level P2 definedness problem, and the bounded native probe confirms that affected consumers are reached in the selected LC05 run. `ProgB_param` declares `rhox`, `cmg`, and graupel parameters as `INTENT(OUT)`, while the active-moment branch does not assign every element. The subsequent `if (cmg>0)` is outside that branch, and `slope_kdm6` immediately consumes several returned parameters. The probe logs only assignment/reachability bits; it does not read or serialize an undefined result value.

**Measured physical impact of undefined outputs: not measured.** The logger's effect on the saved forward histories was measured separately and is bit-for-bit neutral in the bounded runs. No conclusion about the numeric value or forecast effect of an unassigned output follows from that check. No initialization, fallback value, `INTENT(INOUT)` retention, or other policy was selected.

## Source path and consumer map

The canonical private source files were read only. Their SHA-256 values are `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5` (`module_mp_kdm6.F`, operational mp37) and `4f0103c8a8321b8e854d3500f4ae567755e41eb78746fac54519eca2686a6648` (`module_mp_kdm6_cons.F`, conservative mp237). Each has seven `ProgB_param` call sites in `kdm62D`, each followed by `slope_kdm6`.

The categories recorded are assignment validity for `rhox`, `cmg`, `pidn0g`, and the table-derived bundle (`avtg`, `pvtg`, `precg2`, `bvtg*`, `rslopegbmax`, and gamma terms); reachability of the `cmg` test and immediate slope reads; selected `rhox` consumers in melt/deposition/evaporation tendencies; and the final diagnostic read. The native record stream shows 59 selected-column `cmg` tests and 59 immediate slope calls with unassigned producer prerequisites per variant, plus 192 reached unassigned `rhox` reads. The final selected-column diagnostic gate did not read an unassigned `rhox` in these records. These counts describe this bounded executed path, not whole-domain totals.

## Selection and actual call-time branches

The selected columns were chosen from retained LC05 5 km `wrfinput_d01` before inspecting native output. At Fortran `(j=73,i=113)`, input `QGRAUP` exceeds `qcrmin=1e-9` on levels 1–11 while input `QIB` is zero. At `(j=73,i=115)`, both input fields are zero on all 39 levels. The second column was therefore an **input-state inactive candidate**, not a guarantee that the later first `ProgB_param` call would remain inactive.

The call-time validity bits show why that distinction matters. On the first site/loop of both mp37 and mp237, the combined source gate is inactive at `i=115`, levels 1–3, and active at levels 4–11; it is inactive again at levels 12–39. At `i=113`, it is active at levels 1–11. The instrumentation records the combined predicate only; it does not determine whether QGRAUP or the bulk-volume mixing-ratio (`brs`) predicate made the `i=115`, levels 4–11 gate true. A prior replay assumption that all 39 levels at `i=115` would be inactive was rejected by the observed flags and is preserved as a probe-selection correction, not scientific evidence.

The active input sample has zero input `QIB`; this exercises a branch, not an admissible physical moment pair or a density-value validation. The trace scanner also found positive-qg, below-threshold call-time cells with the producer gate inactive: 763 paired trace producer/consumer records for mp37 and 771 for mp237 across the bounded step.

The `S10RHO` numeric `consumer_id` is a stable semantic tag, not a source-line claim for both variants. Its integer spellings match the mp37 legacy anchor locations; the manifest maps each to the current mp237 source location: `1418` pgmlt (mp237 line 1456), `2824` pgdep (2862), `2915` pgevp (2953), `2916` pgeml (2954), and `3027` pre-ProgB max (3065). The generator and replayer pin that mapping.

The event stream contains `S10CMG`, `S10PB`, `S10SLP`, `S10RHO`, `S10DIAG`, `S10SCAN`, `S10TRACE`, and `S10TRS` rows. The replayer requires an exact code-fixed eight-call-context × two-column × 39-level producer/cmg/slope key set, all 78 final-diagnostic cells, and the complete site-1 latitude census. Each variant manifest pins the event SHA-256, total rows, and per-tag counts, while the replay module independently hard-codes the matching SHA/count goldens. Thus a removed or relocated `S10RHO` row still fails when the manifest hash and counts are rewritten. Regression tests also remove a later site-2 paired producer/consumer key. Event fields contain only integer indices and validity/reach flags, never OUT values.

## Instrumentation and build

`make_progb_validity_capture.py` created separate macro-guarded shadow sources for mp37 and mp237. It pinned each current private-source hash and verified byte-exact recovery after stripping capture blocks. The logger is compiled under `KDM6_PROGB_VALIDITY_CAPTURE`; a single executable per variant ran both arms, with `KDM6_PROGB_VALIDITY_CAPTURE_LOG` unset for control and `1` for capture. Events contain integer flags and indices only, never a `ProgB_param` OUT value.

The Fortran source followed WRF's explicit preprocessing sequence: comment stripping, CPP with the WRF defines/includes, `tools/standard.exe`, then traditional CPP into `.f90`, followed by the recorded `mpif90 -c` command with `-ffp-contract=off`. As a recipe check, this sequence reproduced S5's retained `module_mp_kdm6ad.f90` SHA exactly (`6af670aa…`). Fresh S10 module objects were placed ahead of the unchanged canonical `libwrflib.a` using the retained explicit G4 linker argv. The build and executable paths/hashes are in the two native manifests. The canonical source, installed `wrf.exe`, `libwrflib.a`, and input set were rehashed and remained unchanged.

## Native runs and noninterference

Each variant used the retained real-data LC05 input, boundary, and chain files; `dt=20 s`; one MPI rank, one model thread, and actual `1x1` process grid; and `history_interval=0`, `history_interval_s=20`. Both arms saved exactly `2025-07-19_00:00:00` and `2025-07-19_00:00:20`. All four runner receipts have exit code 0 and `experiment_valid=true`.

For each variant, the control and capture used the same executable SHA, input identity, and namelist SHA. Their 606 MB history files also have identical SHA-256. `strict_bitwise_nc.py` reports **253/253 numeric fields raw-bit equal plus exact `Times` equality** (254 common variables total) for each logging-off/on pair. The capture has 5,662 records for mp37 and 5,678 for mp237. Both variants have 624 rows each for `S10PB`, `S10CMG`, and `S10SLP`, 212 `S10RHO` rows, 78 `S10DIAG` rows, and 1,974 `S10SCAN` rows; mp37 has 763 paired trace rows and mp237 has 771. The event-payload SHA-256 values are `63319cb1…878fd684` and `dc3d122f…eea922e0`, respectively.

## Excluded setup attempts and limitations

An initial mp237 source-selection invocation pointed the native ProgB generator at `module_mp_kdm6ad.F`; its pinned hash check rejected the wrapper before compilation. The correct native mp237 ProgB source is `module_mp_kdm6_cons.F`. A separate accidental `make -B -n` invocation without an explicit target expanded WRF's recursive main target and stopped at the missing `/external/ioapi_share` setup path. Its process group was terminated before any WRF executable ran. Post-attempt checks matched the pinned hashes for `module_mp_kdm6.F` (`fc0a72d3…`), `module_mp_kdm6_cons.F` (`4f0103c8…`), `main/wrf.exe` (`676223e8…`), and `main/libwrflib.a` (`722f83c0…`). No WRF executable ran; the setup incident is excluded from scientific evidence.

The output-meaning policy for inactive and trace graupel remains open. This one-step, one-case probe does not establish a numeric value, its physical impact, a safe fallback, all-domain validity, longer-run effect, or a policy for retaining state across calls. S10 stays OPEN pending an explicit validity/retention decision and any corresponding physical validation.

## Evidence files

- [mp37 native manifest](native_progb_validity_mp37_2026-09-25.json), [event flags](progb_validity_events_mp37_2026-09-25.txt), and [replay](progb_validity_replay_mp37_2026-09-25.json)
- [mp237 native manifest](native_progb_validity_mp237_2026-09-25.json), [event flags](progb_validity_events_mp237_2026-09-25.txt), and [replay](progb_validity_replay_mp237_2026-09-25.json)
- [prepared manifest template](progb_validity_manifest_template_2026-09-25.json)
- [source overlay builder](../make_progb_validity_capture.py), [record replayer](../replay_progb_validity.py)

The focused generator/replayer suite passes 10 tests. The completed replay results deliberately keep `undefined_output_physical_impact` as `NOT_MEASURED` and `physical_validity_policy` as `OPEN`. Graphify refreshed the structural graph and linked the replayer to its deletion-regression tests; LLM semantic extraction was unavailable because no Graphify semantic API credential is configured, so the report’s scientific interpretation is manually authored from the retained source and native receipts.
