# S10 hybrid success actions: selected native 20 s pair

**S10 remains OPEN.** This opt-in mp237 run adds `S10HYACT` records to the existing midpoint plus exact-zero-rate hybrid. The records identify the executed branch and numerator at four `rhox` quotient consumers. They are bounded to the first step and three selected horizontal cells; they do not form a full-domain mass, volume, or heat budget.

The generated source keeps the physical stores in their existing order. Its logging-OFF and logging-ON runs used the same freshly linked executable, retained input, and effective namelist; only `KDM6_PROGB_VALIDITY_CAPTURE_LOG=1` differed. Both 20 s runs completed and saved 0 and 20 s frames. Their history SHA-256 is identical (`e0a54b63…257273ff`), and both frames match at raw-bit level. Each history has 253 finite numeric variables over 158,946,410 checked cells. The source generator's macro-OFF restoration and macro-ON/OFF syntax/object builds passed; strict byte identity of WRF-preprocessed macro-OFF `.f90` is not claimed. The [path-redacted receipt](S10_midpoint_rate_zero_run2/receipt.json) records the build and run hashes.

The ON stream contains 135 `S10HYACT` rows and no `S10HYFAIL` rows. The [selected raw rows](S10_midpoint_rate_zero_run2/S10HYACT_selected_rows.txt) are included so the branch and quotient checks can be repeated. Each row contains the seven-integer call key, consumer ID, action and density-assigned flags, then eight REAL4 hex words for pre/post `qg`, numerator, density, effective quotient, pre/post `brs`, and `dtcld`. The call key's `site` is the **latest ProgB producer call**, not a guarded consumer index.

| Consumer | Numerator meaning | Executed action | Rows |
| --- | --- | --- | ---: |
| `pgmlt/rhox` | Capped D1 mass **amount** | Nonzero division | 24 |
| `pgdep/rhox` | Process **rate** | Exact-zero bypass | 47 |
| `pgevp/rhox` | Process **rate** | Exact-zero bypass | 32 |
| `pgeml/rhox` | Process **rate** | Exact-zero bypass | 32 |

The logged effective quotient is zero on all 111 bypass rows. On all 24 division rows, the recorded numerator is nonzero, density is assigned and positive, and a separate binary32 division reproduces the recorded term. All logged numeric fields are finite. The public `test_selected_native_success_rows_replay` repeats these checks from the selected rows. These are checks of selected executed arithmetic, not approval of the 400 kg m⁻³ midpoint density.

One row is at the earlier seven-call witness `(j,i,k)=(2,142,17)` after **ProgB producer site 5**, at the `pgdep` consumer: `pgdep=0`, `rhox=0` with the density marked assigned, and the quotient is bypassed. In that stage-2 record `qg` changes from zero to `1.4233516709011296×10⁻¹²`, while `brs` changes from zero to `1.4233518352255213×10⁻¹⁵`. Other stage-2 terms contribute to these stores; the row must not attribute those changes to zero `pgdep`. No `S10HYACT` row was observed for this cell after ProgB producer sites 6 or 7.

The new capture closes the prior evidence gap about **which guarded actions actually executed in these selected cells**. It does not validate the full source-ordered mass–volume–heat budget, the physical number/volume basis, native-to-Python/C++ seven-call parity, transformed AD, or observation cost. The hybrid remains opt-in and the operational default is unchanged.
