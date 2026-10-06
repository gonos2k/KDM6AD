# Bounded source-only research candidate: clean-workspace acceptance

The existing fp64 native-column command passed from a clean source clone, a
new Python environment installed from PyPI, and a freshly built/installed C ABI
library. Two runs produced raw-bit-identical arrays. This accepts one numerical
research configuration; it is not a published release, a licensed redistribution
package, a new KMA-window experiment, host forecast or scientific approval.

- Build source: PR #377 merge `4ce39d8043730c011e78c861da1768e64038faf1`.
- Source directory: `/private/tmp/KDM6AD-research-rc-20261006/source`.
- Python environment: `/private/tmp/KDM6AD-research-rc-20261006/env`.
- Isolated build/install: the sibling `build` and `install` directories.
- Source-only [user recipe](../../docs/RESEARCH_CANDIDATE.md).
- [Execution manifest](RESEARCH_CANDIDATE_result_2026-10-06.json),
  [raw receipts and arrays](RESEARCH_CANDIDATE_receipts_2026-10-06.zip),
  [resolved Python dependencies](RESEARCH_requirements_macos_arm64_2026-10-06.txt),
  and [native CLI acceptance driver](RESEARCH_column_acceptance_source_2026-10-06.py).

## Fixed configuration and actual results

The demonstrated environment is macOS arm64, Python 3.10.11, Torch 2.13.0,
NumPy 2.2.6, netCDF4 1.7.4, pytest 9.1.1 and pyproj 3.7.1; the manifest records
the observed OS version and exact Clang, GNU Fortran and CMake versions.
The candidate uses Release, `-ffp-contract=off`, live test assertions and
`KDM6_ENABLE_TEST_HOOKS=OFF`, without the substep-dump compile macro.

| Check | Executed result | Scope |
| --- | --- | --- |
| Fresh dependency install / pip check | Completed; no broken requirements | New venv, rather than inherited Python packages |
| Fresh C++ and Fortran build | Completed | No private host build or operational install changed |
| CTest | **19 passed, 0 failed, 0 skipped tests** | 17 C++ tests and two Fortran tests; fault-injection sections inside the ABI test are deliberately not compiled into this candidate |
| Installed ABI export surface | **11 expected symbols, no leaks** | Actual installed dylib |
| Loaded-library audit | Torch, Torch CPU and C10 loaded from the new venv | Dylib paths and hashes recorded, not inferred from headers |
| Native CLI | **Two `NUMERICAL_PASS` runs; arrays raw-bit identical** | Installed library, original retained native input |
| Real rejection cases | **Three expected nonzero exits** | Existing output preserved; outside-grid column and unsupported ice-domain input produce no normal result directory |
| Corrected public-only Python suite | **1,628 passed / 87 skipped / 0 failed** | Explicit empty RTTOV discovery paths; unavailable private assets reported |
| Supplementary CLI filesystem contract | **9 passed** | Analytic ABI double verifies saved PASS/FAILED status and return code, not native physics |
| Updated fixture predicate, assets absent | **10 passed / 1 skipped** | Two changed test files; no RTTOV profile supplied |
| Updated fixture predicate, assets present | **2 passed** | Historical pinned diagnostic still executes when its required inputs exist |

These counts overlap and are not additive. All full Python runs emitted 51
warnings, including Torch JIT deprecations and a NumPy-extension size warning;
the raw logs preserve them. Passing tests do not certify compatibility beyond
the recorded configuration or resolve those warnings on other environments.

The retained forecast hash is
`be0edb894d1ddc5996f925cf01d56d1d882b53d6ed0295566edac2cb60f31308`.
The command reads time index 1 at 2025-07-19 00:00:20 UTC, zero-based column
`(i,j)=(3,272)`, all 39 native levels, and stored NCCN. Its single 20-second
step uses selector 2, dry-number 1 and the unchanged 10/10 volume thresholds.
Maximum per-field JVP/FD relative difference is **5.583113428056277e-8**,
below the existing `1e-5` criterion; duality is **1.7898345672809642e-16**,
below the existing `1e-12` criterion. The physical number basis and observation
admission remain false. This is a snapshot-derived Python-reader/C ABI call,
not exact host-staged operand replay.

## Two reproducibility findings and their disposition

**Mixed Torch discovery.** A fresh `CMAKE_PREFIX_PATH` configure used the venv
Torch package/headers but selected existing Homebrew `libtorch` and `libc10`
through normal library discovery. Red independently reproduced this at configure
time. The candidate explicitly pins both library files; the README puts the
selected Torch library directory first with `CMAKE_LIBRARY_PATH` for a fresh
cache. The corrected build and actual loaded images agree. No Torch package,
physics formula, tolerance or operational default was modified.

**Incomplete private-test prerequisites.** The first explicitly public-only
suite returned **1 failed / 1,626 passed / 86 skipped**. Its historical clear-QV
test checked WRF/GK2A/calibration availability but unconditionally loaded a
missing RTTOV reference T/Q/pressure profile. Its predicate now also requires
those three profile files. The corrected suite passes and explicitly skips the
unavailable test; the same test passes with its profile present. Numerical
assertions and the production diagnostic are unchanged. The failing run is
retained in the bundle rather than relabeled as successful.

A preceding full suite returned **1,688 passed / 25 skipped** while the legacy
resolver discovered local `/Users/yhlee/AD-RTTOV` fixtures. That run includes
live RTTOV fixture tests and is retained as separate external-asset evidence.
It is not the public-only result or a native KMA-window acceptance. The
public-only run sets both RTTOV discovery variables to an explicit empty path.

## Provenance and package boundaries

The fresh library and native CLI were built/executed from the unchanged clean
PR #377 source. For the final Python suite only, the two changed test files were
overlaid onto that clone. The manifest records their hashes separately from all
compiled `libtorch` source hashes; no runtime/physics/ABI source was overlaid.
Two controlled binary-discovery links in the ignored `libtorch/build` directory
pointed Python parity tests at the fresh out-of-tree executables. The recipe
uses an ordinary in-tree ignored build directory instead.

The bundle contains logs, XML, manifests and generated numerical arrays, not
private host sources, native forecast files, installed binaries, RTTOV code,
coefficients or observational data. The native input must be separately supplied
with appropriate permission. Exact build/dependency versions belong to the
companion execution manifest; `acceptance-cases/acceptance.json` alone records
CLI source/input/library identity and outcomes.

Licensing/redistribution terms are unresolved. No tag, GitHub Release or binary
package was published. A second-user/second-machine acceptance and a clean Linux
native-input run are not claimed. KMA/RTTOV asset provisioning remains a separate
extension; B/R/bias, product compatibility, physical budgets and unattended
operation retain their existing unapproved status. The management maturity
scores are not recalculated from these test counts.
