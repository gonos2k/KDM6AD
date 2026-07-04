---
title: KDM6 Microphysics Zotero Survey
instance_of: Source
page_kind: source-page
date_ingested: 2026-06-25
epistemic_status: observed
provenance:
  sources:
    - /tmp/zotero-kg-kdm6-microphysics-survey
---
# KDM6 Microphysics Zotero Survey

## Summary

This page ingests the Zotero tag `kdm6-microphysics-survey` as a research source set for [[KDM6]], [[KDM6AD]], and differentiable bulk microphysics paper planning. The staging folder contains 30 Zotero-exported markdown files, of which 24 include abstracts and 6 are metadata-only. The analysis below is therefore abstract-based, with lower confidence for the metadata-only entries.

The literature does not yet frame KDM/WDM-family bulk microphysics in automatic-differentiation terms. Its strongest contribution to [[KDM6AD]] is the design space it exposes: number-concentration prediction, CCN/aerosol coupling, sedimentation consistency, graupel/riming property prediction, partial cloudiness, and WRF/KIM evaluation cases. These become the scientific boundary conditions for a parity-preserving differentiable implementation.

## Coverage

- Zotero tag: `kdm6-microphysics-survey`
- Staging folder: `/tmp/zotero-kg-kdm6-microphysics-survey`
- Items: 30 total; 24 abstract-supported, 6 metadata-only
- Metadata-only entries: `FPPAYJ7D`, `PR3T9Z88`, `GQGBWTHG`, `BXF95QCZ`, `WGYGYPHD`, `DFJTS2Q8`
- Related differentiable/AD candidate note: [[kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25]]

## Research Synthesis

### WDM/KDM lineage

The most direct KDM6AD-relevant lineage is WSM6 to WDM6 to WDM7/KIM. `S5NS7S78` defines WDM6 as WSM6 plus prognostic number concentrations for cloud and rain and prognostic CCN, giving variable raindrop size distributions at reasonable computational cost. `S4CLN4HN` evaluates WDM6 in WRF and links improved convection and East Asian monsoon rainfall to a wider range of cloud and rain number concentrations. `F9XNUVAV` and `YNQVLR8Y` extend this lineage toward WDM7 and modified WDM6 with mixed-phase terminal velocity and graupel density prediction.

For a new [[KDM6AD]] paper, this lineage supports the claim that the port is not merely an engineering translation: it preserves a scientifically evolved WDM/KDM parameterization family whose key value comes from number and particle-property degrees of freedom.

### Moment closure and distribution control

The two Milbrandt and Yau papers (`FZDHQKYZ`, `8MJWGZTF`) make the spectral shape parameter a central numerical/physical control. Fixed shape parameters affect sedimentation, size sorting, and growth rates; three-moment closure promotes reflectivity as a predicted moment. Morrison et al. (`U7R5SXMJ`, `73FFYNNF`, `KAURJBJH`, `MN2GWUIL`) show the broader consequence: moving from one-moment to two-moment formulations changes rain evaporation, stratiform precipitation, particle size, number concentration, and radiation balance.

For differentiability, these papers identify sensitive axes that gradients should expose. They also flag where derivative quality may be fragile: size-distribution closures, diagnostic intercept parameters, sedimentation moment coupling, and substep/numerical-method choices.

### Sedimentation and numerical consistency

`WWWCHIHX` is especially important for AD-oriented work because it frames artificial reflectivity growth as a numerical artifact from using different weighted fall velocities for different moments. A differentiable implementation can faithfully differentiate a flawed numerical artifact unless parity and numerical consistency are both evaluated. This argues for paper sections that distinguish forward parity, physically meaningful sensitivity, and derivative validation.

### Ice, graupel, riming, and particle-property continua

Several papers move away from fixed ice categories. `6LFPWSSW` uses diagnosed riming intensity and temperature-dependent ice properties to represent a continuum from pristine ice to graupel with fewer processes. The P3 sequence (`V7B2ESBN`, `R5RMW5GG`, `WC9TJWPA`) represents ice using prognosed bulk particle properties, then adds multiple free categories to reduce property dilution. `YNQVLR8Y` adds predicted graupel density to WDM6 and shows changed graupel sedimentation, reduced mountainous precipitation bias, and better graupel density/fall-velocity behavior against disdrometer retrievals. `LCVBT38U` shows precipitation and hail/graupel outcomes are highly sensitive to intercept parameters and particle density.

