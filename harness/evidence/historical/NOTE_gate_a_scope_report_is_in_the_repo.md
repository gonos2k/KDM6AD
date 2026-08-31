# The Gate A scope report the four-case withdrawal calls missing is in the repo

Moved here from `SCIENCE_STATUS.md`: this is release-adjudication history, not a
science statement, and the current-status table is for what is true of the model.

`g33m_v14_fourcase_result.json` is **withdrawn with no replacement**. Its stated
reason is that a decision-grade rerun needs `--gate-a-scope-report` and

> that report (sha256 cff6cb64f36f) is not on this host -- only its digest
> survives, in anchors.sh

That is not so, and was not so when it was written.

    harness/evidence/gate_a_scope_report.json
    sha256 cff6cb64f36f818f4eeb655ab8e5ffe3423195bdd4509b88bf4c128d0564dbd2

which is the pinned digest exactly. `git log --diff-filter=A` puts the file in
the tree at `28d5e35` on 2026-07-28, regenerated at `ed7cba6` on 2026-07-30. At
`2935fcd` (2026-08-21), the commit that wrote the withdrawal text, `git show`
returns the same 2053 bytes and the same sha256. The file was three weeks old and
byte-identical at the moment it was declared absent.

`gateb_g33m_check.py` takes it by PATH (`--gate-a-scope-report`, line 100) with a
separate `--expected-gate-a-scope-report-sha256`, so the refusal the withdrawal
describes -- passing the digest alone -- was correct, and unnecessary.

Feasibility was checked and the run deliberately NOT made: the pinned runtime is
present (`~/kdm6ad-g33m-runtime`, CPython 3.11.14, numpy 2.4.6, which is what the
verifier records) and the digest is in `anchors.sh` across the g33m trees. What
stops the regeneration is not availability. Writing a decision artifact for a
release gate is owner adjudication, and the withdrawal itself says attribution
is.

**The four-case verdict remains OPEN.** Nothing here moves it.
