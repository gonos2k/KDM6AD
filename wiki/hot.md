---
title: Hot Cache
type: meta
date_modified: 2026-07-02
---
# Hot Cache

## Current Focus
- [[KDM6AD Forward Parity]] between mp37 [[KDM6]] and mp137 [[KDM6AD]].
- [[KDM6AD Automatic Differentiation ABI]] boundaries, especially forward-only diagnostics.
- [[Differentiable Bulk Microphysics Research Gap]] for a new paper on parity-preserving differentiable KDM/WDM-family microphysics.
- [[kdm6ad-code-story-literature-review-2026-06-25]] as the current code-explanation storyline.
- [[kdm6plus-collection-mathematical-deep-ingest-2026-06-25]] as the deeper math-focused literature ingest for manuscript drafting.
- [[KDM6AD Mathematical Microphysics Operators]] and [[KDM6AD Differentiability Audit]] as the current technical framing for derivative claims.
- [[kdm6ad-20260610-presentation-adversarial-review]] as the presentation coverage check: useful story source, but stale on C-ABI VJP/JVP implementation status.
- [[papers/_index|KDM6AD 논문 페이지 색인]] with 42 separate paper pages.
- [[KDM6 Literature Genealogy]] and [[KDM6AD Literature Claim Map]] as the two main paper-link hubs.

## Recent Activity
- 2026-07-02 ACHIEVED full 10-step (→12h np4-tcp gate in progress) STRICT BITWISE parity, all 254 vars, every frame. The 2026-06-30 "irreducible §48 graupel-density floor / accept prognostic parity out-of-scope" verdict is SUPERSEDED: that floor decomposed into ~20 fixable 1:1 classes (§53–§53u). RHO_ICE floor fixed by symmetric clamp-boundary snap at BOTH bounds (§53r); the rest by unconditional rate-loop vt2 (§53k), RAW wilt/sqrt divisions on the f32 op-path (§53n/§53u), qv-clamp removal (§53t), Nrevp in-loop transfer (§53s), Picons/limiter gates (§53q). Also: MPI (np≥2) needs `--mca btl self,tcp` — Open MPI shared-memory BTL SEGVs flakily with the libtorch-loaded ranks. See [[kdm6ad-10step-bitwise-achieved-2026-07-02]]. Traps → fortran-pytorch-port lessons-learned §53–§61.
- 2026-06-30 fixed frame-2 divergence root cause: rain-NUMBER sedimentation in the C++ port (sedimentation.cpp falk_nr missing f32 store cast; slope.cpp:77 rain vtn f32→f64). Verified nr/qr bitwise; QNRAIN ↓99.5%; RAINNC/VIS resolved. (SUPERSEDED framing: the "remaining §48 graupel-density floor" was NOT irreducible — see 2026-07-02.) See [[kdm6ad-frame2-rain-sed-bitwise-fix-2026-06-30]].
- 2026-06-29 ran /kg-reflect: surfaced the parity↔AD surface-disjointness gap, the step-1-only parity vs frame 2/3 divergence blind spot, and the unquantified mp137 slowdown (Benchmark schema signal).
- 2026-06-25 rechecked SS strict bitwise parity: frame index 1 is the documented gate and passes for final/gate/relink/kstandalone pairs.
- 2026-06-25 verified `/Users/yhlee/KDM6AD-k` as the current reviewed code/KG root and filed [[kdm6ad-final-code-location-verification-2026-06-25]].
- 2026-06-25 recorded [[Codex Canonical Worktree Decision 2026-06-25]] and [[Codex Stale Nested Cwd Incident 2026-06-25]] in KG.
- 2026-06-25 corrected Codex session-directory record: canonical root is `/Users/yhlee/KDM6AD-k`, not `/Users/yhlee/KDM6AD/KDM6AD-k`.
- 2026-06-25 vault bootstrapped locally.
- 2026-06-25 ingested [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]].
- 2026-06-25 aligned kg-skill setup for Codex and pinned `wiki/.schema`.
- 2026-06-25 ingested [[kdm6-microphysics-zotero-survey-2026-06-25]] from the Zotero tag `kdm6-microphysics-survey`.
- 2026-06-25 added [[kdm6ad-code-story-literature-review-2026-06-25]] for reference-backed code storytelling.
- 2026-06-25 narrowed Zotero `KDM6+` to KDM6/KDM6AD papers and ingested the collection with full-text mathematical emphasis.
- 2026-06-25 adversarially reviewed `/Users/yhlee/Desktop/이대/발표자료/(20260610)KDM6AD.pptx` and added it as a source note.
- 2026-06-25 split the `KDM6+` set into 42 individual Korean paper pages under `wiki/papers/`.

