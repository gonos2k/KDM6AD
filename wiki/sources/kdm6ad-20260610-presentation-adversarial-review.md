---
title: KDM6AD 20260610 Presentation Adversarial Review
date_ingested: 2026-06-25
source_type: presentation-review
tags:
  - kdm6ad
  - presentation
  - adversarial-review
  - automatic-differentiation
  - data-assimilation
---
# KDM6AD 20260610 Presentation Adversarial Review

## Source

- PPTX: `/Users/yhlee/Desktop/이대/발표자료/(20260610)KDM6AD.pptx`
- Existing extraction: `.omo/ultraresearch/20260625-150432-kdm6ad-papers/pptx_extract/slides_text.md`
- Existing image contact sheet: `.omo/ultraresearch/20260625-150432-kdm6ad-papers/pptx_extract/contact_sheet.jpg`
- PPTX structure: 15 slides. Slide bodies are image-only; speaker notes contain the extractable text.
- OCR caveat: local Tesseract has `eng`, `osd`, and `snum`, but no Korean model. Slide image review therefore used the contact sheet plus the embedded speaker notes.

## Inclusion Verdict

This presentation was not previously represented as a first-class source page in the wiki. Its extracted notes existed under `.omo/ultraresearch/.../pptx_extract`, but the main KG pages did not cite the PPTX directly.

The current wiki already covers some of its technical themes:

- [[KDM6AD Forward Parity]] covers the mp37/mp137 parity theme.
- [[KDM6AD Automatic Differentiation ABI]] covers the separated operational and AD paths.
- [[kdm6ad-code-story-literature-review-2026-06-25]] covers the manuscript story around parity-preserving differentiable implementation.
- [[KDM6AD Differentiability Audit]] covers the need to qualify derivative claims around nonsmooth gates.

But the presentation adds historical and explanatory material that was underrepresented:

- the "one physics, five representations" storyline: Fortran original, PyTorch oracle, C++ operational mirror, C ABI, Fortran wrapper;
- the precision-fence story: early boundary casts injected a frame-1 seed error, later removed by making the operational path f32 while preserving fp64 for AD;
- the human/AI/KG adversarial loop as a development process narrative;
- the warning that the June 10 presentation state is not identical to the June 25 current code state.

## Slide-Level Coverage Matrix

| Slide | Presentation claim | Current KG coverage | Adversarial status |
| --- | --- | --- | --- |
| 1 | Five-act story: need, artifact, trust, human/AI process, close | Partially covered by [[overview]] and [[kdm6ad-code-story-literature-review-2026-06-25]] | Add as presentation/story source, not physics evidence. |
| 2 | KDM6 microphysics is a strongly branched six-species water transformation problem | Covered only broadly by literature and KDM6/KDM6AD notes | The "312 branches" figure needs code-count evidence before manuscript use. |
| 3 | 4D-Var needs `grad J`; microphysics must provide tangent/adjoint information | Covered by [[KDM6AD Mathematical Microphysics Operators]] and DA canvas | Must state that KDM6AD supplies only a microphysics block, not a complete 4D-Var system. |
| 4 | Existing Fortran is forward-only; branches, clipping, NaN gates block naive gradients | Covered by [[KDM6AD Differentiability Audit]] | Correct direction, but should be made mathematical with piecewise-smooth operator language. |
| 5 | One physics represented five times: Fortran original, PyTorch oracle, C++ runtime, C seam, Fortran wrapper | Partially covered in AGENTS/README, weak in wiki | Add to story as a verification architecture. |
| 6 | Two paths: f32 WRF operational path and fp64 4D-Var path; June 10 notes say working gradients were direct fp64 oracle and C-ABI VJP/JVP were G3-unimplemented | Wiki currently says handle C-ABI VJP/JVP exists | Historical claim is stale for current code. Current code implements `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c`; targeted tests passed on 2026-06-25. |
| 7 | AD leaves a graph, reverse mode gives adjoint, forward mode gives tangent | Covered by AD ABI and math operator notes | Rhetorical "free differentiation" must be qualified: AD cost, memory, nonsmooth gates, and diagnostic boundaries remain. |
| 8 | f32 operational path removed a boundary-cast seed error; fp64 AD path remains | Partially covered by parity notes | Good internal story, but needs exact experiment artifact if used as a paper result. |
| 9 | Frame 0-1 bit-identical; later divergence is floating-point non-associativity amplification, not a defect | Partially covered by forward parity | Should not overclaim general stability. Use as a specific SS/run observation unless rerun broadly. |
| 10 | Unit tests, AD tests, symbolic parity, clean build, WRF run passed; tolerance policy remains | Covered by code comparison snapshot | Current targeted C-ABI tests passed; a fresh full WRF run was not rerun in this review. |
| 11 | Shift from code to working method | Not core technical wiki | Keep in process/story section only. |
| 12 | LLM-wiki, source, graph, authority split | Covered by kg setup/log | Useful for methodology narrative, not scientific evidence. |
| 13 | Claude Code builds, Codex breaks; six review passes converged defects into documentation | Partially reflected in logs | Valuable process evidence, but should not substitute for tests. |
| 14 | Human/Claude/Codex/KG loop as self-reinforcing process | Partially reflected in KG logs | Keep as development narrative. |
| 15 | One-and-a-half-month journey from reference implementation to integration/parity/f32/adversarial convergence | Not directly covered | Useful as timeline, but claims need dates and artifacts. |

## Adversarial Findings

### Finding 1: Slide 6 is stale if read as current status

The presentation says the current working gradient is not ABI-based and that C-ABI VJP/JVP is unimplemented. That was credible as a June 10 milestone, but it is no longer the current June 25 code state.

