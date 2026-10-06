# Source-only research candidate acceptance

This is the smallest proposed clean-workspace acceptance path for the
normalized dry-number microphysics candidate. It separates the C/C++ library
build from a single native-column experiment and from the optional GK2A–RTTOV
window path. It is not a binary distribution, WRF host integration,
accepted-observation cost, physical-policy approval, or operational release.
Distribution/license permission has not been established; this repository
does not designate a canonical binary release.

## 1. Build and install the C ABI library

Use a clean checkout at the candidate revision. The demonstrated reference
acceptance environment is macOS arm64 with Apple Clang 21.0, CMake 3.24.4,
Python 3.10.11 and a local PyTorch install that provides CMake's `Torch`
package. The [execution manifest](../harness/evidence/RESEARCH_CANDIDATE_result_2026-10-06.json)
and [report](../harness/evidence/REPORT_research_candidate_2026-10-06.md) bind the
build, loaded images, tests and native command receipts. GNU Fortran 15.2.0 is optional for the C++ library but adds ISO_C
smoke tests when CMake detects it. The fully resolved Python dependencies are
[recorded separately](../harness/evidence/RESEARCH_requirements_macos_arm64_2026-10-06.txt);
the inline installer below pins the direct dependencies.

```sh
set -eu
git clone https://github.com/gonos2k/KDM6AD.git KDM6AD
cd KDM6AD
git checkout 4ce39d8043730c011e78c861da1768e64038faf1

KDM6_WORK="$(mktemp -d)"
python3 -m venv "$KDM6_WORK/env"
. "$KDM6_WORK/env/bin/activate"
python -m pip install \
  torch==2.13.0 numpy==2.2.6 netCDF4==1.7.4 pytest==9.1.1 pyproj==3.7.1

KDM6_ROOT="$(pwd)"
KDM6_BUILD="$KDM6_ROOT/libtorch/build"
KDM6_INSTALL="$KDM6_ROOT/libtorch/install"
TORCH_ROOT="$(python -c 'import os, torch; print(os.path.dirname(torch.__file__))')"
TORCH_CMAKE_DIR="$TORCH_ROOT/share/cmake"

if test -e "$KDM6_BUILD" || test -e "$KDM6_INSTALL"; then
  echo "use a fresh build and install tree" >&2; exit 1
fi
unset KDM6_SUBSTEP_DUMP
cmake -S "$KDM6_ROOT/libtorch" -B "$KDM6_BUILD" \
  -DCMAKE_PREFIX_PATH="$TORCH_CMAKE_DIR" \
  -DTorch_DIR="$TORCH_CMAKE_DIR/Torch" \
  -DCMAKE_INSTALL_PREFIX="$KDM6_INSTALL" \
  -DCMAKE_BUILD_TYPE=Release \
  -DTORCH_LIBRARY="$TORCH_ROOT/lib/libtorch.dylib" \
  -Dc10_LIBRARY="$TORCH_ROOT/lib/libc10.dylib" \
  -DKDM6_ENABLE_TEST_HOOKS=OFF
cmake --build "$KDM6_BUILD" --parallel 2
ctest --test-dir "$KDM6_BUILD" --output-on-failure
cmake --install "$KDM6_BUILD"

python "$KDM6_ROOT/libtorch/tests/check_c_abi_exports.py" \
  "$KDM6_INSTALL/lib/libkdm6_c.2.0.0.dylib"
```

The install is a versioned library and headers under the in-tree ignored
prefix; it does not create a CMake package config. Record the source commit and
dirty state, compiler/CMake/PyTorch versions, installed library hash,
configured CTest count and ABI-export result with the acceptance record. CTest
has 17 base tests; it adds two Fortran smoke tests if a Fortran compiler is
detected. Test hooks and the substep-dump macro are off for this candidate
build. The fresh reference build completed all 19 configured tests (17 C++/C
ABI plus two Fortran smoke tests), and the installed library exported the
expected 11 C ABI symbols.

For Python tests of the normalized column runner's input, ABI-call and failure
handling contract, run:

```sh
python -m pytest -q oracle/tests/test_normalized_dry_column_run.py
```

These tests use a mock ABI and do not substitute for the real-library column
run below. For a public-only suite, explicitly disable private RTTOV discovery and point
the ABI test at the built library:

```sh
mkdir "$KDM6_WORK/empty-rttov"
AD_RTTOV_HOME="$KDM6_WORK/empty-rttov" \
KDM6_RTTOV_RUNTIME="$KDM6_WORK/empty-rttov" \
KDM6_C_LIBRARY="$KDM6_INSTALL/lib/libkdm6_c.2.0.0.dylib" \
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  python -m pytest -rs -q oracle/tests
```

Optional fixture tests must report unavailable assets as skips. A run using
local RTTOV fixtures is separate evidence; an unset `AD_RTTOV_HOME` can resolve
the historical maintainer path and must not be called a public-only acceptance.

## 2. Run one native 5 km microphysics column

