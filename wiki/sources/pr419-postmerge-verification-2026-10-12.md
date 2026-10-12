---
title: PR418 post-merge verification omissions
type: source
date_ingested: 2026-10-13
source_type: code-review-and-tests
tags: [KDM6AD, AMI, provenance, regression]
---
# PR418 post-merge verification omissions

[[KDM6AD]] audit at main569892ae found two verification omissions after
[[pr418-nine-channel-closeout-2026-10-12]]: the future nine-channel driver
did not bind its viewing-geometry reader, and the nine-channel capture/audit
tests were outside public CI discovery. The [audit report](../../harness/evidence/pr419_postmerge_audit_2026-10-12/REPORT.md)
records source-mutation reproduction, direct producer binding and portable
oracle capture/quality/audit/checkpoint tests.

These fixes do not change the old radiative results, warning flags, observation
support rule or physical/AD map. Saved additional channels remain flagged32768;
no real9 analysis or new H ran. Portable tests use synthetic H and mocked input
provenance; the local complete-driver test additionally uses existing private
reference/template files and real KDM/L-BFGS. Neither is a native/RTTOV case.

PR418 manifests verify their committed historical sources. The new driver
source hash differs intentionally after this fix; original PLAN/BT/flag files
are preserved. Old pending receipts and historical builds remain bounded to
their recorded inputs and execution, not assertions about every current path.