For [[KDM6AD]], this group is the strongest scientific motivation for gradients with respect to ice/graupel parameters. It also warns that hard category boundaries, density regime switches, and wet/dry growth logic can create nonsmooth or piecewise derivative behavior.

### Aerosol, CCN, and electrification coupling

`S5NS7S78` and `S4CLN4HN` emphasize prognostic CCN and cloud/rain number concentrations in WDM6. `MN6MLEV6` generalizes this to aerosol population modes for CCN and ice-freezing nuclei, including competition through maximum supersaturation. `MJXBBFFI` and `4BGBRWV6` connect CCN, graupel density, rime splintering, hydrometeor number concentration, and storm electrification. Even when electrification is outside KDM6AD's current scope, these papers identify aerosol and number-concentration sensitivities that a differentiable microphysics scheme should be able to interrogate.

### Subgrid variability and partial cloudiness

`FPZXV7V2` and `RY3KNSHQ` show why nonlinear microphysical process rates cannot be treated as if grid-cell mean condensate were representative. `EECBWRCU` extends partial-cloudiness effects into global-model precipitation and radiative feedbacks. The relevance for [[KDM6AD]] is direct: differentiating grid-mean process rates may produce misleading sensitivities unless the subgrid/cloud-fraction treatment is part of the model surface being differentiated.

### Evaluation contexts

The survey spans idealized 1D/2D tests, WRF squall lines, Korean Peninsula convection, East Asian monsoon rainfall, ICE-POP winter storms, CAM3 global simulations, and KIM system context. `29NRUUA4`, `F9XNUVAV`, and `YNQVLR8Y` are particularly useful for Korean winter-storm and WDM-family evaluation framing. `DFJTS2Q8` is metadata-only but identifies the KIM forecast-system context that motivates KDM-family operational relevance.

## Paper-by-Paper Ledger