Supply an authorized native WRF/KIM-meso history file as `NATIVE_INPUT`. The
file is not included in this repository. The retained candidate frame has
`DX=DY=5000 m`, 234×282 columns, 39 model layers and frame index 1 at
2025-07-19 00:00:20 UTC. Its expected SHA-256 is
`be0edb894d1ddc5996f925cf01d56d1d882b53d6ed0295566edac2cb60f31308`; the
selected zero-based column is `(i,j)=(3,272)`. Use the same input hash and
column for an independent replay. Do not substitute a remapped profile,
another forecast or synthesized QNCCN.

```sh
NATIVE_INPUT="/path/to/retained/native_5km_history"
KDM6_LIBRARY="$KDM6_INSTALL/lib/libkdm6_c.2.0.0.dylib"
KDM6_OUTPUT="$KDM6_WORK/normalized-dry-column"

DYLD_LIBRARY_PATH="$TORCH_ROOT/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  python oracle/scripts/run_normalized_dry_column.py \
    --input "$NATIVE_INPUT" \
    --library "$KDM6_LIBRARY" \
    --time-index 1 --i 3 --j 272 \
    --output "$KDM6_OUTPUT"
```

The output path must not exist. Keep `arrays.npz` and `result.json` as the
acceptance artifacts; the result records input, library and runner hashes.
Acceptance of this numerical column experiment requires exit status 0,
`NUMERICAL_PASS`, finite graph and value-only outputs, raw-bit graph/value
agreement, strict paired-moment input/output admission, JVP/VJP duality at or
below 1e-12, and all twelve per-field centered-FD relative errors at or below
1e-5. Preserve any failure result as a failure; do not weaken a gate to make
the candidate pass. A pass applies only to this fixed 20 s, selector-2,
dry-number-1 experiment with the runner's recorded 10/10 volume thresholds
and stored NCCN. It establishes neither physical number-unit calibration nor
observation or operational approval.

The clean-source acceptance run used Python 3.10.11, PyTorch 2.13.0, NumPy
2.2.6 and netCDF4 1.7.4. It executed this fixed column twice. Both runs
returned `NUMERICAL_PASS` and their fourteen saved arrays matched raw-bit; the
installed library SHA-256 was
`c8d3bcbfeb6ee9f7bada2c93a3dec4baad78313183f93c63c9e4b26571f91acd`. The
installed library's actual loaded libtorch/libc10 images were verified to come
from this fresh environment. Three negative checks behaved as expected: an
existing output directory was left unchanged, `i=234` was rejected outside
the input grid, and a clear column was rejected because it has no input ice.
The [acceptance driver](../harness/evidence/RESEARCH_column_acceptance_source_2026-10-06.py)
pins the source revision, input hash and installed-library hash for these
repeats/rejections. These checks accept this installed library/column
candidate only; they do not extend the tested profile domain.

To check preflight failures without inventing malformed NetCDF assets, use a
missing input path and a pre-existing empty output directory. Both commands
must exit nonzero; the missing-input command must not create its output path,
and the existing-output directory must remain empty.

```sh
if python oracle/scripts/run_normalized_dry_column.py \
  --input "$KDM6_WORK/no-such-native-input.nc" --library "$KDM6_LIBRARY" \
  --time-index 1 --i 3 --j 272 --output "$KDM6_WORK/missing-input-output"; then
  echo "unexpected success" >&2; exit 1
fi
test ! -e "$KDM6_WORK/missing-input-output"

mkdir "$KDM6_WORK/preexisting-output"
if python oracle/scripts/run_normalized_dry_column.py \
  --input "$NATIVE_INPUT" --library "$KDM6_LIBRARY" \
  --time-index 1 --i 3 --j 272 --output "$KDM6_WORK/preexisting-output"; then
  echo "unexpected success" >&2; exit 1
fi
test -z "$(find "$KDM6_WORK/preexisting-output" -mindepth 1 -print -quit)"
```

Linux port CI is a separate portability gate; no clean Linux native-input
acceptance is claimed here. To adapt this recipe there, use the installed `.so.2.0.0` library, `libtorch.so` and `libc10.so`
for the two explicit CMake library paths, and `LD_LIBRARY_PATH` instead of
`DYLD_LIBRARY_PATH`.

## 3. Keep the KMA–RTTOV extension separate

The Python APIs can select `normalized_dry=True` with
`observation_coordinate="kma_v3_0"` for thermal AMI channels 8–16, diagnostic
Huber delta and sigma of 1, zero bias, no pseudo-RH, an explicit native-grid
cloud fixture and frozen background optical density. This is a constrained
research configuration; it does not supply missing observation data or
approve a scientific cost.

The retained native KMA window runner is not a clean-workspace command: its
source pins a private forecast, profile-preparation receipt and RTTOV fixture
under `/private/tmp`. An independent KMA/RTTOV acceptance also needs the actual
native model frame, observation and geolocation inputs, calibration table,
RTTOV executable, coefficients and AMI hydrotables, plus declared surface,
geometry and reference-profile assets. The runtime resolver uses a local
`rttov_runtime` bundle when present or `AD_RTTOV_HOME` otherwise; a bundle also
depends on system libraries. Those assets and their redistribution rights are
not provided by this document. Do not treat CTest or the one-column
microphysics CLI as KMA window acceptance.
