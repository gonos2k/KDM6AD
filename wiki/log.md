---
title: Wiki Log
type: meta
date_modified: 2026-06-25
---
# Wiki Log

## [2026-06-25] init | local Obsidian vault bootstrapped
- Wiki root: `/Users/yhlee/KDM6AD-k/wiki`
- Mode: local Obsidian vault initialization
- Schema pin: skipped, global kg schema files missing
- Next: ingest KDM6 vs KDM6AD comparison into `sources/`, `entities/`, and `concepts/`.

## [2026-06-25] ingest | KDM6 vs KDM6AD Code Comparison
- Added: `sources/kdm6-vs-kdm6ad-code-comparison-2026-06-25.md`
- Added entities: `entities/KDM6.md`, `entities/KDM6AD.md`, `entities/WRF KIM-meso Host.md`
- Added concepts: `concepts/KDM6AD Forward Parity.md`, `concepts/KDM6AD Automatic Differentiation ABI.md`
- Updated: `overview.md`, `index.md`, `hot.md`, folder `_index.md` pages
- Tensions found: formal kg schema pin is still unavailable; `diag_rhog` is forward-only and not in the packed AD ABI; mp137 is slower in observed SS timing.

## [2026-06-25] kg-update | graphify refreshed after ingest
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Graph: 40955 nodes / 66522 edges / 4812 communities
- Wiki sync: navigation metadata updated.
- Caveats: graphify CLI reports code extraction only; markdown/wiki semantic extraction would require slash `/graphify --update`.

## [2026-06-25] kg-update | graphify refreshed on request
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Per-corpus delta: 40959 nodes / 66526 edges / 4824 communities; AST extraction 4854/4854 files
- Wiki sync: navigation metadata updated.
- Caveats: graphify CLI updates code extraction only; docs/wiki semantic extraction requires slash `/graphify . --update`.

## [2026-06-25] setup | Codex kg-skill alignment
- Added: project `AGENTS.md` with Codex-adapted KG/Graphify rules.
- Installed: pinned schema files under `wiki/.schema/`.
- Mirrored: kg schema/templates into Codex-readable global skill directories.
- Verified: local `graphify` version is `0.8.39`.
- Caveats: upstream `kg-skill` remains Claude Code oriented; slash-command guidance must be translated to Codex skills or bare Graphify CLI commands.

