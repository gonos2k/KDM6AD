# Native D1 snow/graupel slope producer into C++ AD (2026-11-05)

This packet extends the [same-call entry-preamble C++ packet](../native_d1_upstream_cpp_ad_2026-11-04/README.md) at native `(i,j,k)=(203,149,16)`, `runtime_call=one_step_call=2`. It uses the **same pinned 9,516-row native capture and the same retained static archive**. No new host or RTTOV run is asserted. The new isolated C++ executable calls actual `progb_param_torch` and `slope_kdm6_torch`, then `melting_torch`, `apply_melt_freeze_inline`, and postmelt `progb_param_torch`. Its input vector is D1-entry QV, T, QG, pre-reclamp BRS, P, and QS; QR, NR, QI, NI, DEN and DEND are separately fixed at their captured values. DEN feeds `denfac`; DEND feeds the slope mass coordinate and D1 melt denominator. They are not interchangeable derivative inputs.

The parent capture records the nine slope values **as D1-consumed operands**. It does not contain a separate tap at the native `slope_kdm6_torch` return. The public Python oracle recomputes all nine operands on the 39-level column from same-call input state and entry ProgB and agrees with all D1 operand words in raw f64 bits on the producing Mac/Torch 2.13 environment. The isolated C++ graph's nine slope outputs also agree with the selected native 16th-level D1 operand words. Its original 16 outputs remain raw-bit identical to the parent C++ graph and native capture, giving **25/25 raw-bit baseline outputs**. Cross-runtime Python math differences are reported separately from these exact captured/C++ anchors.

The connected snow/graupel fields are `n0sfac`, `rslope_s`, `rslope2_s`, `rslopeb_s`, `rslopemu_s`, and the corresponding graupel `rslope_g`, `rslope2_g`, `rslopeb_g`, `rslopemu_g`. In this parameterization `MUS=MUG=0`; `n0so` and `n0go` reduce to fixed `N0S/N0G`, so this graph keeps them fixed rather than claiming state-dependent intercept tangents. Entry ProgB produces `pidn0g`, `pvtg`, `bvtg`, and `rslopegbmax` for the graupel slope call. The local map still fixes QR/NR/QI/NI, density, other force inputs, later process rates, and the outer `entry_cpm` lifecycle.

## Selected conditional derivatives

Six directions are checked: QV, QG, pre-reclamp BRS, P, and QS as unit-relative perturbations, plus absolute T by 1 K. Actual C++ double-reverse JVP and C++ VJP weighted contractions are checked against the separately implemented Python producer chain, the verified 25-component JVP dot product, and represented-gap central differences. Every finite-difference endpoint is reevaluated by the Python chain; the same warm, open snow/graupel melt-cap, active snow/graupel slope, `n0sfac=1`, and entry/postmelt 800–900 ProgB branches are checked. The QG `+10⁻⁴` endpoint reaches the 900 density cap in **both** ProgB calls and is reported as a separate finite change, outside local JVP acceptance.

| Direction | Snow slope JVP | Graupel slope JVP | Applied snow melt JVP | Applied graupel melt JVP | D1 NR JVP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Relative QS16 | `+2.351988002986554e−4` | `0` | `−8.558393646484794e−5` | `+2.451360583150443e−7` | `−42.16896232241336` |
| Relative pre-BRS16 | `0` | `+6.0861029262814643e−5` | `0` | `−5.462740791691299e−6` | `+153.51762175873318` |

With slopes frozen in the parent packet, the pre-BRS direction gave graupel melt `+2.089838978561415e−6` and D1 NR `−37.659303955392076`. Recomputing the graupel slope changes both signs. This is the **conditional f64 map** with the other inputs above fixed; it does not identify a physical total derivative, forecast effect, or particle-number conservation. The local `relative_qg16` graupel-slope tangent is zero because the active ProgB intercept and QG scale together at this selected point; this does not mean the full graupel path is insensitive to QG.

## Provenance, replay, and limits

`raw/cpp_build_receipt.json` pins this C++ source and object/executable hashes, the prior native archive and slope object hashes, Torch libraries, Debug/assertion build, `-ffp-contract=off`, input capture, and output hash. The public replay checks these against the parent native build receipt and tracked slope source. The private archive, executable, object and full host checkpoint remain local; the receipt documents their linkage but public CI does not rebuild or rehash those private bytes. `raw/cpp_result.json` is the archived actual C++ execution output. The ordinary replay pins its SHA-256; `--output` is a test input whose supplied bytes are rehashed and then checked arithmetically.

The result is a selected one-cell, one-call **conditional f64 stage AD** check. It does not extend the packed C ABI, establish operational f32 or full subcycle AD, verify the outer QV→`entry_cpm` lineage, establish raw QNICE physical units, or connect host state to GK2A–RTTOV cost. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run the public suite with `python -m unittest discover -s harness/evidence/native_d1_slope_cpp_ad_2026-11-05 -v` and with `PYTHONOPTIMIZE=1 python -O -m unittest discover -s harness/evidence/native_d1_slope_cpp_ad_2026-11-05 -v`.
