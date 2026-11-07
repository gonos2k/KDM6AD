# NC–NCCN applied-transfer ledger on the captured native column (2026-11-07)

This packet re-executes the **f64 C ABI value path** on the saved `(203,149)` native column (39 levels, 20-second call) from [the NC16 VJP packet](../native_nc16_vjp_branch_window_2026-11-06/README.md). It adds ten value-only capture fields around the activation, complete-evaporation return, reservoir clamp, cleanup and DSD stores. The C++ source is the #544 isolated source with these capture calls added; stripping the ten calls recovers the published #544 coordinator byte for byte. The published runtime and CMake source are also byte-identical to #544. This is **not a new private host or RTTOV run**, and this packet does not compute new C++ AD derivatives.

## Executed cases and noninterference

The run plan was fixed before execution: baseline; QV16 relative half steps `10^-3` and `10^-4`; TH16 absolute half steps `0.01` and `0.001 K`; NC16 relative half step `10^-4`; and the QG17+BRS17 joint relative half step `10^-3`. Each perturbation has plus/minus endpoints, giving **13 value calls**. Every call was executed twice in separate processes with the same isolated DSO: capture off and capture on. All four NPZ arrays (`state`, `forcing`, `xland`, `output`) are raw-equal in each pair and raw-equal to the corresponding saved #544 or #546 endpoint. The on capture has **14,001 rows**; removing the ten new fields × 39 levels recovers the corresponding 13,611-row parent capture in order, datatype and raw words. The run receipt pins hashes of the DSO, static archive, source, producer, logs, NPZ and each uncompressed capture. The private DSO/archive/object bytes are not in this public packet; their build and run hashes are provenance records, not an independent public rebuild.

## Applied numeric ledger

For each of 13 calls × 39 levels, `replay.py` uses the **captured** `ncact` rate and executed f64 operation order to reproduce, by raw bits:

1. `NC_after_activation = max(NC_in + ncact·20, 0)` and `NCCN_after_activation = max(NCCN_in − ncact·20, 0)`;
2. the complete-evaporation return `NC_after_activation·cloud_complete_evap`, the corresponding NC reduction and NCCN addition;
3. the NCCN reservoir clamp to `[10^8, 2×10^10]`, including its captured floor/cap decisions;
4. NC and NCCN through the satadj handoff, cleanup, DSD and packed output.

The exact-rational diagnostics separately calculate the activation pair's stored NC gain versus NCCN departure, the preclamp NC+NCCN roundoff, and the **reservoir adjustment**. They use the stored f64 words as exact rationals; they do not undo rounding incurred during the stores. Across 507 level-calls the maximum absolute activation-pair difference is `3.3760443329811096e-9` in stored numeric coordinates, and the maximum preclamp store difference is `8.745701052248478e-9`. These are numerical diagnostics, not a physical number conservation result. Ten levels per call have nonzero captured `ncact` and take the NCCN floor; no level takes the upper cap. Twenty-one levels per call have the complete-evaporation mask, but only three have a nonzero returned amount.

At native level 16 (`k_zero=23` in the top-first capture, packed index 15), the baseline has `NC_in=154080925.8395777`, `NCCN_in=100000000`, `ncact=5000000 s^-1` in the source's numeric convention. The 20-second activation increases NC by `100000000` and lowers NCCN to zero. The NCCN floor then adds `100000000` to its numeric stored coordinate, so final NCCN is again `100000000`. The floor contribution is **not** the activation transfer. At the negative QV `10^-3` endpoint, the applied departure is `70793393.23928493`, the post-activation NCCN is `29206606.760715067`, and the floor contribution is `70793393.23928493`. At the positive TH `0.01 K` endpoint, those values are `84086928.87507313`, `15913071.124926865` and `84086928.87507313`. The `results.json` file contains all 13 native-16 cases and per-call counts.

The replay checks the applied stores **conditional on captured `ncact` and evaporation mask**. It does not independently recalculate supersaturation, `activated_fraction`, `ncact_raw`, or every condition that produces the mask. The pinned #544 and #546 manifests and preserved parent rows connect to those earlier packets; their full arithmetic replays are separate tests. This packet also does not derive a JVP/VJP of the floor or claim that a zero captured rate has zero derivative. The tested active cells have nonnegative inputs; the evidence does not cover negative-state clipping or an active upper NCCN cap.

## Validation scope

The packet's default CLI pins every new raw, producer and executed-source asset with SHA-256. Test overrides accept rehashed capture or receipt bytes but keep parent capture, array, source and selected arithmetic checks; tests show rejection of a changed post-activation NCCN word, a changed floor flag, a false run direction/step claim and a wrong f64 datatype. The default CLI also compares parent endpoint array words and the 13,611 preserved capture rows with the parent packages. The original parent packets remain responsible for their own upstream production and branch claims.

This is a **conditional numerical NC–NCCN process ledger** for one native-state column through the isolated f64 C ABI. It does not settle the physical units or admissible moment relationship of QNICE/NCCN, the external aerosol source represented by the NCCN floor, NR source/sink attribution, operational f32 AD, whole-host sensitivity or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_nc_nccn_applied_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