## Key Tensions / Open Questions
- Codex session metadata for this thread still carries the old nested cwd; future edits must explicitly use `/Users/yhlee/KDM6AD-k`. See [[Codex Canonical Worktree Decision 2026-06-25]].
- STALE-FRAMING (2026-07-02): the concept/overview/audit layer still asserts "step-1 (frame index 1) is THE documented gate" and "diag_rhog is an irreducible parity floor." Both are now FALSE — parity holds through 10 steps (→12h) on all 254 vars/all frames, and the RHO_ICE floor was fixable (§53r). [[KDM6AD Forward Parity]], `overview.md`, and [[kdm6ad-frame2-rain-sed-bitwise-fix-2026-06-30]] need their "gate = step-1 only" / "floor accepted out-of-scope" claims rewritten.
- OP-PATH-RAW vs DA-CLAMPED idiom (emerging, no page): [[KDM6AD Differentiability Audit]] frames min/max clamps as uniformly "piecewise smooth, AD-safe." Parity required REMOVING those clamps on the operational f32 path (Fortran uses raw ÷/sqrt) while keeping smooth clamped forms ONLY on the f64 DA path — a dtype-conditional dual-path idiom now used ~25× (§53n/§53t/§53u/§60). The two framings reconcile via this idiom, which deserves its own concept/heuristic page.
- Upstream kg-skill docs remain Claude Code oriented, so slash-command guidance must be translated to Codex skill triggers or bare Graphify CLI commands.
- `diag_rhog` is excluded from the packed AD ABI — but now because it is a diagnostic with no meaningful derivative, NOT because it is an irreducible parity floor (that rationale is superseded; diag_rhog is bitwise as of §53r).
- mp137 is slower than mp37 in observed final SS timing (still unquantified — Benchmark-schema signal). MPI note: np≥2 needs `--mca btl self,tcp` (Open MPI shm BTL SEGVs with libtorch-loaded ranks).
- The Zotero microphysics survey is abstract-only for 24 papers and metadata-only for 6 papers; full-text verification is still needed before manuscript citation.
- The new deep ingest covers 35 PDFs, but 7 KDM6-relevant metadata-only items still need source PDFs before detailed claims.
- The June 10 presentation contains a stale claim that C-ABI VJP/JVP was unimplemented. Current code/test status supersedes that slide.
- Seven paper pages are intentionally conservative because their Zotero items still lack attached PDFs.
- [reflect 2026-06-29] Parity surface ≠ AD surface: the f32 forward gate validates outputs (incl. `diag_rhog`, `REFL_10CM`, `re_*`) that the fp64 packed AD ABI *excludes*, on a different precision and variable set. Nothing in the wiki gates the fp64 differentiated forward map against [[KDM6]]. See [[KDM6AD Forward Parity]] vs [[KDM6AD Automatic Differentiation ABI]] / [[KDM6AD Differentiability Audit]].
- [RESOLVED 2026-06-30, SUPERSEDED 2026-07-02] The frame 2/3 divergence (was: 19/51 differing vars) was the rain-NUMBER sedimentation port bug (falk_nr f32-cast + rain vtn f64), NOT a satadj/condensation issue — fixed + verified. The 06-30 "residual = §48 graupel-density clamp floor, accepted out-of-scope" conclusion is NO LONGER TRUE: on 2026-07-02 the full residual (graupel density + all remaining vars) was driven to STRICT BITWISE through 10 steps → 12h. See [[kdm6ad-10step-bitwise-achieved-2026-07-02]]. (Step-1 was never the "intended gate"; it was the last fully-bitwise step before the rain-sed seed activated — now every step is bitwise.)
- [reflect 2026-06-29] "mp137 slower than mp37" is asserted across 5 pages but never quantified; no Benchmark page/number exists. Candidate schema signal SIG-001 (EMERGING_CLASS Benchmark).
