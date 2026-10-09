# Red: applied saturation-adjustment quantities in the cached partition study

This review uses only the earlier private value-only observer record and its cached selected-column checkpoint. It did not read or hash the forecast, call `kdm6_step`, run RTTOV, or modify physics. The selected native layer is WRF bottom-up `k=3` zero-based. The partition calls use constant forcing and fixed physical end time 20 seconds.

The observer directly saved, per saturation-adjustment call, `sw_percent`, the strict `sw_percent>0` gate, qv/qc/T entry and return values, NC/NCCN *volume* inventory entry and return values, `den`/`dend`, `xl`, and `cpm`. It did not record `pcact`, `pcond`, `ncact`, a pre-clamp NCCN value, or the complete-evaporation flag. The receipt does not contain those rates. The analysis script reconstructs them from the captured endpoints and the source equations, labels each as reconstructed, and checks that the reconstructed map reproduces the saved qv/qc/T endpoints within about `2.1e-17 kg/kg` and `5.7e-14 K`. Positive captured qc output at every stage rules out the complete-evaporation equality branch for this particular record; this is a case-specific source inference, not a general branch trace.

| Call partition | Call | Captured `sw_percent` | Reconstructed entry `qv−qs` (kg/kg dry) | Captured `dend` (kg dry air/m³) | Reconstructed `b` (m⁻³) | Reconstructed clip `C` (m⁻³) | Reconstructed `a` (kg/kg dry) | Reconstructed `c` (kg/kg dry) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 s | 1 | +1.662121616 | +2.97471622e-4 | 1.114659836 | 201,341,630.353 | 100,000,000 | 2.55360466e-6 | +7.99416212e-5 |
| 10 s + 10 s | 1 | +1.662121616 | +2.97471622e-4 | 1.114659836 | 201,341,630.353 | 100,000,000 | 2.55360466e-6 | +7.99416212e-5 |
| 10 s + 10 s | 2 | −0.039493793 | −7.15597339e-6 | 1.114750154 | 0 | 0 | 0 | −1.97096584e-6 |
| 5 s × 4 | 1 | +1.662121616 | +2.97471622e-4 | 1.114659836 | 201,341,630.353 | 100,000,000 | 2.55360466e-6 | +7.99416212e-5 |
| 5 s × 4 | 2 | −0.039493793 | −7.15597339e-6 | 1.114750154 | 0 | 0 | 0 | −1.97096584e-6 |
| 5 s × 4 | 3 | +0.000830541 | +1.50443399e-7 | 1.114747996 | 0 | 0 | 0 | +4.14442033e-8 |
| 5 s × 4 | 4 | −0.000017539 | −3.17693714e-9 | 1.114748041 | 0 | 0 | 0 | −8.75180417e-10 |

Here `a=pcact*dtcld` and `c=pcond*dtcld` are applied mixing-ratio amounts. Their rates were reconstructed using `oracle/kdm6/coordinator.py` and `satadj.py`; neither rate was directly observed. `b=ncact*dtcld` is the reconstructed coordinator-stage activation increment, in `m⁻³`. `C` is reconstructed as the source’s final NCCN clamp departure, also in `m⁻³`. At the first call, the strict supersaturation gate is on, the activated fraction saturates at one, and the rate cap makes `b` equal the entry NCCN volume number. `NCCN_in−b` is zero; the configured `NCCN_MIN=1e8 m⁻³` produces the `+1e8 m⁻³` reservoir departure. No later call creates another activation increment or another clip.

Equation locations: `oracle/kdm6/coordinator.py::apply_satadj_step_torch` lines 1972–2025 computes `sw`, the activation fraction/rate, pcact and the final NCCN clamp; lines 2027–2044 apply pcond and return. `oracle/kdm6/satadj.py::saturation_adjustment_torch` lines 71–96 defines `work1`, denominator order and signed pcond branches. `oracle/kdm6/runtime.py` lines 535–557 forms the dry-density number conversion; lines 608–622 set `dtcld` and the volume-coordinate NCCN entry clamp. The analysis mirrors these equations after the fact; it did not insert a new runtime observer or access internal rate tensors.

The 5-second third call is a useful boundary counterexample. Its `sw_percent>0` activation gate is true, but `sw_percent/0.48` is tiny and the source expression `max((NCCN+NC)*fraction−NC,0)` gives zero because NC already exceeds that fractional target. A positive activation gate therefore does not mean positive applied number activation. Gate histories are `[true]`, `[true,false]`, and `[true,false,true,false]`; applied `b` and the reservoir departure totals are the same in all three partitions: `201,341,630.353 m⁻³` and `100,000,000 m⁻³` respectively.

The common first call yields the same applied activation mass and condensation amount for all partitions: `a=2.553604662e-6` and `c=7.994162119e-5 kg/kg dry`. The `ncact/dtcld` and `pcond/dtcld` rates scale with `dtcld`; multiplying by `dtcld` cancels that division on this fixed first-stage input. Later calls see changed qv/qc/T and different saturation branches, so their signed `c` amounts differ. Cumulative satadj `a+c` is `8.249522585e-5`, `8.052426001e-5`, and `8.056482903e-5 kg/kg dry`, matching the observed final qc amounts for 20, 10+10, and 5×4 seconds. Cumulative qv/qc closure residuals are `1.87e-18`, `3.66e-19`, and `3.12e-19 kg/kg`; cumulative latent residuals using each captured `xl/cpm` are `−1.42e-15`, `−2.19e-14`, and `−8.55e-14 K`. These are only sums across the captured satadj stages, not a whole-step or host budget.

The external fixed forcing retains `rho_m=1.134940598 kg/m³` moist air, but `dend=rho_m/(1+qv_entry)` is recomputed at each outer `kdm6_step` call. Consequently the volume-number coordinates change between calls even before the next satadj update. The result records a density-only rebase estimate for NC and NCCN using `Nvol_next = Nvol_previous * rho_dry_next/rho_dry_previous`. For NCCN the observed next input matches that estimate to roundoff. NC has residuals after density-only rebase (roughly −1.60e3 m⁻³ after the first 10-second call and smaller later residuals); those are left unattributed because the cached observer does not capture all intervening processes. Do not telescope raw `m⁻³` number values across calls, infer an environmental CCN source, or interpret the volume-coordinate rebase as microphysical activation. State boundary numbers remain per kg dry air.

The generated [RESULT.json](RESULT.json) carries all seven calls, per-call captured/reconstructed fields, source and input hashes, closure checks and intercall basis-rebase residuals. `analyze_cached_partition.py` is an arithmetic reader of the cached observer and NPZ only. Reproduce it from this worktree with:

```sh
python harness/evidence/pr392_applied_partition_2026-10-09/analyze_cached_partition.py \
  --output /tmp/pr392-applied-partition-result.json
```

The script refuses to overwrite an existing output, does not open NetCDF or invoke KDM6, and labels reconstructed rates and quantities. The receipt includes no-universal-number-conservation/no-S17 limits. The original `20/10/5` endpoints remain partition-sensitive what-if results, not a timestep convergence-order test.

The initial canonical graph query found the coordinator satadj node but did not expose the applied-volume-number and intercall density-rebase details needed for this review; `coordinator.py`, `satadj.py`, and `runtime.py` source were checked directly. A scoped code graph (10 nodes, 26 edges) and semantic fragment (11 nodes, 11 edges) are under `graphify-out/pr392-red/`.
