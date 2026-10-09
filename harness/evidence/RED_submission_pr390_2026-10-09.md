# Red submission-scope review: PR390 diagnostics

Reviewed the current candidate packet in the isolated `ada6fc42` worktree on 2026-10-09, after the root’s submission decision and wording updates. No files were staged at review time. The candidate consists of bounded evidence reports, hash/metadata receipts, small authored MPI/host capture scripts, derived RTTOV values, and captured control logs.

## Payload review

The private RTTOV source copy, diagnostic patch, object/library/executable, raw `ext`/`ltick` dump, profile files, and native host NetCDF inputs/outputs remain under ignored `graphify-out/`; none appear in the candidate file list. The tracked evidence contains derived values, source/build/input hashes, paths, and summary logs. The host state comparator receipt contains times and match counts rather than raw arrays. The candidate credential-pattern scan found no common API-token, private-key, cloud-key, or credential-assignment patterns.

The public payload includes only task-authored Fortran/Python controls and bounded logs; no RTTOV source code or coefficient/hydrotable content is present. The local scripts hardcode private workstation paths and licensed runtime assets, so they support the documented local runs rather than a general public replay. The reports scope that limitation and make no full-release or production-acceptance claim.

The license assessment now paraphrases the NWP SAF agreement terms and retains its official link. It states that the authorized instrumented source copy and resulting objects/dump remain private. The two time-sensitive report statements are now framed by date: the Oct 8 diagnostic phase occurred locally, and the Oct 9 audit itself ended before the user-requested PR action. The decision note makes clear that submitting the PR does not approve the pending scientific choices, physical observation case, or operations.

## Submission status

The content is suitable for the requested PR once the root stages the intended tracked evidence. Keep `graphify-out/` ignored and excluded. The remaining Oct 8 MPI orchestration-hash gap, failed historical target run, and open physical/independent-case work are disclosed in the reports; the separately pinned current MPI witness does not claim to recover the historical script hash.