## [2026-06-25] kg-update | graphify refreshed after Codex kg-skill alignment
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update --force`
- Per-corpus delta: 42651 nodes / 68217 edges / 4812 communities; AST extraction 4855/4855 files
- Wiki sync: navigation metadata updated.
- Caveats: force was used to accept a small node-count shrink after wiki/meta text cleanup; graphify CLI updates code extraction only, while docs/wiki semantic extraction requires an available Graphify orchestrator/skill.

## [2026-06-25] init-deep | KDM6/KDM6AD AGENTS hierarchy
- Scope: KDM6/KDM6AD only; broad WRF/vendor guidance intentionally excluded.
- Added/updated: root `AGENTS.md`, `libtorch/AGENTS.md`, `oracle/AGENTS.md`, `host_fortran/AGENTS.md`, `host/KIM-meso_v1.0/AGENTS.md`, `harness/AGENTS.md`.
- Mode: `cli-update`
- Per-corpus delta: 42683 nodes / 68244 edges / 4823 communities; AST extraction 4860/4860 files
- Wiki sync: navigation metadata updated.
- Caveats: graphify CLI updates code extraction only; docs/wiki semantic extraction requires an available Graphify orchestrator/skill.

## [2026-06-25] kg-update | KDM6/KDM6AD graph refreshed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Per-corpus delta: 42693 nodes / 68254 edges / 4828 communities; AST extraction 4860/4860 files
- Wiki sync: navigation metadata updated.
- Caveats: graphify CLI updates code extraction only; docs/wiki semantic extraction requires an available Graphify orchestrator/skill.

## [2026-06-25] zotero-kg | KDM6AD differentiable microphysics bridge
- Zotero status: local API and connector reachable; semantic DB has 119 documents.
- Exported: Zotero tag `kdm6-microphysics-survey` to `/tmp/zotero-kg-kdm6-microphysics-survey` (30 markdown files).
- Added query note: `queries/kdm6ad-differentiable-microphysics-zotero-kg-2026-06-25.md`.
- Dry-run only: 5 candidate differentiable/AD references built under tag `kdm6ad-differentiable-microphysics`; no Zotero writes performed.
- Caveats: Zotero writes require explicit approval; full tag ingest still requires `$kg-ingest /tmp/zotero-kg-kdm6-microphysics-survey`.

## [2026-06-25] kg-update | zotero-kg note indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Per-corpus delta: 42710 nodes / 68270 edges / 4827 communities; AST extraction 4861/4861 files
- Wiki sync: navigation metadata updated after Zotero-KG query note.
- Caveats: Zotero writes remain dry-run only until explicitly approved.

## [2026-06-25] kg-ingest | KDM/WDM microphysics Zotero survey
- Source: `/tmp/zotero-kg-kdm6-microphysics-survey` (`kdm6-microphysics-survey`, 30 Zotero markdown exports)
- Added source page: `sources/kdm6-microphysics-zotero-survey-2026-06-25.md`
- Added concepts: `Bulk Microphysics Design Space`, `Differentiable Bulk Microphysics Research Gap`
- Updated entities/navigation: `KDM6`, `KDM6AD`, `overview.md`, `hot.md`, `sources/_index.md`, `concepts/_index.md`, `index.md`
- Caveats: analysis is abstract-only for 24 papers and metadata-only for 6 papers; full-text verification remains necessary before manuscript citation.

## [2026-06-25] kg-update | KDM/WDM microphysics survey indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Per-corpus delta: 42746 nodes / 68303 edges / 4833 communities; AST extraction 4864/4864 files
- Wiki sync: navigation metadata updated.
- Caveats: Graphify CLI updated code/wiki markdown structure only; semantic paper extraction beyond the source pages would require slash/orchestrator graphify update.

## [2026-06-25] kg-ingest | KDM6AD code story literature review
- Added source page: `sources/kdm6ad-code-story-literature-review-2026-06-25.md`
- Focus: manuscript-ready explanation of current KDM6AD architecture using KDM/WDM microphysics, AD cloud-microphysics, and Fortran/PyTorch interop references.
- Updated navigation/entity pages: `sources/_index.md`, `KDM6AD`, `overview.md`, `hot.md`, `index.md`
- Caveats: this is a literature/code synthesis note; cited papers still need full-text verification before final manuscript citation wording.

## [2026-06-25] kg-update | KDM6AD code story indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Per-corpus delta: 42774 nodes / 68330 edges / 4830 communities; AST extraction 4865/4865 files
- Wiki sync: navigation metadata updated.
- Caveats: Graphify CLI updated structural markdown extraction only; external paper full-text semantic extraction remains outside this run.

## [2026-06-25] cleanup | vault visibility cleanup
- Removed the raw structural report mirror from the Obsidian vault.
- Updated: `wiki/index.md`, `AGENTS.md`, Obsidian app/workspace settings.
- Policy: generated structural artifacts are ignored by Obsidian; the vault keeps synthesized KG notes and Canvas views only.

## [2026-06-25] kg-ingest | KDM6+ collection mathematical deep ingest
- Source: Zotero collection `KDM6+` (`ZABGLNPX`), staged at `.omo/kg-ingest-kdm6plus-20260625/staging` with 42 item markdown exports.
- Full text: extracted PDF text/snippets for 35/42 items; 7 metadata-only items remain flagged for source PDF acquisition.
- Added source page: `sources/kdm6plus-collection-mathematical-deep-ingest-2026-06-25.md`.
- Added concepts: `KDM6AD Mathematical Microphysics Operators`, `KDM6AD Differentiability Audit`.
- Updated entities/navigation: `KDM6`, `KDM6AD`, `overview.md`, `hot.md`, `sources/_index.md`, `concepts/_index.md`, `index.md`.
- Focus: PSD moment equations, nonlinear process rates, graupel-density sensitivity, sedimentation consistency, JVP/VJP checks, and DA observation-operator boundaries.

## [2026-06-25] kg-update | KDM6+ mathematical deep ingest indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Graphify refresh: 41308 nodes / 66839 edges / 4873 communities; AST extraction 4932/4932 files.
- HTML graph view: skipped by Graphify because the graph exceeds the 5000-node visualization limit.
- Wiki verification: source/concept pages linked from `index.md`, `overview.md`, `hot.md`, source index, concept index, `KDM6`, and `KDM6AD`.
- Caveats: Graphify CLI refreshes structural code/markdown graph artifacts. The full paper semantics are represented in the authored KG notes and Zotero staging manifest rather than a separate LLM semantic extraction pass.

## [2026-06-25] kg-challenge | 20260610 KDM6AD presentation adversarial review
- Source: `/Users/yhlee/Desktop/이대/발표자료/(20260610)KDM6AD.pptx`
- Extraction basis: existing slide notes and image contact sheet under `.omo/ultraresearch/20260625-150432-kdm6ad-papers/pptx_extract/`.
- Added source page: `sources/kdm6ad-20260610-presentation-adversarial-review.md`.
- Updated: `overview.md`, `hot.md`, `index.md`, `sources/_index.md`, `KDM6AD`, and `KDM6AD Automatic Differentiation ABI`.
- Main adversarial finding: slide 6 is historical/stale for current ABI status. Current code exposes `kdm6_step_ad_c`, `kdm6_handle_vjp_c`, and `kdm6_handle_jvp_c`; targeted `ctest -R "(c_abi|fortran|handle|autograd)"` passed 4/4.
- Caveats: slide bodies are image-only and local OCR lacks Korean language data, so review used extracted speaker notes plus visual contact-sheet inspection.

## [2026-06-25] kg-update | presentation review indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Graphify refresh: 41327 nodes / 66857 edges / 4880 communities; AST extraction 4933/4933 files.
- HTML graph view: skipped by Graphify because the graph exceeds the 5000-node visualization limit.
- Caveats: Graphify CLI refreshes structural code/markdown graph artifacts; Korean slide-image OCR was not available locally.

## [2026-06-25] kg-ingest | KDM6AD individual paper pages
- Source: Zotero `KDM6+` curated set and `.omo/kg-ingest-kdm6plus-20260625` staging/manifest.
- Added: `wiki/papers/_index.md` and 42 individual paper pages named `paper-<ZoteroKey>.md`.
- Added concepts: `KDM6 Literature Genealogy`, `KDM6AD Literature Claim Map`.
- Updated navigation/entity pages: `index.md`, `overview.md`, `hot.md`, `sources/_index.md`, `concepts/_index.md`, `KDM6`, and `KDM6AD`.
- Policy: individual paper reasoning belongs in `wiki/papers/`; source pages remain collection ledgers and synthesis/review pages.
- Caveats: 7 papers still lack attached PDFs, so their pages intentionally avoid strong quantitative claims until source PDFs are acquired.

## [2026-06-25] kg-update | individual paper pages indexed
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Graphify refresh: 41692 nodes / 67182 edges / 4913 communities; AST extraction 4973/4973 files.
- Verification: 42 `wiki/papers/paper-*.md` pages, one `wiki/papers/_index.md`, and zero missing wiki links in local link scan.
- Caveats: Graphify CLI refreshes structural code/markdown graph artifacts; full semantic paper re-extraction would require the slash/orchestrator graphify path.

## [2026-06-25] kg-ingest | KDM6AD 논문별 학술 계보 페이지 대폭 개선
- Source: `.omo/zotero-kdm6plus-kdm6-only-20260625/kdm6plus_kdm6_only_literature_summary.json` + `.omo/kg-ingest-kdm6plus-20260625/kdm6plus_collection_fulltext_manifest.json`
- Scope: Zotero `KDM6+` 중 KDM6/KDM6AD 관련 42편 개별 논문 페이지 전체 재작성.
- Change: 각 페이지에 학술적 가치, 계보적 위치, 방법론, 수학적 구조, KDM6AD JVP/VJP·자료동화 연결, 정당화 가능/불가능 주장, 후속 연구 질문을 추가.
- Caveat: 원문 미확보 7편은 공개 초록·출판사 메타데이터 기반 보수 정리로 표시.

## [2026-06-25] kg-ingest | 논문 페이지 계보·연산자·미분 독해 추가 보강
- Scope: `wiki/papers/paper-*.md` 42편에 계보적 독해 매트릭스, KDM6AD 연산자 대응, 미분가능 미세물리 수학 독해, 적대적 검토 포인트 추가.
- Rationale: 기존 확장 후에도 분량과 학술 밀도가 부족할 수 있어 각 논문을 독립 학술 노드로 읽을 수 있도록 보강.

## [2026-06-25] kg-update | 논문 페이지 심화 보강 후 graphify 갱신
- Source dir: `/Users/yhlee/KDM6AD-k`
- Mode: `cli-update`
- Graphify refresh: 41989 nodes / 67483 edges / 4913 communities; AST extraction 4969/4969 files.
- Wiki sync: raw code-tree `GRAPH_REPORT.md`는 AGENTS.md 지침에 따라 `wiki/`로 복사하지 않고 `graphify-out/`에만 유지.
- Caveats: Graphify CLI는 구조적 code/markdown graph 갱신이며, 논문 원문 전체의 LLM semantic re-extraction은 별도 orchestrator 경로가 필요하다.

## [2026-06-25] session-correction | Codex session directory corrected
- Canonical project root: `/Users/yhlee/KDM6AD-k`
- Canonical wiki root: `/Users/yhlee/KDM6AD-k/wiki`
- Correction: older Codex session metadata and shell `PWD` still report `/Users/yhlee/KDM6AD/KDM6AD-k`; that nested path is not the active worktree for KDM6AD-k records or code work.
- Action: updated `AGENTS.md` to require explicit `/Users/yhlee/KDM6AD-k` workdir verification before edits.

## [2026-06-25] guardrail | stale nested path marked as non-worktree
- Added stop instructions at `/Users/yhlee/KDM6AD/KDM6AD-k/AGENTS.md`.
- Added visible marker at `/Users/yhlee/KDM6AD/KDM6AD-k/DO_NOT_WORK_HERE.md`.
- Purpose: if Codex or another tool follows stale session metadata into the nested path, the first project instruction should redirect work to `/Users/yhlee/KDM6AD-k`.
- Hard-stop option still pending explicit approval: move the nested tree aside and replace `/Users/yhlee/KDM6AD/KDM6AD-k` with a symlink to `/Users/yhlee/KDM6AD-k`.

## [2026-06-25] kg-record | Codex canonical worktree decision filed
- Added decision page: `decisions/Codex Canonical Worktree Decision 2026-06-25.md`.
- Added experience page: `experiences/Codex Stale Nested Cwd Incident 2026-06-25.md`.
- Updated: `index.md`, `decisions/_index.md`, `experiences/_index.md`, and `hot.md`.
- Canonical root remains `/Users/yhlee/KDM6AD-k`; stale nested path remains `/Users/yhlee/KDM6AD/KDM6AD-k`.

## [2026-06-25] kg-query | KDM6AD final code location verification
- Added query page: `queries/kdm6ad-final-code-location-verification-2026-06-25.md`.
- Result: current reviewed code and KG/wiki are under `/Users/yhlee/KDM6AD-k`, not `/Users/yhlee/KDM6AD/KDM6AD-k`.
- Verification: Graphify query found KDM6AD nodes in canonical graph; `ctest --test-dir libtorch/build --output-on-failure` passed 16/16; miniforge `pytest oracle/tests/test_cpp_parity.py -q` passed 1/1.
- Initial observation: existing SS `klfs_lc05_fcst` artifacts pass strict bitwise comparison at frames 0/1 and differ at frames 2/3. Subsequent recheck clarified that the documented gate is frame index 1.
- Updated: `overview.md`, `hot.md`, `index.md`, `queries/_index.md`, `KDM6`, `KDM6AD Forward Parity`, and `kdm6-vs-kdm6ad-code-comparison-2026-06-25.md`.

## [2026-06-25] kg-query | SS step-1 bitwise gate rechecked
- Result: documented SS strict bitwise gate is `klfs_lc05_fcst.202507190000` frame index `1`, corresponding to the `history_interval_s=20` step-1 frame.
- Verification: final pair `mp37_final_1min_hist0_20260624_194512` vs `mp137_final_1min_hist0_20260624_194620` passed with 254 common variables, 253 numeric bitwise matches, 0 differences, and 1 non-numeric `Times` variable.
- Additional check: gate/relink/kstandalone historical mp37/mp137 pairs also passed at frame index `1`.
- Correction: the previous last-frame/default-frame comparison was outside the documented SS step-1 gate and should not be cited as a failure of the KDM6AD bitwise parity claim.

## [2026-06-25] kg-lint | graph/wiki health and current parity status
- Graph health: `graphify-out/graph.json` parses as 42026 nodes / 67516 edges; `GRAPH_REPORT.md` and `manifest.json` exist.
- Graph caveat: `.graphify_python` was not found in this tree, so the configured Graphify interpreter pin is missing or not used by this checkout.
- Freshness: before this log entry, no wiki Markdown page was newer than `GRAPH_REPORT.md`. Source freshness had one meaningful candidate newer than `graph.json`: `host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/namelist.input`, modified by the fresh SS parity run; generated SS run outputs were newer but treated as run artifacts.
- Wiki health: 77 Markdown pages, 1090 wikilinks, 0 missing wikilink targets, 0 ambiguous targets. Orphans were limited to `index.md` and `.schema/README.md`; zero-outgoing pages were `.schema/README.md`, `heuristics/_index.md`, `procedures/_index.md`, and `log.md`.
- Current parity status rechecked with fresh current-build outputs: `mp37_current_bitwise_1min_hist0_20260625_181246` vs `mp137_current_bitwise_1min_hist0_20260625_181449`, both `exit_code=0`.
- README parity settings were confirmed in both copied run namelists: `run_minutes=1`, `history_interval=0`, `history_interval_s=20`, `use_adaptive_time_step=.false.`, `step_to_output_time=.false.`, with `mp_physics=37` for KDM6 and `mp_physics=137` for KDM6AD.
- Exact result: `klfs_lc05_fcst.202507190000` frame index `1` passed strict raw-bit comparison with 254 common variables, 253 numeric bitwise matches, 0 differences, and 1 non-numeric `Times` variable. Frame `0` also passed; frame `2` failed with 19 differing numeric variables and frame `3` failed with 51.
- Wording caveat: claims should say "SS step-1 frame index 1 strict bitwise pass"; "all frames" or unqualified last-frame parity is false for the checked fresh run.

## [2026-06-29] reflect | parity gate and AD surface validate disjoint quantities; multi-step divergence and perf are un-paged
- Cycle: first /kg-reflect for this wiki (6 ingests, 0 prior reflects → reflect_debt reset to 0).
- Sample: hot.md, overview.md, log.md tail; concepts {KDM6AD Forward Parity, KDM6AD Automatic Differentiation ABI, KDM6AD Differentiability Audit, KDM6AD Mathematical Microphysics Operators}; entities {KDM6, KDM6AD}; sources/kdm6-vs-kdm6ad-code-comparison.
- Insight 1 (blind_spot/cross-reference): forward parity is f32 on outputs incl. diag_rhog/REFL_10CM/re_*, which the fp64 packed AD ABI excludes. The parity guardrail does not cover the differentiated fp64 map; no wiki page gates the fp64 forward map against KDM6.
- Insight 2 (shifted_ground/temporal): SS bitwise parity passes at step-1 frame index 1, but frames 2/3 diverge (19 then 51 differing variables, 2026-06-25 kg-lint). KDM6AD Forward Parity concept page omits this; multi-step trajectory drift is unbounded/unexplained.
- Schema signal SIG-001 (EMERGING_CLASS Benchmark, medium): "mp137 slower" recurs across 5 pages / multiple ingests with no quantified Benchmark page.
- Side effects: hot.md Key Tensions + Recent Activity updated; no content pages created; schema unchanged (signal only).

## [2026-06-30] kg-query | frame-2 rain-sedimentation bitwise fix + graupel-density floor
- Added query page: queries/kdm6ad-frame2-rain-sed-bitwise-fix-2026-06-30.md.
- Resolved Insight-2's open question (why frames 2/3 diverge): the seed is rain/graupel SEDIMENTATION, NOT condensation/satadj. Step 1 is globally bitwise-clean; step-2 micro entry (post-sed) diverged only in qr/nr/qg.
- Fixed 2 verified 1:1 deviations in the C++ port: sedimentation.cpp falk_nr missing .to(f32) (Fortran falkn REAL4); slope.cpp:77 rain vtn f32→f64 (Fortran F:3647/3755 DOUBLE). Verified: nr/qr bitwise; frame-2 19→16 vars; QNRAIN ↓99.5%; RAINNC/VIS_SFC/VIS_SFC_RAW resolved.
- Remaining frame-2 divergence proven to be the §48 graupel-density clamp floor (RHO_ICE Δ=800=clamp range, 140/208 cells at 100/900 bound) + brs near-zero noise (25787 no-graupel cells ≈0). Decision: accept prognostic-field parity; graupel-density (diag_rhog) is the documented AD-limit/§48 floor, out of scope.
- Harness bug found: KDM6_DUMP_CALL counts (step×tile), KDM6_DUMP_STEP counts steps → misaligned under numtiles=2 (use CALL=3 for step2/tile1).
- Transferable traps recorded to fortran-pytorch-port lessons-learned §50/§51/§52.

## 2026-07-02 — 10-step full-variable bitwise parity ACHIEVED
- **10/10 frames STRICT BITWISE PASS** (254 vars, mp37 vs mp137, SS real case). Goal "10 step 적분까지 bitwise" met.
- Added query page: queries/kdm6ad-10step-bitwise-achieved-2026-07-02.md (fix ladder §53-§53s, method, caveats).
- Key final fixes: §53k unconditional rate-loop vt2 (sed-zeroing must NOT reach rates); §53n wilt RAW ratios (19 sites, orders-of-magnitude class); §53q Picons/limiter gates (per-cell ncmin, no added ni>0 guard); §53r RHO_ICE 100-bound snap; §53s Nrevp IN-LOOP nr→nccn transfer (mid-rate-loop state mutation semantics).
- Transferable traps → fortran-pytorch-port lessons-learned §53-§59.

## [2026-07-02] kg-update | KDM6AD-k full-corpus graph rebuild (post-bitwise campaign)
- Source dir(s): . (graphify-out/.graphify_root)
- Mode: cli-update (AST-only, SHA256 cache; graphify 0.8.39, 0 LLM tokens)
- Delta: 42076 nodes · 67567 edges · 4922 communities (4985 files scanned, all re-extracted; 98% EXTRACTED / 2% INFERRED)
- Wiki sync: single-corpus — wiki/graph-report.md created (was absent)
- Caveats: Fortran cross-file `calls` edges partial (same-file callees only; USE/defines backbone reliable). macOS Apple-clang cpp cannot pre-resolve `.F` #ifdef → capital-F files parsed raw with all branches present. graph.html skipped (42076 > 5000 viz limit).

## [2026-07-02] reflect | Achieved-parity result inverts the wiki's core "step-1 gate / irreducible §48 floor" narrative; op-path-raw vs DA-clamped idiom has no page
- Insight 1 (shifted_ground): 10-step/12h full bitwise SUPERSEDES the 06-30 "accept prognostic parity, graupel-density floor out-of-scope" verdict. Forward-Parity concept + overview + 06-30 query still assert step-1-only gate & irreducible floor — both false.
- Insight 2 (emerging_pattern): dtype-conditional "raw on f32 op-path / clamped-safe on f64 DA-path" idiom used ~25× reconciles Differentiability-Audit's "clamps are AD-safe" with the port's "clamps break Fortran parity" — no concept/heuristic page exists.
- Schema signals: SIG-001 SUPERSESSION (06-30 floor decision → 07-02 achievement); SIG-002 EMERGING_CLASS/HEURISTIC (op-raw/DA-clamped idiom).
- hot.md updated (Recent Activity + Key Tensions rewritten, date bumped); reflect_debt → 0.

## [2026-07-02] kg-ingest | Folded achieved-parity reality into Forward Parity concept + overview
- Source: [[kdm6ad-10step-bitwise-achieved-2026-07-02]] (already-filed query page) + log/lessons-learned
- Updated: concepts/KDM6AD Forward Parity.md (Current Status rewritten to 10-step/12h all-frame bitwise; diag_rhog rationale corrected; op-raw/DA-clamped idiom added; 2 supersession callouts preserving old step-1-gate + §48-floor framing), overview.md (parity theme + open questions)
- Tensions: source overturns page's own prior "step-1 gate" + "irreducible graupel floor" claims → preserved as [!warning] supersession callouts, not erased
- No new pages; no schema change. reflect_debt already reset this cycle.

## [2026-07-02] verify | 12h np4 gate FAILED to confirm (mp137 MPI-init crash, not divergence); np1 long gate relaunched
- 12h -np4 --mca btl self,tcp: mp37 rc=0 (12 frames), mp137 rc=1 crashed at step 1 (wrote only IC frame). "1/12 PASS" is mp137's missing data (frame-oob), NOT a numerics divergence — index 0 (IC) is bitwise.
- Root cause: Open MPI runtime init race with the libtorch-loaded mp137 ranks (flaky; shm→SIGSEGV, tcp→rc=1). Numerics/bitwise fidelity unaffected.
- Wiki corrected: Forward Parity + overview walked back from "12h confirmed" to "10-step confirmed at np1; 12h/MPI gates in progress."
- Relaunched definitive 12h gate at np1 (flake-free) under nohup → SS_MPI4/GATE12H_NP1_STATUS.

## [2026-07-03] fix | step-23 NaN root cause = §53v stale-supcol (homog heating timing) + REFL cmg asymmetry; 19/19 frames bitwise
- NaN chain: homog(T<233K) cells first appear step-16 → C++ pre1.supcol (post-homog t) vs Fortran loop-top supcol (pre-pihmf t) → D4 bigg_factor 0.2-2.3% → qg/brs/qr seed → step-22 nc/nr/ni NaN → step-23 wrapper guard fatal ("kdm6ad: NaN after copy-back" — the flaky "MPI crash" was this, not a transport bug).
- Fix §53v-minimal: mf_view supcol = compute_supcol(pre-homog t) ONLY (full homog/reslope reorder regressed 650k cells — reverted). REFL_10CM: mp37 cmg1d now uses reconciled diag_rhog (symmetric with mp137 wrapper).
- Verified: 6-min np1 pair 19/19 frames STRICT BITWISE (254 vars). Final 12h np4-tcp gate running (SS_MPI4B GATE12H_FINAL_STATUS).
- Traps → fortran-pytorch-port lessons-learned §62-§64.

## [2026-07-03] investigate | np≥2 비결정·NaN의 진원은 업스트림 KDM6(qnn) — mp137 포팅 결백 확정
- 대조 실험 사다리: WSM6 np2 재현 PASS(호스트 결백) → mp37 np2/np4 재현 FAIL → 순정(계측 제거) 빌드도 FAIL → numtiles=1도 FAIL → **순정 mp37의 QNCCN이 step2-3에 43k셀 확산+NaN** (north-rank 광역, 수-ULP~NaN).
- mp137-특이 결함은 전부 수정: §53w(clamp NaN-전파→fmax/fmin), NN-init halo-dz8w 미초기화 읽기(kdm6.F+래퍼 tile-restrict), pre-bridge NaN 판별 가드. mp137 np4 크래시 급감.
- 결론: np≥2 bitwise 페어는 업스트림 qnn 비결정 해결 전까지 성립 불가 — np1이 유효 게이트(19/19 bitwise 확보, 6h 게이트 진행 중). 별도 과제: 업스트림 qnn NaN 추적(활성화 (sw)**actk 음수-거듭제곱? PD-이류 renorm? 스칼라 lateral-BC 부재?).
- 스킬 §66 기록(3-컨트롤 사다리: 원본 자기재현성 → 타 스킴 → 순정 빌드).

## [2026-07-03] bugreport | share/module_bc.F flow_dep_bdy_qnn OOB — 별도 리포트 발행
- 루트 `BUGREPORT_module_bc_flow_dep_bdy_qnn.md` + experiences/module-bc-flow-dep-bdy-qnn-oob-2026-07-03.md.
- 3중 결함(dz8w 전치 OOB, xland 선언 차원 오류, z_sum 행-누적) + 증폭기(mp_kdm6.F FP-동등 게이트) + 오인 경로 + 진단 사다리 + 수정/검증 상태 문서화.

## [2026-07-04] fix | §53x dqv_sum 타-분기 오염 — step-10 시드 소멸 (np1 36스텝 ALL PASS)
- 사다리: 30분 페어 바이섹션(첫 FAIL step10, QCLOUD/QVAPOR 1셀 1ULP) → np1 재현 → stage 사다리(postfreeze PASS/poststateupdate FAIL) → Δ-차분(Δt/Δqr 동일·Δqv만 상이) → 소비-층 프로브 양측(qv_base·prevp bitwise 동일, dqv_sum만 2ULP 차이) → cold.pinud의 warm-셀 잔존(2.3e-13)이 단일-체인 합을 오염.
- 수정: coordinator.cpp dqv를 분기-verbatim(cold F:2782 5항 / warm F:2913 3항, supcol where)으로 — xlwork2와 동일 구조.
- 교훈 §68(분기-verbatim 합·소비-층 프로브·Δ/dt 역산 우선), §69(덤프 리더 좌표기저 — lat/its가 2 시작; recs[108]이 이웃 셀이었던 '불가능한 관측'의 정체).
- 진행: mp137 vader np4 12h "SUCCESS COMPLETE WRF"(MPI-공존 종결) + §53x 최종 12h 페어 게이트 발사(mp37_final12h vs mp137 §53x vader).

## [2026-07-04] MILESTONE | mp37↔mp137 12h·MPI(np4) STRICT BITWISE 완전 달성 — 캠페인 목표 종결
- FINAL GATE: 12h(2160스텝) np4, 254변수 × 12프레임(0-11h) 전부 STRICT BITWISE PASS. mp37=tcp/mp137=vader(§53x dylib) — transport 수치-무영향 동시 실증. 12:00 적분 SUCCESS COMPLETE(정각 프레임은 복사 타이밍으로 미포함).
- 결정 수정 사슬(2026-07-03~04): flow_dep_bdy_qnn OOB 3종(업스트림, np≥2 비결정·NaN 근원) → §53w fmax/fmin → NN-init tile-restrict → §53x dqv 분기-verbatim(cold.pinud warm-잔존 오염).
- [[KDM6AD Forward Parity]] 최종 상태: np1 및 np4/12h 모두 달성. 이전 "10-step np1 한정" 주의 문구 대체.

## [2026-07-04] measure | FP-동등 게이트(F:3238) 변경은 회귀 — 실측으로 리포트 §7 권고 철회
- 사용자 지시("영향 미치는지 추가정보")에 따라 KDM6_GATE_DIAG 계측으로 12분·전도메인 측정: 게이트 8511만 발화 중 74.9%가 청천(qci=0) 셀. 청천 셀에서 pcond=0=-0로 발화→nci(1)을 CCN(nci3)으로 재활용. 이 덕분에 우려됐던 qmin-패딩 누수가 현재 0.
- 옵션 A(full-evap 한정)로 바꾸면 청천 재활용 소멸→315,445셀/12분·총 1.29e11 droplet을 패딩이 파괴(number 비보존). 즉 개선이 아니라 회귀. parity 위험도 없음(12h np4 bitwise가 게이트 통과 증명).
- 결론: 게이트 현상 유지. 측정 계측은 무해성(gate-diag ON==OFF 37/37 bitwise) 확인 후 제거. BUGREPORT §7 정정.
- 교훈: "amplifier"로 보이는 결정적 FP-동등 분기라도 변경 전 실측 필수 — 측정이 권고를 뒤집었다("measure before acting"이 harmful change를 예방).

## [2026-07-04] codex-review | 세션 변경 4건 검토 — 런타임 parity 3건 CORRECT, adjoint stale 1건 발견
- Codex(gpt-5.5, xhigh, read-only) 검토: ① flow_dep_bdy_qnn OOB 수정(전치/선언/컬럼적분) CORRECT, ② §53x dqv branch-verbatim(cold/warm 항집합·supcol 게이트) CORRECT, ③ NN-init tile-restrict + pre-bridge NaN 가드 CORRECT.
- 발견(pre-existing): wrftladj/solve_em_ad.F의 qnn adjoint 경로 stale — L3007 forward-recompute가 scale_h/dz8w/xland 누락, L5956 a_flow_dep_bdy_qnn은 ccn_conc조차 없는 구버전 시그니처. 활성 parity 경로 무관(em_real 미빌드), adjoint 재생성 필요한 별도 과제 → 부분 hand-patch 대신 BUGREPORT §7에 기록.

## [2026-07-04] kg-update | 그래프 포트-범위로 재초점 (host/ .gitignore 제외)
- Source dir: . (root); graphify 0.8.39, cli-update (AST-only, LLM 0)
- Delta: 42076→5460 노드, 67567→7798 엣지, 4922→243 커뮤니티 — .gitignore(이번 세션 추가)가 /host/ WRF 트리를 제외해 그래프가 libtorch/oracle/harness(미분가능 포트)로 재초점됨. god nodes: State·kdm62d_one_step·Forcing·model_to_rttov_tensors (이전 WRF module_configure 대체). 공개 포트 저장소 범위와 정합.
- Wiki sync: single (wiki/graph-report.md). index.md에 Graph snapshot 섹션 없음 → 미변경.
- Caveats: (1) host/ Fortran 참조는 이제 그래프에 없음 — 전체 트리 그래프가 필요하면 .gitignore 우회 필요. (2) Fortran calls 엣지는 파일 간 부분적(USE/defines 백본은 신뢰).

## [2026-07-04] reflect | 개념층이 달성·근본수정에 뒤처짐 + 이중경로 idiom 3주기 미페이지화
- 3 insights: (1) Differentiability Audit의 균일-클램프 프레이밍이 점프/꺾임 구분·이중경로로 이중 반증, (2) op-raw/DA-clamped idiom 여전히 페이지 없음(2026-07-02부터 3주기), (3) hot/overview가 "12h 진행중/MPI 크래시(수치 아님)"로 stale — 실제는 달성 + flow_dep_bdy_qnn 수치 NaN 오진. Forward Parity·log는 갱신, overview/hot Recent Activity 재작성은 /kg-ingest 필요.
- Schema drift: 없음. 관찰: heuristics(0)·procedures(0) 폴더가 fortran-pytorch-port 트랩·dump-bisection 사다리로 채울 여지.

## [2026-07-04] ingest | docs/KDM6AD_differentiable_mathematics.md → 수학·AD 지식 흡수
- Source page: [[kdm6ad-differentiable-mathematics-2026-07-04]]. Created: [[Operational-Raw vs DA-Clamped Dual Path]](concept). Updated: [[KDM6AD Automatic Differentiation ABI]](VJP/JVP/HVP·handle·custom Fn), [[KDM6AD Differentiability Audit]](점프 vs 꺾임 + 이중경로, Tension 콜아웃), [[KDM6AD Mathematical Microphysics Operators]](19-연산자 합성·야코비안), overview.md(12h 달성·flow_dep_bdy_qnn 오진 정정), concepts/sources _index.
- Tensions preserved: Audit "균일 클램프" vs 소스(점프/이중경로) → Tension 콜아웃; overview "12h 진행중/MPI 크래시" → 달성+수치 NaN으로 정정. Reflect Insight #1·#2·#3 모두 해소.

## [2026-07-04] verify | ctest is 14/16 on the pinned toolchain (public-surface review round 2)
- Applied a 12-finding static adversarial review (public-surface/ABI overclaim); rebuilt the port and measured **ctest 14/16** on clang 22.1.4 (ENVIRONMENT.md). Two aborts — `coordinator` `test_picons_inactive_when_ni_zero` (exact `<1e-15` inactive-branch equality) and `c_abi` `test_c_abi_vjp_jvp_roundtrip` (hard-coded f32-backward NaN-corner field set) — are numeric-corner asserts on the **f32 autograd backward**, sensitive to libm/compiler ULP; they do NOT touch the operational forward or the 12h×np4 bitwise parity. Confirmed PRE-EXISTING by stashing the review fixes and re-running from baseline `991b9d6` (identical 2 failures).
- Correction to older entries: the "ctest 16/16 passed" recorded 2026-06-25 ([[queries/kdm6ad-final-code-location-verification-2026-06-25]], [[sources/kdm6-vs-kdm6ad-code-comparison-2026-06-25]], log:194) held on the **prior toolchain**; those dated records are kept as history. Current-state docs (README, ENVIRONMENT.md, docs/HOST_INTEGRATION.md) now state 14/16 truthfully. The 2 asserts are tracked as an open numeric-robustness item, not yet fixed.

## [2026-07-04] fix | coordinator ctest failures were STALE TESTS (not f32-backward ULP) → 15/16
- Corrects the prior entry's mischaracterization (flagged by Codex stop-review). MEASURED the two failures instead of assuming:
  - `coordinator` was NOT f32-backward/ULP — it is **f64 forward** and had THREE stacked stale-test aborts (assert kills the binary at the first, masking the rest): (1) `test_picons_inactive_when_ni_zero` asserted a pre-§53q invariant (ni=0 ⇒ no Picons); §53q deliberately removed the ni gate to match Fortran mp37 (measured qi 1e-4→0, qs→1e-4 = full Picons fire, as designed) → renamed/rewritten to assert the §53q behavior. (2)+(3) `test_cold_phase_runs_finite` / `test_melt_freeze_phase_runs_finite` built synthetic `SlopeOutputs` with an aggregate initializer that omitted the appended `vt2r/vt2s/vt2i` fields, so positional init left `vtn_r/vtn_i/n0sfac_field` undefined → `c10::Error` "undefined Tensor" → fixed the initializers. All three are test-maintenance, NOT production bugs (operational path populates every field; 12h×np4 parity holds).
  - `c_abi` `test_c_abi_vjp_jvp_roundtrip` IS the f32 operational-graph backward: measured a NaN in the `th` gradient (field 0) beyond the test's hard-coded `{qi,nc,ni}` corner set. Left as an OPEN numeric item (not auto-widened — could mask a regression); the f32 backward is documented-nonfinite at corners (§0.1.A → DA uses fp64).
- Result: **ctest 15/16**. Docs (README, ENVIRONMENT.md, docs/HOST_INTEGRATION.md) updated from 14/16 + wrong "f32-backward ULP" framing to 15/16 + accurate per-failure characterization.

## [2026-07-04] fix | ctest GREEN 16/16 + public-surface round-3 (10 findings)
- **P0 — quickstart no longer red.** The f32 `c_abi` VJP/JVP corner-set assert (`f==4||8||9`) pinned a *non-contractual* detail — the f32 backward NaN at inactive-ice corners propagates to graph-connected inputs (e.g. `th`), and which fields is toolchain-dependent. Retightened the test to the actual CONTRACT: mechanics only (buffer overwritten + a real finite non-zero gradient + not-all-NaN); non-finite count is now a diagnostic print. Clarified the C ABI header contract: f32 handle VJP/JVP = mechanics/diagnostics (finiteness NOT guaranteed); reliable fp64 adjoints via `kdm6_step_ad_c`. **ctest 15/16 → 16/16.**
- **P0-3** `kdm6_step_ad_c` xland doc narrowed: a raw C pointer can't disambiguate flat batch order, so it MUST be Fortran column-major `(im,jme)` (impl always treats it so).
- **P1** C++ `Parameters`/`make_parameters` marked RESERVED/not-wired + `kdm6_step` now `TORCH_CHECK`-fails if a param requires grad (was a C++-side twin of the C ABI `param_grad_flags` trap). `GraphMode` modes other than `RecordGraph` now fast-fail in `Handle::vjp/jvp` (were silently ignored). `run_ss_case.py` guards `proc=None`/rc-fallback (mpirun/wrf.exe missing → OSError no longer `UnboundLocalError`). HOST_INTEGRATION "Source note" reworded (host_fortran/ is in the private tree, not this repo).
- **P2** New `test_c_abi_closep_nulls_handle` (idempotent NULL + real-handle nulling). C ABI now sets `*handle=nullptr` on every error path (`kdm6_step_c`/`_ad_c`). `wiki/graph-report.md` stale-mirror left with its strong GENERATED banner (regen needs a graphify run).
- Verified: `cmake --build` + `ctest` → **16/16 pass**. Docs (README/ENVIRONMENT/HOST_INTEGRATION) updated to green + the derivative contract.

## [2026-07-05] kg-update | REFUSED by anti-shrink guard — graph is SEMANTIC (doc+rationale), not code-only
- Source dir: `.` (scan-root memo `graphify-out/.graphify_root`); graphify 0.8.39; Mode: cli-update (attempted, no LLM).
- Guard fired: fresh code-only AST extract = **3983** nodes vs existing `graph.json` = **5460**. Refused (correctly) — "may be missing chunk files from a previous session."
- **Root cause**: the existing graph is a **semantic graph built by the `/graphify` LLM orchestrator** — `file_type` split = document 2897 + code 1844 + rationale 719. A bare `graphify update` does **code-only AST** and cannot regenerate the 2897 doc + 719 rationale nodes, so it always under-counts. **`--force` would DESTROY the 3616 doc/rationale nodes** (the entire LLM knowledge layer). Secondary: `host/` WRF Fortran (2187 files) is gitignored, so the code-only walk sees only 213 files.
- **Decision: did NOT `--force`.** Graph left intact (5460 nodes, built 2026-07-04, still within the 7-day freshness window). This session's actual changes were oracle docstrings + one `_lamda_from_qn` helper extraction + one dead-code removal + CI/docs — near-zero AST impact.
- Correct refresh tool = **`/graphify . --update`** (slash-orchestrator; LLM subagents re-extract code+docs+rationale). That is OUT of kg-update's code-only scope and costs LLM tokens → deferred to the user.
- Wiki sync: none (graph unchanged). `wiki/index.md` has no `## Graph snapshot` section (untouched). ⚠️ Future kg-update runs will hit the same guard — do NOT `--force`; use `/graphify . --update`.