Current evidence:

- `libtorch/bridge/kdm6_c_api.cpp:307` defines `kdm6_step_ad_c`.
- `libtorch/bridge/kdm6_c_api.cpp:370` defines `kdm6_handle_vjp_c`.
- `libtorch/bridge/kdm6_c_api.cpp:398` defines `kdm6_handle_jvp_c`.
- `host_fortran/kdm6_iso_c.F:183` wraps the fp64 DA path and handle calls for Fortran.
- `libtorch/tests/test_c_abi.cpp:249` exercises packed VJP/JVP ABI mechanics.
- `libtorch/tests/test_fortran_smoke.f90:120` exercises the Fortran `kdm6_step_ad` and `kdm6_handle_vjp` path.
- Verification on 2026-06-25: `ctest --test-dir libtorch/build -R "(c_abi|fortran|handle|autograd)" --output-on-failure` passed 4/4 tests.

Therefore the wiki should not say "C-ABI VJP/JVP is unimplemented" as a current fact. It should say:

> In the 2026-06-10 presentation, C-ABI VJP/JVP was still described as future work. In the current 2026-06-25 code, the fp64 packed C/Fortran AD ABI exists and has targeted tests, while the WRF mp137 runtime remains value-only.

### Finding 2: The presentation is strong on story but thin on microphysics mathematics

The slides explain why differentiability matters, but they do not contain PSD moment equations, fall-speed moment weighting, process-rate nonlinearity, or observation-operator derivatives. For a manuscript, this presentation cannot replace [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]].

The paper should still include equations such as:

```text
y_{n+1} = F_KDM6(y_n, x_n, theta)
delta y_{n+1} = J_y delta y_n + J_x delta x_n + J_theta delta theta
lambda_n = J_y^T lambda_{n+1}
n_x(D) = N0_x D^{mu_x} exp(-lambda_x D)
M_k = N0_x Gamma(mu_x+k+1) / lambda_x^{mu_x+k+1}
```

### Finding 3: The 4D-Var story needs a boundary statement

Slide 3 correctly motivates `grad J`, but a hostile reader can object that a microphysics tangent/adjoint block is not a complete 4D-Var system. The manuscript should state the scope explicitly:

```text
KDM6AD exposes a differentiable microphysics step/operator. Full 4D-Var still
requires the host model trajectory, observation operators H, time-window
accumulation, checkpointing, background/observation covariances, and minimization.
```

This prevents overclaiming "KDM6AD is a 4D-Var implementation."

### Finding 4: "Differentiation comes for free" is rhetorically useful but scientifically unsafe

Slide 7 is a good oral explanation, but the paper should not use that phrase literally. AD provides exact derivatives of the implemented computational graph, not necessarily physically meaningful derivatives across nonsmooth thresholds.

Use the [[KDM6AD Differentiability Audit]] framing instead:

- smooth regions: moment equations, power-law fall speeds away from zero;
- piecewise-smooth regions: `max`, `min`, clamps, category gates;
- fragile regions: inactive hydrometeor corners, zero/near-zero PSD variables, `0*Inf` autograd patterns;
- excluded diagnostics: `diag_rhog`, some reflectivity/effective-radius products unless explicitly included in the differentiated operator.

### Finding 5: "New path is more stable" needs a narrower claim

Slide 9 says the new path is "more stable." The current evidence supports a narrower claim:

> The f32 operational path removed the observed boundary-cast seed mismatch and achieved strict parity in the tested SS artifacts.

It does not prove broad numerical stability across all cases, resolutions, compilers, architectures, or long integrations. If the phrase remains in a presentation, it should be framed as "more stable in the observed parity gate" or backed by a broader regression matrix.

### Finding 6: The process narrative is useful, but it must not replace reproducible gates

Slides 11-14 describe the human/Claude/Codex/KG loop. This is valuable for project methodology and reproducibility history, but the technical paper should put this after hard artifacts:

- code path and ABI;
- parity evidence;
- AD dot-product/JVP/VJP evidence;
- differentiability audit;
- literature-motivated sensitivity axes.

The KG/adversarial loop can be a development-method note, not the main scientific proof.

## What To Carry Into The Manuscript

Use the presentation for:

- a concise motivation: microphysics is a highly nonlinear branch-heavy operator where DA needs tangent/adjoint products;
- architecture storytelling: one physics preserved across reference, oracle, C++ mirror, C ABI, and host wrapper;
- separation of paths: f32 operational parity path versus fp64 AD/DA path;
- trust narrative: parity gates plus adversarial review plus KG memory.

Do not use the presentation alone for:

- mathematical derivations;
- literature-backed claims about KDM/WDM physics;
- current implementation status of C-ABI VJP/JVP without the June 25 code correction;
- full data-assimilation system claims.

## Updated Current Claim

The KG should use this current claim:

> [[KDM6AD]] currently separates a value-only f32 WRF/mp137 operational path from a packed fp64 AD path. The June 10 presentation captured an earlier phase in which direct fp64 oracle gradients were the working surface and C-ABI VJP/JVP was still future work. The current June 25 code exposes C/Fortran handle VJP and JVP products through `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c`, with targeted C++/Fortran tests passing. Manuscript claims should therefore cite the PPTX only as historical/story context and cite current code/tests for ABI status.

## Links

- [[KDM6AD]]
- [[KDM6AD Automatic Differentiation ABI]]
- [[KDM6AD Forward Parity]]
- [[KDM6AD Differentiability Audit]]
- [[kdm6ad-code-story-literature-review-2026-06-25]]
- [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]]
