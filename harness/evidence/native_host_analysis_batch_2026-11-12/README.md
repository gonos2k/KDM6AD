# Saved host-column analysis and CI baseline (2026-11-12)

This packet recomputes three results using existing public evidence only. It makes **no new KDM, WRF host or RTTOV call**:

1. `full_output_fd.py` reads the exact archived #583 f64 interior JVP and six value-endpoint pairs. It reports 2,808 TH16-direction comparisons across two centers, three represented central-difference steps and 468 output positions. Each row retains raw words, absolute derivative error, declared per-field numerical scale error, output residual in f64 ULP and a resolved/equal-word classification. The scale source is an archived copy of `harness/verify_state_forcing_ad.py`; its numbers support numerical comparison, not physical-unit approval.
2. `f32_f64_diff.py` compares #580 operational f32 B=1 outputs with the rounded #583 f64 DA outputs for the **same exact-widened input**. The 101/468 differences are classified by field, native level and signed f32 ULP. This locates differences; it does not establish their production stage or cause.
3. `ci_timing.py` re-parses compressed public #583 GitHub Actions logs and job metadata, keeping suite-reported CPU/test time distinct from job wall time. The required Oracle job took 25m44s; normal and optimized serial evidence steps took 617s and 612s. Concurrent jobs are not summed as PR latency.

The [manifest](manifest.json) pins source scripts, derived JSON, the exact public CI logs/metadata and the archived field-scale source. [Replay](replay.py) recomputes all three outputs and checks the saved [summary](results.json). The two large per-row result files are deterministic gzip JSON. Run `python -m unittest discover -s harness/evidence/native_host_analysis_batch_2026-11-12 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.

Equal endpoint words remain unresolved, even with JVP=0. The 2,808 rows cover **one TH16 input direction**, not a full Jacobian or every process branch. The f32/f64 mismatch table is a comparison of two different maps. These analyses do not establish host-tile derivatives, physical budgets or GK2A–RTTOV cost sensitivity; `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