| Zotero key | DOI | Working role for KDM6AD paper |
| --- | --- | --- |
| `S5NS7S78` | `10.1175/2009MWR2968.1` | WDM6 origin: WSM6 plus cloud/rain number concentrations and prognostic CCN; direct KDM/WDM lineage anchor. |
| `S4CLN4HN` | `10.1155/2010/707253` | WDM6 WRF evaluation; links improved precipitation behavior to broader number-concentration variability. |
| `F9XNUVAV` | `10.3390/rs13193860` | WDM7/Korean Peninsula evaluation; mixed-phase terminal velocity and collision-coalescence modifications. |
| `YNQVLR8Y` | `10.5194/gmd-17-7199-2024` | Modified WDM6 with predicted graupel density; strongest recent WDM6-specific particle-property paper in the set. |
| `FZDHQKYZ` | `10.1175/JAS3534.1` | Spectral shape parameter controls sedimentation and growth rates; key derivative/sensitivity axis. |
| `8MJWGZTF` | `10.1175/JAS3535.1` | Three-moment closure with reflectivity as prognostic moment; useful contrast to KDM6AD diagnostic reflectivity boundary. |
| `WWWCHIHX` | `10.1175/2010JAS3341.1` | Sedimentation/advection consistency; warns that AD can expose numerical artifacts, not just physical sensitivity. |
| `U7R5SXMJ` | `10.1175/JAS3446.1` | Double-moment cloud/climate scheme with nucleation and supersaturation handling; broad process-design reference. |
| `KAURJBJH` | `10.1175/2008JCLI2105.1` | CAM3 two-moment description and numerical tests; substepping and diagnostic precipitation treatment. |
| `MN2GWUIL` | `10.1175/2008JCLI2116.1` | CAM3 two-moment global results; particle size/number/radiation consequences. |
| `73FFYNNF` | `10.1175/2008MWR2556.1` | One- vs two-moment squall-line comparison; rain evaporation and stratiform precipitation sensitivity. |
| `FPPAYJ7D` | `10.1007/s00703-005-0112-4` | Metadata-only two-moment mixed-phase model-description reference; verify full text before citing details. |
| `PR3T9Z88` | `10.1007/s00703-005-0113-3` | Metadata-only maritime vs continental deep-convection reference; verify full text before citing details. |
| `6LFPWSSW` | `10.1175/2010MWR3293.1` | Riming intensity and temperature-dependent ice characteristics; category-continuum alternative. |
| `V7B2ESBN` | `10.1175/JAS-D-14-0065.1` | P3 Part I: prognosed ice particle properties in one free ice category. |
| `R5RMW5GG` | `10.1175/JAS-D-14-0066.1` | P3 Part II: WRF case comparisons; dense hail-like ice vs lower-density graupel behavior. |
| `WC9TJWPA` | `10.1175/JAS-D-15-0204.1` | P3 Part III: multiple free ice categories; property dilution and convergence with added categories. |
| `LCVBT38U` | `10.1175/MWR2810.1` | Hail/graupel intercept and density sensitivity; useful for parameter-gradient motivation. |
| `JSKHVK2M` | `10.1175/2008MWR2387.1` | Thompson snow parameterization; snow density/shape/distribution assumptions affect supercooled water. |
| `MN6MLEV6` | `10.5194/gmd-9-567-2016` | LIMA aerosol/CCN/IFN-driven quasi-two-moment design; aerosol-cloud interaction contrast. |
| `MJXBBFFI` | `10.1175/JAS-D-12-0264.1` | CCN effects on storm microphysics, graupel density, and lightning; aerosol sensitivity example. |
| `4BGBRWV6` | `10.1175/2009JAS2965.1` | Two-moment electrification simulation; hydrometeor number and graupel density affect charging. |
| `FPZXV7V2` | `10.1029/2000JD900504` | Subgrid condensate variability biases nonlinear process rates; tuning-vs-explicit variability framing. |
| `RY3KNSHQ` | `10.1175/JAS-D-17-0234.1` | Partial cloudiness concept for bulk microphysics; in-cloud conversion before process-rate computation. |
| `EECBWRCU` | `10.1029/2018JD029519` | Partial cloudiness in global summer simulations; precipitation/radiative feedback impact. |
| `29NRUUA4` | `10.5194/gmd-15-4529-2022` | ICE-POP WRF comparison of WDM6/WDM7/Thompson/Morrison; melting-process bias diagnosis. |
| `WGYGYPHD` | `10.1007/s13143-018-0066-3` | Metadata-only prognostic hail WRF reference; verify full text before citing details. |
| `DFJTS2Q8` | `10.1007/s13143-018-0028-9` | Metadata-only KIM system reference; motivates operational KIM/KDM context. |
| `GQGBWTHG` | `10.1175/1520-0493(1989)117<0231:AIWSA>2.0.CO;2` | Metadata-only saturation-adjustment reference; likely relevant to nonsmooth adjustment logic. |
| `BXF95QCZ` | `10.1175/1520-0450(1983)022<1065:BPOTSF>2.0.CO;2` | Metadata-only classic snow bulk-parameterization reference; verify full text before citing details. |

## New Paper Use

The most defensible paper angle is: [[KDM6AD]] provides a forward-parity-preserving differentiable implementation of a KDM/WDM-family bulk microphysics scheme, making sensitivities available for scientifically meaningful controls identified by prior microphysics literature. The novelty should not be claimed as a new physical scheme. It should be claimed as an AD-capable implementation surface for an established scheme family, with explicit guardrails for forward parity and derivative interpretation.

Suggested claim structure:

1. The microphysics literature establishes that number concentrations, CCN/aerosol activation, graupel/riming properties, moment closure, and subgrid cloudiness materially alter precipitation and hydrometeor structure.
2. Existing KDM/WDM studies evaluate forward behavior but do not provide a general automatic-differentiation interface for sensitivity, calibration, or DA workflows.
3. [[KDM6AD]] separates operational forward parity from an fp64 handle-based VJP/JVP ABI, allowing derivative experiments without changing the WRF mp137 runtime path.
4. The derivative interpretation must be scoped: diagnostics such as reflectivity/effective radius, saturation adjustment, category thresholds, sedimentation corrections, and partial-cloudiness choices may be nonsmooth or diagnostic-only.

## Open Risks

- This ingest used Zotero metadata and abstracts only, not full PDF text.
- The six metadata-only entries need full-text verification before being used as evidence in a manuscript.
- The Zotero tag is microphysics-heavy but AD-light; the differentiable-programming and algorithmic-differentiation literature is tracked separately in [[kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25]].

## Links

- [[KDM6]]
- [[KDM6AD]]
- [[WRF KIM-meso Host]]
- [[Bulk Microphysics Design Space]]
- [[Differentiable Bulk Microphysics Research Gap]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
