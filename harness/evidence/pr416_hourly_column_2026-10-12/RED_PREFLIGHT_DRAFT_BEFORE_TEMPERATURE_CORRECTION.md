# Red preflight: PR416 selected hourly native column

## Disposition

**GO for the one declared read-only extraction.** The plan selects only the run-specific forecast child and the fixed native column at `j=103, i=48`, for indices 5, 6, and 7 corresponding to 05:00, 06:00, and 07:00 UTC on July 19. The geo check is against 36.195343017578125°N, 122.0966796875°E with absolute tolerance `1e-6` degrees. This review did not execute the extractor or open forecast state arrays.

## Source and plan checks

The final extractor SHA-256 is `3a858e6e60fd5efd870724250009c58d093f24c3043f144d696d3f28416e249e`; the plan SHA-256 is `aa76539dca47ec2e0097447b91e3016d061ade5e964c13ba1e1e1ac7f3b60465`. The plan's source receipt for the extractor matches its current bytes. The plan records `PREDECLARED_NO_COLUMN_READ` and outputs absent at declaration. The code refuses a second declaration or extraction if the plan or any output root already exists, then uses exclusive-create output paths and a one-shot read marker.

The chosen file is the run-specific child under the named MP137 term-parity run. The plan records the root-level file as a different inode and directs the reader to use only the child. It checks the child run identity and successful exit, MP137 namelist, all four rank completion markers, and the recorded terminal-parity pass. At execution, source receipts and forecast file stat must still match; the selected slices are read once, file stat and plan hash are checked again afterward, and there is no forecast write path. The 4.13 GB forecast itself is not fully hashed; this limitation is explicit.

The read contract distinguishes 3-D state/pressure fields, 1-D vertical coefficient vectors, 40-level interfaces, and surface scalars. It limits reads to one open file, saved indices 5/6/7, and the selected column; `U` and `V` use only the adjacent native staggered faces, while `W` remains on its 40 interfaces. Wind destaggering uses adjacent faces, and earth-relative rotation is performed only when both selected rotation scalars exist. The plan records the observed variable dimensions, shape, dtype, and units and the extractor revalidates them at execution.

## Arithmetic and preservation

The selected-frame helper promotes stored REAL(4) input slices to float64 for the native state arithmetic. It reconstructs `theta_m = THM + T0`, dry theta from `theta_m / (1 + (R_V/R_D) QVAPOR)`, Exner `PII = (P+PB)/P0` to the `RCP` power, temperature as `theta_m × PII`, and dry/moist density from the native pressure and temperature. The extractor records the native 39 center levels and 40 interfaces without remapping. Heights use `(PH+PHB)/g`; layer thickness is checked positive by the selected-frame helper. P8W comes from the hash-validated Python REAL(4) transcription, whose source checks finite strictly decreasing interface pressures; the WRF Fortran routine is not executed. Hydrometeor column mass is computed from the five mass mixing ratios times dry density and layer thickness, excluding number moments and QIB.

Each selected raw slice is checked for masked, fill, nonfinite, or wrong-shape values before conversion; values and boolean masks are separately retained, preserving source dtype for the raw arrays. The summary hashes the raw slice values. No H, M, RTTOV, optimizer, native forecast run, observation decoder, or temporal interpolation is invoked.

## Interpretation limits

This extracts a model-state diagnostic from a completed four-rank MP137 hourly run. It is separate from the retained one-rank PR415 local KDM optimization and does not make them a matched experiment. The run archive lacks an executable-byte digest and exact model input-file hashes, and the `wrfchainp_d01` `START_DATE` / forecast `Times` discrepancy remains unresolved. The final host boundary interval `[09:00, 12:00)` ends exclusively at 12:00 for further host advancement. Results from this selected-column read cannot establish observed cloud truth, process attribution, forecast skill, or host evolution after that boundary endpoint.
