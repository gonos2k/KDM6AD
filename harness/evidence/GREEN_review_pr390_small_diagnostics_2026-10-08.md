# Green review: PR390 small diagnostics

Reviewed the fixed-candidate physical-questions note, the MPI control report and receipt, the short-host pair and state comparison, and the single-profile RTTOV packet and supporting receipts. The claims below are supported within their stated scopes.

## Demonstrated coverage

- The standalone Fortran controls exercised `MPI_Init`, `MPI_Finalize`, and `_Exit(0)` with and without the existing observer. The linked arms loaded the pinned historical KDM6AD and Python 3.10 PyTorch dylibs. Separate direct singleton runs returned direct-child wait status 0; `mpirun` arms report aggregate launcher status. This demonstrates observer forwarding on a control, not the historical WRF shutdown path.
- The paired 20-model-second host smoke completed normally without and with the observer. Both receipts report experiment validity, exit code 0 and a `1x1` grid. The observer arm records WRF `MPI_Finalize` entry/return with `ierr=0` and `_Exit(0)`. Both saved times are `2025-07-19 00:00:00` and `00:00:20`; the strict comparator reports all 254 variables bit-identical at each frame, with none skipped. This supports observer noninterference for this initial-time one-step pair.
- The RTTOV source audit identifies the 20 km⁻¹ total-layer extinction threshold and bit-15 quality value 32768, distinct from OD30. The instrumented diagnostic now measures actual trigger layers for the fixed saved profile: channel 8 layers 65–66 and channel 9 layers 64–66, with `ltick`, clear-sky base, total extinction before clipping and postclip values recorded. Category totals match, hydrometeor content/fraction are zero and aerosols are disabled, so the measured profile’s additional hydrometeor contribution is zero. Size parameters include nonzero entries. The outputs are evidence from a new isolated diagnostic build, not internal arrays recovered from the historical executable.
- The original and instrumented RTTOV outputs are byte-identical for the retained direct and K products on this one profile. The comparisons support instrumentation output noninterference for these calls and inputs. They do not cover other profiles, different aerosol or hydrometeor settings, internal arithmetic, or higher derivatives.

The candidate note was updated to cite the measured layer summary while retaining the historical-binary and individual-gas limits. The main report preserves the distinction between the short smoke and the invalid 358-minute run. The historical long-run termination cause, target-time validity, physical observation correspondence, and model cloud cause remain open. The zero-condensate model column versus nearby liquid VIIRS retrieval does not establish a microphysics, NC, ozone or sensor-bias cause.

## Provenance and review corrections

The MPI receipt now hashes the isolated native target’s `configure.wrf` rather than the canonical host file named by the earlier metadata. Its recorded `mpif90` flags match the isolated configuration’s `FCOPTIM` and `FCBASEOPTS`, with the project-required `-ffp-contract=off`; the linked arm uses its `LIB_LOCAL` libraries and `LC_RPATH` runtime. The runner hash and corrected configure hash are recorded. This correction was metadata-only; the executed controls were not rerun.

The tracked host-pair receipt enumerates each run’s `experiment_valid.json`, `run_identity.json`, and `input_sha256.json` paths and hashes. Its capture note records that the source-capture script and original scratch result stayed unchanged. Original executable, library, observer, harness and input pins match before and after.

The RTTOV diagnostic receipt records matching saved input hashes, the private instrumented executable/source/object/library hashes, the run status and raw-dump hash. Only the RTTOV Eddington setup object was rebuilt; other objects were hash-compared against the installed build. The original RTTOV executable and assets remain unchanged. Licensed source and raw arrays remain in ignored local output and are not represented in the semantic fragment.

The bounded Green/Red review found no remaining required production P1/P2 item in this scope. The Green pass closed the isolated-configure hash metadata mismatch and verified the host receipt-list correction; the candidate note’s earlier future-tense wording for actual extinction measurements was also updated to cite the completed profile diagnostic.

The bounded graphify semantic JSON contains nodes and explicit references for the candidate note, MPI report, paired host evidence, RTTOV report/summary, Green and Red reviews, and wiki source note. Its IDs and edge targets are unique and resolvable, and every `source_file` exists. It distinguishes measured MPI-control forwarding from the historical native termination cause, which remains unknown. Graph merge, cache and relationship review remain with the coordinating agent.

## Remaining limits

No evidence here explains the historical launcher exit 1 or repairs the failed target run. The diagnostic RTTOV build applies to one profile and does not attest that the original executable was built from the inspected source. Individual gas species were not separated. VIIRS retrieval QA, pixel UTC, parallax datum and common footprint remain incomplete, and no valid target-time independent-observation comparison or forecast-skill evidence is established.

No full pytest, native CI, legacy parity campaign, geometry replay, or Huber cost replay was repeated; production arithmetic did not change. The focused one-step output comparison and single-profile RTTOV comparisons cover the new evidence claims.