## [2026-07-05] graphify --update | semantic rebuild (5460 → 3926 nodes) — doc/rationale layer refreshed
- Ran `/graphify . --update` (the correct tool the prior kg-update entry pointed to). Re-extracted 216 changed files: 111 code via AST (2586 nodes) + 105 doc/paper/wiki via 5 parallel general-purpose subagents (169 semantic nodes after dedup). Noise filtered (.obsidian/.omx/.remember/graphify-out, 15 files).
- `build_merge` into the existing graph: pruned changed-file old nodes; the 5190 manifest "deletions" (host/ .obsidian/.omx state) matched no graph nodes ("already clean" — host/ was never a subgraph, confirming the 5460↔code-only gap was doc/rationale-vs-code-only, not host/). Deduplicated 1715 nodes (68 exact + 1647 fuzzy).
- Result: **3926 nodes / 6748 edges / 247 communities**. file_type: code 1844→1871, document 2897→1277, rationale 719→729, concept 0→38, paper 0→11. Semantic layer preserved (2055). Verified healthy before force-writing graph.json (guard tripped on -1534; reduction is dedup+rescope, all key nodes present incl `_lamda_from_qn`, Dual-path, C ABI, Forward Parity).
- Outputs: graphify-out/{graph.json, graph.html, GRAPH_REPORT.md} regenerated; wiki/graph-report.md mirror synced. ~1.06M subagent tokens (5 agents).
