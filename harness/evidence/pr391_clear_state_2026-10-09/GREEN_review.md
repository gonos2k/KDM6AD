# Green review — PR391 saved clear-state saturation diagnostic

Date: 2026-10-09. Scope: independently check the case_00 native-column thermodynamic diagnostic and the claims it can support. This is not a general PR review or a production-physics approval.

## Finding

No production defect is demonstrated. The focused evidence supports one bounded statement: the 39 native layers in archived RTTOV `case_00`, profile 001, are below water saturation and below the selected ice-branch saturation test using the KDM6 oracle's executed thermodynamic constants. The saved RTTOV hydro content and fraction are zero, while some effective-size parameters are nonzero. This establishes a clear baseline input for this case only; it does not explain the earlier native `exit 1`, establish forecast quality, or certify an analysis/optimizer result.

The diagnostic script independently loads `p.txt`, `t.txt`, and `q.txt` from the evidence archive rather than relying on copied profile values. Their 39-layer native suffix exactly matches the public enriched P/T/Q arrays. It inverts moist-air ppmv to dry-air mass mixing ratio with the optics writer's exact molar masses (`Mv=18.01528`, `Md=28.9647`, from [model_profile_builder.py](../../../oracle/kdm6/obs/model_profile_builder.py#L31)), then compares a separate NumPy transcription of saturation against the executed Torch routines and `default_thermo_params()` in [thermo.py](../../../oracle/kdm6/thermo.py#L58). The coefficient values are the oracle's f32-stepwise rounded defaults promoted to f64; NumPy/Torch maximum absolute differences are recorded in `result.json`.

The maximum native `q/qs_water` is **0.9553440633005558** at RTTOV layer 63 (1-based), native suffix top-down position 36 (1-based), WRF bottom-up `k=3` (0-based; Fortran `k=4`). There `q=0.018194574862718582 kg/kg`, `qs=0.019045049382375744 kg/kg`, and `qs−q=0.0008504745196571614 kg/kg`. At fixed pressure and humidity, the water-saturation root is **296.0134076624113 K**, **0.7354160849491223 K** below the saved temperature. The maximum `q/qs_ice` on the actual `T < ttp` branch is **0.43290235825739953**, at RTTOV layer 42 / WRF `k=24`, so the cold layers are also below this ice-saturation test.

The ratios are mixing-ratio ratios, not vapor-pressure ratios. At the water maximum, `e/es=0.956613697055035` when deriving `e` from dry mixing ratio with thermodynamic `ep2=Rd/Rv`; using the archived moist-air mole fraction directly gives `e/es=0.9562801499968837`. The difference is expected because the optics inversion's exact molecular-mass ratio and the thermodynamic `Rd/Rv` ratio differ slightly. The script reports both conventions and does not conflate them.

## Cross-checks and boundaries

- The PR391 structural graph is absent/incomplete for this private profile path; the available prior graph query exposed only the general humidity concept, not archive-to-builder/thermo dependencies. Source inspection and the pinned archive/public receipt therefore supply this review's provenance. No graph claim substitutes for the source checks above.
- The native forecast column at time `2025-07-19_05:55:40`, `j=86,i=48` (zero-based), reconstructs the archived native centers with maximum absolute differences of 0 hPa for pressure, 0 K for temperature, and `3.64e-12 ppmv` for humidity. This is a selected-slice comparison; the Red review owns the single whole-file before/after forecast hash.
- The saved RTTOV hydro inputs contain 0 nonzero content values and 0 nonzero fraction values. The effective-size input contains 78 nonzero parameters (range 0–10); size parameters alone do not imply hydrometeor mass.
- Applying `make_default_cvt` from [da_cvt.py](../../../oracle/kdm6/da_cvt.py#L206) to this saved column yields a **projected** 51 active controls: `th=39`, `qv=12`. Applying the recorded normalized/conserving `qv_levels=39` mask with mass-hydrometeor diagonal controls zeroed yields a **projected** 78: `th=39`, `qv=39`. The v10 report is from a separate 00:00 experiment, so these counts are not evidence of a case_00 optimizer run. The State/Fortran ABI `th` coordinate is potential temperature; [runtime.py](../../../oracle/kdm6/runtime.py#L346) forms physical KDM temperature as `th×Exner`, which is the native T supplied to RTTOV. The WRF `T` variable is a perturbation and is not the CVT `th` control.
- Zero hydro background plus `eps=0` pins direct hydro CVT rows. Active `th` and `qv` controls can still create condensate through KDM processes; no absence-of-indirect-creation claim is made.
- No KDM/RTTOV executable, optimizer, or forecast was run here. The retained [internal research checklist](../CHECKLIST_internal_research_2026-10-07.md#L21) remains the authority for these separate requirements:

| Requirement | This diagnostic provides | Current boundary |
| --- | --- | --- |
| R1: physical coordinates, thresholds, admissible states, density roles | Source-unit conversion and one saved column's q/qs context | Research choices and supported regime remain open |
| R2: valid observation to native model correspondence | Saved `case_00` P/T/Q and selected native-slice parity | QA, pixel time, footprint and valid target correspondence remain open |
| KDM→RTTOV derivatives and process budgets | None | JVP/VJP, directional differences, and named-process budgets remain open |
| T1: timestep dependence | None | Same-final-time 20/10/5 s study remains open |
| C1: multicolumn native-grid behavior | None | Multiple native columns and serial/worker agreement remain open |
| V1: unused validation separation | None | Eligible unused initializations/time sets remain open |
| BT/cost sensitivity and scientific outcome | None | No analysis, optimizer, KDM/RTTOV executable, or forecast run here |

Forecast skill and unattended cycling remain separate objectives, not gates imposed by this one-profile diagnostic.

## Reproduction and source identity

Run from the repository root with:

```sh
python harness/diagnose_clear_candidate.py --output graphify-out/pr391-green/clear_candidate_rerun.json
```

The run completed successfully twice. Its machine-readable output is [result.json](result.json). Inputs are pinned there by archive and enriched-JSON SHA-256, plus per-member hashes. Red's before/after whole-file forecast receipt is intentionally separate; this Green script reads only the selected NetCDF column.

Source checksums at review time: guarded diagnostic `diagnose_clear_candidate.py` SHA-256 `0263c51b0a1bf1275bec0e17e15725c37b603b9cb61d862be452fa800dec422f`; its prior executed source is preserved at `graphify-out/pr391-root/diagnostic_source_before_guard.py` with the recorded SHA-256 `d3bd737ca92ae44735e24df648240f226e6bcc95aa2a3868f4702f5b61539440`; `thermo.py` `5278c14c6d87178af5ee963eef59d3297b923fa374412fd854c01e43ffb1b5cd`; `da_cvt.py` `64a4826b3c6c3985a89e3d590ea61e53b1c62c3352254833c56e06a1a6099021`; `model_profile_builder.py` `b9264edb61f32010c025718ad59ef686746f156e2a3c011c473943fbf82788ab`. The later guards change input refusal/reporting behavior only; the existing result remained byte-identical and no calculation was rerun. These are inspection-time identities for attribution, not an endorsement of any changed production binary.

## Priority assessment

No P1/P2 production finding. The substantive remaining items are acceptance/evidence gaps tracked separately: choose a supported physical regime and coordinate/density roles (R1), bind a valid observation to native model state with QA/time/footprint evidence (R2), then complete the declared derivative/budget and numerical studies before making a science-result claim. Forecast/cycling, calibration, and bias tuning are separate choices rather than prerequisites imposed by this diagnostic.
