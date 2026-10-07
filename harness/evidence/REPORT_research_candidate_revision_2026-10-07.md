# Research recipe revision alignment — PR #378 checkout

The user recipe now selects clean PR #378 `30931e52f99e38f9abcd6e7e3b8cd055227a5c23`
for build, installation, native-column execution and Python tests. Both corrected
test files are in that commit; no test overlay is required. This resolves the
P2 instruction/source mismatch without changing physics, the ABI or thresholds.

The October 6 source/result/ZIP remain unchanged: they describe a clean PR #377
build and native run, followed by two declared test overlays for the final
Python suite. Those valid historical results are not renamed or attributed to
the new checkout.

## Executed matched recipe

A new clone, new venv installed from the committed dependency lock, and new
in-tree build/install directories were used under
`/private/tmp/KDM6AD-research-rc-20261007`. The clean source HEAD before and after
all checks is `30931e52`. CMake's source directory points into that clone;
Python runs with the same clone as cwd and the installed library explicitly
selected. There are no injected source/test files or binary-discovery links.

| Check | Result |
| --- | --- |
| Build/install and CTest | **19/19 passed**, including both Fortran tests |
| Installed C ABI exports | **Exactly 11 expected symbols** |
| Loaded Torch/Torch CPU/C10 images | All from the new venv; hashes recorded |
| Installed-library native-column runs | **Two NUMERICAL_PASS**, all saved array contents raw-bit equal |
| Rejections | **Three expected failures**: preserved existing output, outside-grid index, unsupported no-ice input |
| Public-only oracle | **1,628 passed / 87 skipped / 0 failed**, 51 warnings retained |
| Test/source composition | Clean `30931e52`, **no overlays** |

These counts overlap and are not additive. The test-hooks-OFF candidate does not
execute internal fault-injection sections; this is unchanged from October 6.
The retained native input and numerical gates are unchanged. The new installed
library SHA-256 is
`64cddefe4fce336a7b9a3979278692324a97a17fe7d5264224bcc05a7f20be2d`;
this newly produced file is identified by its own receipt, not the older hash.

The [execution manifest](RESEARCH_CANDIDATE_revision_result_2026-10-07.json)
binds the source files, clean HEAD, CMake source directory, library, loaded
images and case commands. The [raw receipt bundle](RESEARCH_CANDIDATE_revision_receipts_2026-10-07.zip)
contains logs/XML and generated arrays, with a digest for each member.

## Current driver and historical driver

The [October 7 witness](RESEARCH_column_acceptance_source_2026-10-07.py) requires
clean `30931e52`; its committed source is
`6fcfffa5422f339ed353c9559f2e2c84147b6997`, SHA-256
`8c204caec007446b478297a622fefe36600d155620e8b6a2e4dea5e65c5e94c8`.
The [guide](../../docs/RESEARCH_CANDIDATE.md) copies the witness from the cloned
tip into the external workspace and verifies that digest before selecting the
`30931e52` source checkout. It therefore does not require the authoring commit
to survive a squash/rebase merge. This keeps the
selected checkout clean and makes the additional witness source explicit.
The existing native CLI and all tests already reside in `30931e52`.

The unchanged October 6 witness still requires clean `4ce39d8`. It is a
historical reproduction tool, not the current-user acceptance driver. The guide
labels its old numeric/library record accordingly and links it separately.

No host forecast or new KMA-window run was performed. This remains one fixed
native-column research configuration on the same developer machine; it is not
a second-user/machine acceptance. Licensing, external-asset provision,
physical/observation approval and operational release retain their existing
unresolved or false dispositions. Management scores are not recalculated here.
